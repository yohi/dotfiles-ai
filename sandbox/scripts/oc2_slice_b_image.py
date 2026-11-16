"""Trusted offline Writer image policy and explicit build execution.

G0 evidence (Alpine) does not authorize a Writer image. A local digest-ref
resolution and expected config ID are both required; bare IDs and tags never
pass validation for execution. Verification helpers do not invoke Docker;
offline_build_argv explicitly inspects the local base, and build_offline_image
executes only after that preflight succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_ARCHIVE = 1024 * 1024 * 1024
_ENTRYPOINT = ["/opt/oc2/slice-b/entrypoint"]
_RUNTIME_FILES = ("entrypoint.py", "offline_fixture.py")
_BASE_IMAGE_DIGESTS = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")


class SliceBImageRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ImagePin:
    source_revision: str
    artifact_sha256: str
    runtime_sha256: str
    image_ref: str
    config_id: str
    archive_sha256: str


@dataclass(frozen=True)
class BuildInputs:
    base_image_ref: str
    opencode_binary_sha256: str
    runtime_sha256: str
    source_revision: str


def _sha_file(path: Path, max_bytes: int) -> str:
    """Hash a regular non-symlink file, enforcing max_bytes while reading it."""
    descriptor: int | None = None
    try:
        if max_bytes < 0:
            raise SliceBImageRejected("invalid image input size limit")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise SliceBImageRejected("unsafe image input")
        h = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            while block := stream.read(min(1024 * 1024, max_bytes + 1 - total)):
                total += len(block)
                if total > max_bytes:
                    raise SliceBImageRejected("image input exceeds size limit")
                h.update(block)
        return h.hexdigest()
    except OSError as e:
        raise SliceBImageRejected("image input inaccessible") from e
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_pin(pin: ImagePin) -> None:
    """Validate immutable pin field formats; this does not inspect files or Manifest data."""
    if not isinstance(pin, ImagePin) or not all(
        _DIGEST.fullmatch(v)
        for v in (pin.artifact_sha256, pin.runtime_sha256, pin.archive_sha256)
    ):
        raise SliceBImageRejected("invalid image SHA-256 pin")
    if not _REF.fullmatch(pin.image_ref) or not _IMAGE_ID.fullmatch(pin.config_id):
        raise SliceBImageRejected(
            "image must have exact repository@manifest-digest and config ID"
        )
    if not re.fullmatch("[a-f0-9]{40}", pin.source_revision):
        raise SliceBImageRejected("unverified source revision")


def verify_build_inputs(source_root: Path) -> None:
    """Require trusted, explicit and independently pinned local build inputs.

    This function never downloads a binary or a base image. The runtime digest
    frames each runtime filename, a NUL byte, and the raw 32-byte SHA-256 digest
    returned by _sha_file, in _RUNTIME_FILES order. The caller must keep inputs
    fixed between this check and the build.
    """
    root = source_root.resolve(strict=True)
    meta = root / "build-inputs.json"
    try:
        data = json.loads(_read_file(meta, 64 * 1024))
    except (OSError, ValueError) as e:
        raise SliceBImageRejected("trusted build inputs unavailable") from e
    if not isinstance(data, dict) or set(data) != {
        "base_image_ref",
        "opencode_binary_sha256",
        "runtime_sha256",
        "source_revision",
    }:
        raise SliceBImageRejected("invalid build input schema")
    try:
        args = BuildInputs(**data)
    except TypeError as e:
        raise SliceBImageRejected("invalid build inputs") from e
    if (
        not _REF.fullmatch(args.base_image_ref)
        or not _DIGEST.fullmatch(args.opencode_binary_sha256)
        or not _DIGEST.fullmatch(args.runtime_sha256)
        or not re.fullmatch("[a-f0-9]{40}", args.source_revision)
    ):
        raise SliceBImageRejected("missing immutable build pin")
    binary = root / "opencode-v2.2.5"
    if _sha_file(binary, 64 * 1024 * 1024) != args.opencode_binary_sha256:
        raise SliceBImageRejected("OpenCode v2.2.5 binary hash mismatch")
    dockerfile = root / "Dockerfile"
    content = _read_file(dockerfile, 64 * 1024).decode("utf-8")
    allowed = (
        "ARG BASE_IMAGE",
        "FROM ${BASE_IMAGE}",
        "COPY --chmod=0555 opencode-v2.2.5 /opt/oc2/bin/opencode",
        "COPY --chmod=0555 entrypoint.py /opt/oc2/slice-b/entrypoint",
        "COPY --chmod=0444 offline_fixture.py /opt/oc2/slice-b/offline_fixture.py",
        "WORKDIR /workspace",
        "USER 10001:10001",
        'ENTRYPOINT ["/opt/oc2/slice-b/entrypoint"]',
        'CMD ["run"]',
    )
    for line in content.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line not in allowed:
            raise SliceBImageRejected("Dockerfile contains unapproved instruction")
    if (
        tuple(
            line for line in content.splitlines() if line and not line.startswith("#")
        )
        != allowed
    ):
        raise SliceBImageRejected("Dockerfile instruction order mismatch")
    runtime_digest = _runtime_sha256(root)
    if runtime_digest != args.runtime_sha256:
        raise SliceBImageRejected("runtime source hash mismatch")
    # Reject broader contexts; binary/build-pins and exact source files only.
    found = {p.name for p in root.iterdir()}
    if found != {
        "Dockerfile",
        "entrypoint.py",
        "offline_fixture.py",
        "opencode-v2.2.5",
        "build-inputs.json",
    }:
        raise SliceBImageRejected("unexpected build-context file")


def offline_build_argv(
    source_root: Path, base_ref: str, *, transport_tag: str,
) -> tuple[str, ...]:
    """Return offline build argv only after inspecting the exact base image locally.

    Runs `docker image inspect` and rejects missing/mismatched local digest
    evidence. Use build_offline_image to execute the returned argv immediately.
    """
    verify_build_inputs(source_root)
    if not _REF.fullmatch(base_ref):
        raise SliceBImageRejected("base must be digest pinned")
    verify_local_base_image(_inspect_local_base_image(base_ref), base_ref)
    meta = json.loads(_read_file(source_root.resolve() / "build-inputs.json", 64 * 1024))
    if base_ref != meta["base_image_ref"] or transport_tag != "oc2-slice-b:transport":
        raise SliceBImageRejected("untrusted build settings")
    return (
        "docker",
        "build",
        "--pull=false",
        "--network=none",
        "--build-arg",
        "BASE_IMAGE=" + base_ref,
        "-t",
        transport_tag,
        str(source_root.resolve()),
    )


def _run_docker_command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run one bounded Docker CLI command without returning its output to users."""
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SliceBImageRejected("Docker command failed") from error


