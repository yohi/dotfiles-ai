"""Trusted Guest image import and sealed image authority issuance."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_slice_b_image_record import ImagePin
else:
    from oc2_slice_b_image_record import ImagePin

from oc2_slice_b_image_record import (
    SliceBImageRejected,
    _validate_docker_host,
    _validate_pin,
)
from oc2_slice_b_image_verify import verify_image_archive, verify_loaded_image


@dataclass(frozen=True, slots=True)
class GuestImageLoadRequest:
    archive_path: Path
    supervisor_root: Path
    image_pin: ImagePin
    expected_record_sha256: str
    docker_host: str


class GuestImageRunner(Protocol):
    @property
    def docker_host(self) -> str: ...

    def image_ids(self) -> tuple[str, ...]: ...

    def load_image(self, archive: Path) -> None: ...

    def inspect_config_id(self, config_id: str) -> Mapping[str, Any]: ...


class _ImageAuthorityToken:
    __slots__ = ()


_IMAGE_AUTHORITY_TOKEN = _ImageAuthorityToken()


@dataclass(frozen=True, slots=True, init=False)
class VerifiedImageAuthority:
    image_pin: ImagePin
    image_record_sha256: str
    config_id: str
    platform: str
    _token: _ImageAuthorityToken = field(repr=False, compare=False)

    def __init__(
        self,
        image_pin: ImagePin,
        image_record_sha256: str,
        config_id: str,
        platform: str,
        *,
        _token: _ImageAuthorityToken,
    ) -> None:
        if _token is not _IMAGE_AUTHORITY_TOKEN:
            raise SliceBImageRejected("VerifiedImageAuthority is issued only after Guest import")
        object.__setattr__(self, "image_pin", image_pin)
        object.__setattr__(self, "image_record_sha256", image_record_sha256)
        object.__setattr__(self, "config_id", config_id)
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "_token", _token)


def is_verified_image_authority(authority: VerifiedImageAuthority | None) -> bool:
    if not isinstance(authority, VerifiedImageAuthority):
        return False
    return (
        authority._token is _IMAGE_AUTHORITY_TOKEN
        and authority.config_id == authority.image_pin.config_id
        and authority.platform == authority.image_pin.platform
        and authority.image_record_sha256 == authority.image_pin.record_sha256
    )


def _supervisor_archive_identity(
    archive: Path,
    root: Path,
    pin: ImagePin,
) -> tuple[int, int, int, int, int]:
    if not root.is_absolute() or ".." in root.parts:
        raise SliceBImageRejected("Supervisor image directory is unsafe")
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise SliceBImageRejected("symlink in Supervisor image directory")
    try:
        root_stat = root.lstat()
        archive_stat = archive.lstat()
    except OSError as error:
        raise SliceBImageRejected("Supervisor image archive is unavailable") from error
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or root_stat.st_uid != os.geteuid()
        or stat.S_IMODE(root_stat.st_mode) != 0o700
        or archive.parent != root
        or archive.name != pin.archive_sha256 + ".tar"
        or not stat.S_ISREG(archive_stat.st_mode)
        or archive_stat.st_uid != os.geteuid()
        or archive_stat.st_nlink != 1
        or stat.S_IMODE(archive_stat.st_mode) != 0o600
        or archive_stat.st_size != pin.archive_size_bytes
    ):
        raise SliceBImageRejected("Guest archive is outside the Supervisor-only store")
    return (
        archive_stat.st_dev,
        archive_stat.st_ino,
        archive_stat.st_size,
        archive_stat.st_mtime_ns,
        archive_stat.st_ctime_ns,
    )


def import_guest_image(
    request: GuestImageLoadRequest,
    runner: GuestImageRunner,
) -> VerifiedImageAuthority:
    """Load only a Host-pinned archive and issue authority after exact Config ID inspection."""
    pin = request.image_pin
    _validate_pin(pin)
    docker_host = _validate_docker_host(request.docker_host)
    if runner.docker_host != docker_host:
        raise SliceBImageRejected("Guest Docker socket does not match the import request")
    if request.expected_record_sha256 != pin.record_sha256:
        raise SliceBImageRejected("Host Image Record digest mismatch")
    before = _supervisor_archive_identity(request.archive_path, request.supervisor_root, pin)
    verify_image_archive(request.archive_path, pin)
    image_ids = runner.image_ids()
    if not isinstance(image_ids, tuple) or any(not isinstance(image_id, str) for image_id in image_ids):
        raise SliceBImageRejected("Guest Docker image listing is invalid")
    if image_ids:
        raise SliceBImageRejected("Guest Image Store is not empty before trusted import")
    runner.load_image(request.archive_path)
    after = _supervisor_archive_identity(request.archive_path, request.supervisor_root, pin)
    if before != after:
        raise SliceBImageRejected("Guest archive changed during Docker Load")
    verify_image_archive(request.archive_path, pin)
    inspect = runner.inspect_config_id(pin.config_id)
    verify_loaded_image(inspect, pin)
    return VerifiedImageAuthority(
        pin,
        pin.record_sha256,
        pin.config_id,
        pin.platform,
        _token=_IMAGE_AUTHORITY_TOKEN,
    )
