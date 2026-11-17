"""Validate the fixed local build context and pin its deterministic identity."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from oc2_slice_b_image_record import SliceBImageRejected, _DIGEST, _REF, _sha_file

_RUNTIME_FILES = ("entrypoint.py", "offline_fixture.py")
_BUILD_INPUTS_FILENAME = "build-inputs.json"
_OPENCODE_BINARY_FILENAME = "opencode-v2.2.5"
_MAX_BUILD_CONTEXT_FILE = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class BuildInputs:
    base_image_ref: str
    opencode_binary_sha256: str
    runtime_sha256: str
    source_revision: str


def verify_build_inputs(source_root: Path) -> BuildInputs:
    root = source_root.resolve(strict=True)
    try:
        data = json.loads(_read_file(root / _BUILD_INPUTS_FILENAME, 64 * 1024))
    except (OSError, ValueError) as error:
        raise SliceBImageRejected("trusted build inputs unavailable") from error
    if not isinstance(data, dict) or set(data) != {
        "base_image_ref", "opencode_binary_sha256", "runtime_sha256", "source_revision",
    }:
        raise SliceBImageRejected("invalid build input schema")
    try:
        inputs = BuildInputs(**data)
    except TypeError as error:
        raise SliceBImageRejected("invalid build inputs") from error
    if (
        not isinstance(inputs.base_image_ref, str)
        or not _REF.fullmatch(inputs.base_image_ref)
        or not isinstance(inputs.opencode_binary_sha256, str)
        or not _DIGEST.fullmatch(inputs.opencode_binary_sha256)
        or not isinstance(inputs.runtime_sha256, str)
        or not _DIGEST.fullmatch(inputs.runtime_sha256)
        or not isinstance(inputs.source_revision, str)
        or len(inputs.source_revision) != 40
        or any(char not in "0123456789abcdef" for char in inputs.source_revision)
    ):
        raise SliceBImageRejected("missing immutable build pin")
    if _sha_file(root / _OPENCODE_BINARY_FILENAME, _MAX_BUILD_CONTEXT_FILE) != inputs.opencode_binary_sha256:
        raise SliceBImageRejected("OpenCode v2.2.5 binary hash mismatch")
    dockerfile = _read_file(root / "Dockerfile", 64 * 1024).decode("utf-8")
    allowed = (
        "ARG BASE_IMAGE",
        "FROM ${BASE_IMAGE}",
        "ARG BASE_IMAGE",
        "ARG SOURCE_REVISION",
        "ARG ARTIFACT_SHA256",
        "ARG RUNTIME_SHA256",
        "ARG BUILD_CONTEXT_SHA256",
        "LABEL dev.oc2.source-revision=${SOURCE_REVISION} dev.oc2.artifact-sha256=${ARTIFACT_SHA256} dev.oc2.runtime-sha256=${RUNTIME_SHA256} dev.oc2.base-image-ref=${BASE_IMAGE} dev.oc2.build-context-sha256=${BUILD_CONTEXT_SHA256}",
        f"COPY --chmod=0555 {_OPENCODE_BINARY_FILENAME} /opt/oc2/bin/opencode",
        "COPY --chmod=0555 entrypoint.py /opt/oc2/slice-b/entrypoint",
        "COPY --chmod=0444 offline_fixture.py /opt/oc2/slice-b/offline_fixture.py",
        "WORKDIR /workspace",
        "USER 10001:10001",
        'ENTRYPOINT ["/opt/oc2/slice-b/entrypoint"]',
        'CMD ["run"]',
    )
    instructions = tuple(line for line in dockerfile.splitlines() if line and not line.startswith("#"))
    if any(line not in allowed for line in instructions) or instructions != allowed:
        raise SliceBImageRejected("Dockerfile instruction order or content mismatch")
    if _runtime_sha256(root) != inputs.runtime_sha256:
        raise SliceBImageRejected("runtime source hash mismatch")
    if {path.name for path in root.iterdir()} != {
        "Dockerfile", "entrypoint.py", "offline_fixture.py",
        _OPENCODE_BINARY_FILENAME, _BUILD_INPUTS_FILENAME,
    }:
        raise SliceBImageRejected("unexpected build-context file")
    return inputs


def build_context_sha256(source_root: Path) -> str:
    root = source_root.resolve(strict=True)
    names = ("Dockerfile", _BUILD_INPUTS_FILENAME, *_RUNTIME_FILES, _OPENCODE_BINARY_FILENAME)
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode("ascii") + b"\x00")
        digest.update(bytes.fromhex(_sha_file(root / name, _MAX_BUILD_CONTEXT_FILE)))
    return digest.hexdigest()


def _runtime_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in _RUNTIME_FILES:
        digest.update(name.encode("ascii") + b"\x00")
        digest.update(bytes.fromhex(_sha_file(root / name, 256 * 1024)))
    return digest.hexdigest()


def _read_file(path: Path, max_bytes: int) -> bytes:
    descriptor: int | None = None
    try:
        if max_bytes < 0:
            raise SliceBImageRejected("invalid image input size limit")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SliceBImageRejected("unsafe image input")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(max_bytes + 1)
    except OSError as error:
        raise SliceBImageRejected("image input inaccessible") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > max_bytes:
        raise SliceBImageRejected("image input exceeds size limit")
    return raw
