"""Local Archive, Docker Config, and Runtime identity verification."""

from __future__ import annotations

from pathlib import Path
import stat
from typing import Mapping

from oc2_slice_b_image_record import (
    ImagePin,
    JsonValue,
    SliceBImageRejected,
    _BASE_IMAGE_DIGESTS,
    _DIGEST,
    _MAX_ARCHIVE,
    _sha_file,
    _validate_pin,
)

_ENTRYPOINT = ["/opt/oc2/slice-b/entrypoint"]


def verify_image_archive(archive: Path, pin: ImagePin) -> None:
    _validate_pin(pin)
    if _sha_file(archive, _MAX_ARCHIVE) != pin.archive_sha256:
        raise SliceBImageRejected("Writer archive SHA-256 mismatch")
    try:
        metadata = archive.lstat()
    except OSError as error:
        raise SliceBImageRejected("Writer archive metadata unavailable") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != pin.archive_size_bytes:
        raise SliceBImageRejected("Writer archive size/type mismatch")


def verify_loaded_image(inspect: Mapping[str, JsonValue], pin: ImagePin) -> None:
    """Require local Config ID and build labels, independent of RepoDigests."""
    _validate_pin(pin)
    _validate_image_config(
        inspect,
        config_id=pin.config_id,
        platform=pin.platform,
        labels=_record_labels(pin),
    )


def _record_labels(pin: ImagePin) -> dict[str, str]:
    return {
        "dev.oc2.source-revision": pin.source_revision,
        "dev.oc2.artifact-sha256": pin.artifact_sha256,
        "dev.oc2.runtime-sha256": pin.runtime_sha256,
        "dev.oc2.base-image-ref": pin.base_image_ref,
        "dev.oc2.build-context-sha256": pin.build_context_sha256,
    }


def _validate_image_config(
    inspect: Mapping[str, JsonValue],
    *,
    config_id: str,
    platform: str,
    labels: Mapping[str, str],
) -> None:
    if inspect.get("Id") != config_id:
        raise SliceBImageRejected("local image Config ID mismatch")
    os_name, architecture = platform.split("/", 1)
    if inspect.get("Os") != os_name or inspect.get("Architecture") != architecture:
        raise SliceBImageRejected("local image platform mismatch")
    config = inspect.get("Config")
    if not isinstance(config, dict):
        raise SliceBImageRejected("local image Config is unavailable")
    if (
        config.get("Entrypoint") != _ENTRYPOINT
        or config.get("Cmd") != ["run"]
        or config.get("User") != "10001:10001"
        or config.get("WorkingDir") != "/workspace"
    ):
        raise SliceBImageRejected("wrong immutable Writer image config")
    observed_labels = config.get("Labels")
    if not isinstance(observed_labels, dict) or any(
        observed_labels.get(name) != value for name, value in labels.items()
    ):
        raise SliceBImageRejected("Writer image build identity labels mismatch")
    env = config.get("Env", [])
    if not isinstance(env, list):
        raise SliceBImageRejected("image environment unavailable")
    safe_env_names = {"PATH", "HOME", "LANG", "LC_ALL", "TERM"}
    seen: set[str] = set()
    for entry in env:
        if not isinstance(entry, str) or "=" not in entry:
            raise SliceBImageRejected("invalid image environment")
        name, value = entry.split("=", 1)
        if name not in safe_env_names or name in seen or "\x00" in value or len(value) > 4096:
            raise SliceBImageRejected("unapproved image environment")
        seen.add(name)


def verify_local_base_image(inspect: Mapping[str, JsonValue], base_ref: str) -> None:
    if not _BASE_IMAGE_DIGESTS.fullmatch(base_ref):
        raise SliceBImageRejected("base image must use an immutable digest ref")
    refs = inspect.get("RepoDigests")
    if not isinstance(refs, list) or base_ref not in refs:
        raise SliceBImageRejected("exact base image digest is not local")


def verify_runtime_pin_against_manifest(pin: ImagePin, runtime_sha256: str) -> None:
    _validate_pin(pin)
    if not _DIGEST.fullmatch(runtime_sha256) or pin.runtime_sha256 != runtime_sha256:
        raise SliceBImageRejected("Writer runtime/Bundle Manifest mismatch")
