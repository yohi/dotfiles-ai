"""Trusted offline Writer image policy. Pure checks; no implicit Docker calls.

G0 evidence (Alpine) does not authorize a Writer image. A local digest-ref
resolution and expected config ID are both required; bare IDs and tags never
pass validation for execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_ARCHIVE = 1024 * 1024 * 1024
_ENTRYPOINT = ["/opt/oc2/slice-b/entrypoint"]


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
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
            raise SliceBImageRejected("unsafe image input")
        h = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                h.update(block)
        return h.hexdigest()
    except OSError as e:
        raise SliceBImageRejected("image input inaccessible") from e


def _validate_pin(pin: ImagePin) -> None:
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

    This function never downloads a binary or a base image. If the Host has not
    supplied a complete trusted pin record, the build is blocked.
    """
    root = source_root.resolve(strict=True)
    meta = root / "build-inputs.json"
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
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
    content = dockerfile.read_text("utf-8")
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
    for name in ("entrypoint.py", "offline_fixture.py"):
        _sha_file(root / name, 256 * 1024)
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
    source_root: Path, base_ref: str, *, transport_tag: str
) -> tuple[str, ...]:
    """Validated argv only. Caller must separately authorize and execute."""
    verify_build_inputs(source_root)
    if not _REF.fullmatch(base_ref):
        raise SliceBImageRejected("base must be digest pinned")
    meta = json.loads((source_root / "build-inputs.json").read_text())
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


def verify_image_archive(archive: Path, pin: ImagePin) -> None:
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


def verify_runtime_pin_against_manifest(pin: ImagePin, runtime_sha256: str) -> None:
    _validate_pin(pin)
    if not _DIGEST.fullmatch(runtime_sha256) or pin.runtime_sha256 != runtime_sha256:
        raise SliceBImageRejected("Writer runtime/Bundle Manifest mismatch")