def _inspect_local_base_image(base_ref: str) -> Mapping[str, Any]:
    """Obtain one local Docker inspect record or reject before generating build argv."""
    result = _run_docker_command(("docker", "image", "inspect", base_ref))
    if result.returncode != 0:
        raise SliceBImageRejected("pinned base image is not available locally")
    try:
        inspect_data = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise SliceBImageRejected("invalid local base image inspection") from error
    if (
        not isinstance(inspect_data, list)
        or len(inspect_data) != 1
        or not isinstance(inspect_data[0], Mapping)
    ):
        raise SliceBImageRejected("invalid local base image inspection")
    return inspect_data[0]


def build_offline_image(
    source_root: Path, base_ref: str, *, transport_tag: str
) -> None:
    """Inspect the pinned base locally, then run the offline Docker build.

    The same Docker CLI context is used for both commands. Missing/invalid local
    image evidence aborts before the builder runs. Docker or validation failures
    raise SliceBImageRejected; command output is captured and not disclosed.
    """
    if not _REF.fullmatch(base_ref):
        raise SliceBImageRejected("base must be digest pinned")
    argv = offline_build_argv(source_root, base_ref, transport_tag=transport_tag)
    build_result = _run_docker_command(argv)
    if build_result.returncode != 0:
        raise SliceBImageRejected("offline Writer image build failed")


