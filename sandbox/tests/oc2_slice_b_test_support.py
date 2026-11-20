from __future__ import annotations

import hashlib
from pathlib import Path
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sandbox.scripts.oc2_slice_b_image as slice_b_image
    from sandbox.scripts.oc2_slice_b_git import (
        GitBaseline,
        POLICY,
        SCHEMA,
        SliceBBundleManifestV1,
        _manifest_bytes,
    )
    from sandbox.scripts.oc2_slice_b_image import ImagePin
    from sandbox.scripts.oc2_slice_b_session import (
        GuestAuthorityVerificationRequest,
        SliceBReceipt,
        VerifiedGuestAuthority,
        _encode_receipt,
        verify_guest_authority_from_host_record,
    )
    from sandbox.scripts.oc2_writer import WriterSessionKey
else:
    from oc2_slice_b_git import GitBaseline, POLICY, SCHEMA, SliceBBundleManifestV1, _manifest_bytes
    from oc2_slice_b_image import ImagePin
    from oc2_slice_b_session import (
        GuestAuthorityVerificationRequest,
        SliceBReceipt,
        VerifiedGuestAuthority,
        _encode_receipt,
        verify_guest_authority_from_host_record,
    )
    from oc2_writer import WriterSessionKey


class FakeGuestImageRunner:
    docker_host: str = "unix:///var/run/docker.sock"

    def __init__(self, pin: slice_b_image.ImagePin) -> None:
        self.pin: slice_b_image.ImagePin = pin

    def image_ids(self) -> tuple[str, ...]:
        return ()

    def load_image(self, archive: Path) -> None:
        if not archive.is_file():
            raise AssertionError('test archive missing')
        return None

    def daemon_id(self) -> str:
        return 'test-daemon-id'

    def container_ids(self) -> tuple[str, ...]:
        return ()

    def inspect_config_id(self, config_id: str):
        return {
            "Id": config_id,
            "RepoDigests": [],
            "Os": "linux",
            "Architecture": "amd64",
            "Config": {
                "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                "Cmd": ["run"],
                "User": "10001:10001",
                "WorkingDir": "/workspace",
                "Env": [],
                "Labels": {
                    "dev.oc2.source-revision": self.pin.source_revision,
                    "dev.oc2.artifact-sha256": self.pin.artifact_sha256,
                    "dev.oc2.runtime-sha256": self.pin.runtime_sha256,
                    "dev.oc2.base-image-ref": self.pin.base_image_ref,
                    "dev.oc2.build-context-sha256": self.pin.build_context_sha256,
                },
            },
        }


def make_key() -> WriterSessionKey:
    return WriterSessionKey("a" * 32, str(uuid.uuid4()), str(uuid.uuid4()))


def make_verified_authority(
    root: Path, key: WriterSessionKey, *, baseline: GitBaseline | None = None,
) -> VerifiedGuestAuthority:
    """Create an isolated, cryptographically verified Guest authority test fixture."""
    root.mkdir(mode=0o700)
    control = root / "image-control"
    control.mkdir(mode=0o700)
    raw = b"test only Host-pinned Writer archive"
    pin = ImagePin(
        source_revision="f" * 40,
        artifact_sha256="c" * 64,
        runtime_sha256="b" * 64,
        base_image_ref="alpine@sha256:" + "d" * 64,
        build_context_sha256="1" * 64,
        dockerfile_sha256="2" * 64,
        image_ref=None,
        config_id="sha256:" + "c" * 64,
        archive_sha256=hashlib.sha256(raw).hexdigest(),
        archive_size_bytes=len(raw),
        platform="linux/amd64",
    )
    archive = control / (pin.archive_sha256 + ".tar")
    archive.write_bytes(raw)
    archive.chmod(0o600)
    if baseline is None:
        baseline = GitBaseline(
            root / "repo",
            "refs/heads/sliceb",
            "4" * 40,
            "5" * 40,
            "sha1",
            "6" * 64,
            "7" * 64,
        )
    manifest = SliceBBundleManifestV1(
        SCHEMA,
        key,
        baseline,
        "8" * 64,
        123,
        POLICY,
        pin.runtime_sha256,
    )
    manifest_bytes = _manifest_bytes(manifest)
    receipt_dir = control / key.session_generation
    receipt_dir.mkdir(mode=0o700)
    manifest_path = receipt_dir / "bundle.manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o600)
    receipt = SliceBReceipt(
        key=key,
        baseline=baseline,
        bundle_sha256=manifest.bundle_sha256,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        transfer_policy_id=POLICY,
        runtime_sha256=pin.runtime_sha256,
        image_record=pin,
        image_record_sha256=pin.record_sha256,
        state="PENDING",
        reason="NOT_RUN",
        writer_id=None,
        started_at=None,
    )
    receipt_path = receipt_dir / "receipt.json"
    receipt_bytes = _encode_receipt(receipt)
    receipt_path.write_bytes(receipt_bytes)
    receipt_path.chmod(0o600)
    return verify_guest_authority_from_host_record(
        GuestAuthorityVerificationRequest(
            receipt_path=receipt_path,
            expected_key=key,
            expected_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
            guest_baseline=baseline,
            archive_path=archive,
            supervisor_image_root=control,
            docker_host=FakeGuestImageRunner.docker_host,
        ),
        FakeGuestImageRunner(pin),
    )
