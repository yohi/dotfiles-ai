"""Canonical Host Image Record and Config-ID verification rules."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, TypeAlias

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)

_DIGEST: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")
_REF: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")
_IMAGE_ID: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BASE_IMAGE_DIGESTS: Final[re.Pattern[str]] = re.compile(
    r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z"
)
_MAX_ARCHIVE: Final[int] = 1024 * 1024 * 1024
_IMAGE_RECORD_SCHEMA: Final[str] = "dotfiles-ai/oc2-slice-b-image-record/v1"


def _string_field(data: dict[str, JsonValue], name: str) -> str:
    value = data[name]
    if not isinstance(value, str):
        raise SliceBImageRejected("invalid image record value types")
    return value


class SliceBImageRejected(RuntimeError):
    """A pinned Slice B image identity failed validation."""


@dataclass(frozen=True, slots=True)
class ImagePin:
    """Immutable Host build and archive identity; image_ref is provenance only."""

    source_revision: str
    artifact_sha256: str
    runtime_sha256: str
    base_image_ref: str
    build_context_sha256: str
    dockerfile_sha256: str
    image_ref: str | None
    config_id: str
    archive_sha256: str
    archive_size_bytes: int
    platform: str

    def to_bytes(self) -> bytes:
        """Encode the full image identity using canonical JSON bytes."""
        _validate_pin(self)
        payload: dict[str, JsonValue] = {
            "schema": _IMAGE_RECORD_SCHEMA,
            "source_revision": self.source_revision,
            "artifact_sha256": self.artifact_sha256,
            "runtime_sha256": self.runtime_sha256,
            "base_image_ref": self.base_image_ref,
            "build_context_sha256": self.build_context_sha256,
            "dockerfile_sha256": self.dockerfile_sha256,
            "image_ref": self.image_ref,
            "config_id": self.config_id,
            "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes,
            "platform": self.platform,
        }
        return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")

    @property
    def record_sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, raw: bytes, expected_sha256: str) -> ImagePin:
        """Parse one canonical record only when its external digest matches."""
        if len(raw) > 16_384 or not _DIGEST.fullmatch(expected_sha256):
            raise SliceBImageRejected("invalid Image Record size or expected digest")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise SliceBImageRejected("image record SHA-256 mismatch")
        try:
            value: JsonValue = json.loads(raw, object_pairs_hook=_unique_json_object)
        except (TypeError, ValueError, UnicodeError) as error:
            raise SliceBImageRejected("invalid image record JSON") from error
        if not isinstance(value, dict) or set(value) != {
            "schema", "source_revision", "artifact_sha256", "runtime_sha256",
            "base_image_ref", "build_context_sha256", "dockerfile_sha256",
            "image_ref", "config_id", "archive_sha256", "archive_size_bytes", "platform",
        }:
            raise SliceBImageRejected("invalid image record fields")
        if value["schema"] != _IMAGE_RECORD_SCHEMA:
            raise SliceBImageRejected("unsupported image record schema")
        image_ref = value["image_ref"]
        size = value["archive_size_bytes"]
        if image_ref is not None and not isinstance(image_ref, str):
            raise SliceBImageRejected("invalid image provenance reference")
        if isinstance(size, bool) or not isinstance(size, int):
            raise SliceBImageRejected("invalid image archive size")
        pin = cls(
            source_revision=_string_field(value, "source_revision"),
            artifact_sha256=_string_field(value, "artifact_sha256"),
            runtime_sha256=_string_field(value, "runtime_sha256"),
            base_image_ref=_string_field(value, "base_image_ref"),
            build_context_sha256=_string_field(value, "build_context_sha256"),
            dockerfile_sha256=_string_field(value, "dockerfile_sha256"),
            image_ref=image_ref,
            config_id=_string_field(value, "config_id"),
            archive_sha256=_string_field(value, "archive_sha256"),
            archive_size_bytes=size,
            platform=_string_field(value, "platform"),
        )
        _validate_pin(pin)
        if pin.to_bytes() != raw:
            raise SliceBImageRejected("image record is not canonical")
        return pin


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise SliceBImageRejected("duplicate image record field")
        result[key] = value
    return result


def _validate_pin(pin: ImagePin) -> None:
    if not isinstance(pin, ImagePin):
        raise SliceBImageRejected("invalid image record type")
    if not all(
        isinstance(value, str) and _DIGEST.fullmatch(value)
        for value in (
            pin.artifact_sha256, pin.runtime_sha256, pin.build_context_sha256,
            pin.dockerfile_sha256, pin.archive_sha256,
        )
    ):
        raise SliceBImageRejected("invalid image SHA-256 pin")
    if not isinstance(pin.config_id, str) or not _IMAGE_ID.fullmatch(pin.config_id):
        raise SliceBImageRejected("image config ID must be sha256:<64 hex>")
    if pin.image_ref is not None and (
        not isinstance(pin.image_ref, str) or not _REF.fullmatch(pin.image_ref)
    ):
        raise SliceBImageRejected("invalid origin image reference")
    if not isinstance(pin.base_image_ref, str) or not _BASE_IMAGE_DIGESTS.fullmatch(pin.base_image_ref):
        raise SliceBImageRejected("base image must use a pinned digest")
    if not isinstance(pin.source_revision, str) or not re.fullmatch(r"[a-f0-9]{40}", pin.source_revision):
        raise SliceBImageRejected("unverified source revision")
    if isinstance(pin.archive_size_bytes, bool) or not isinstance(pin.archive_size_bytes, int):
        raise SliceBImageRejected("invalid image archive size")
    if not 1 <= pin.archive_size_bytes <= _MAX_ARCHIVE:
        raise SliceBImageRejected("image archive size is outside the allowed bound")
    if pin.platform != "linux/amd64":
        raise SliceBImageRejected("unsupported Writer image platform")


def _sha_file(path: Path, max_bytes: int) -> str:
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
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise SliceBImageRejected("unsafe image input")
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            while block := stream.read(min(1024 * 1024, max_bytes + 1 - total)):
                total += len(block)
                if total > max_bytes:
                    raise SliceBImageRejected("image input exceeds size limit")
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise SliceBImageRejected("image input inaccessible") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_docker_host(docker_host: str) -> str:
    if not isinstance(docker_host, str) or not docker_host.startswith("unix:///" ):
        raise SliceBImageRejected("Docker endpoint must be an explicit Unix socket")
    socket_path = docker_host.removeprefix("unix://")
    if (
        "\x00" in socket_path
        or socket_path.startswith("//")
        or os.path.normpath(socket_path) != socket_path
        or any(part in ("", ".", "..") for part in socket_path.split("/")[1:])
    ):
        raise SliceBImageRejected("Docker Unix socket path is not canonical")
    return docker_host