def verify_image_archive(archive: Path, pin: ImagePin) -> None:
    """Check archive hash against a format-validated pin; caller controls later file use."""
    _validate_pin(pin)
    if _sha_file(archive, _MAX_ARCHIVE) != pin.archive_sha256:
        raise SliceBImageRejected("Writer archive SHA-256 mismatch")


def verify_loaded_image(inspect: Mapping[str, Any], pin: ImagePin) -> None:
    """Inspect is the result of a **local exact image_ref lookup** by trusted Guest.

    Caller must use an injectable offline Docker runner and pass the result of
    `docker image inspect <pin.image_ref>`; no fallback to tag or ID permitted.
    """
    _validate_pin(pin)
    if not isinstance(inspect, Mapping):
        raise SliceBImageRejected("no image inspect response")
    if inspect.get("Id") != pin.config_id:
        raise SliceBImageRejected("local image Config ID mismatch")
    refs = inspect.get("RepoDigests")
    if not isinstance(refs, list) or pin.image_ref not in refs:
        raise SliceBImageRejected("exact digest-qualified RepoDigest is not local")
    cfg = inspect.get("Config")
    if (
        not isinstance(cfg, Mapping)
        or cfg.get("Entrypoint") != _ENTRYPOINT
        or cfg.get("Cmd") != ["run"]
    ):
        raise SliceBImageRejected("wrong immutable Writer entrypoint/cmd")
    if cfg.get("User") != "10001:10001" or cfg.get("WorkingDir") != "/workspace":
        raise SliceBImageRejected("wrong image UID/workdir")
    safe_env_names = {"PATH", "HOME", "LANG", "LC_ALL", "TERM"}
    env = cfg.get("Env", [])
    if not isinstance(env, list):
        raise SliceBImageRejected("image environment unavailable")
    seen: set[str] = set()
    for entry in env:
        if not isinstance(entry, str) or "=" not in entry:
            raise SliceBImageRejected("invalid image environment")
        name, value = entry.split("=", 1)
        if (
            name not in safe_env_names
            or name in seen
            or "\x00" in value
            or len(value) > 4096
        ):
            raise SliceBImageRejected("unapproved image environment")
        seen.add(name)


def _read_file(path: Path, max_bytes: int) -> bytes:
    """Read a bounded regular source file with an enforced in-read byte cap."""
    descriptor: int | None = None
    try:
        if max_bytes < 0:
            raise SliceBImageRejected("invalid image input size limit")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SliceBImageRejected("unsafe image input")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(max_bytes + 1)
    except OSError as e:
        raise SliceBImageRejected("image input inaccessible") from e
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > max_bytes:
        raise SliceBImageRejected("image input exceeds size limit")
    return raw


def _runtime_sha256(root: Path) -> str:
    """Hash runtime filenames and _sha_file digests in the canonical pin order."""
    digest = hashlib.sha256()
    for name in _RUNTIME_FILES:
        file_digest = _sha_file(root / name, 256 * 1024)
        digest.update(name.encode("ascii") + b"\x00")
        digest.update(bytes.fromhex(file_digest))
    return digest.hexdigest()


def verify_local_base_image(inspect: Mapping[str, Any], base_ref: str) -> None:
    """Require a local image inspection containing the exact digest-qualified base ref."""
    if not _BASE_IMAGE_DIGESTS.fullmatch(base_ref):
        raise SliceBImageRejected("base image must use an immutable digest ref")
    refs = inspect.get("RepoDigests")
    if not isinstance(refs, list) or base_ref not in refs:
        raise SliceBImageRejected("exact base image digest is not local")


def verify_runtime_pin_against_manifest(pin: ImagePin, runtime_sha256: str) -> None:
    """Compare a format-validated image pin with the trusted Bundle Manifest runtime digest."""
    _validate_pin(pin)
    if not _DIGEST.fullmatch(runtime_sha256) or pin.runtime_sha256 != runtime_sha256:
        raise SliceBImageRejected("Writer runtime/Bundle Manifest mismatch")
