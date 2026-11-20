from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest
from typing import TYPE_CHECKING, Any, Mapping, TypedDict, Unpack
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from oc2_slice_b_image import (  # noqa: E402
    ExistingGuestImageVerificationRequest,
    SliceBImageRejected,
    is_verified_image_authority,
    reverify_existing_guest_image,
)
from oc2_slice_b_git import BundleArtifact, admit_clean_repo  # noqa: E402
from oc2_slice_b_session import (  # noqa: E402
    ExistingGuestAuthorityVerificationRequest,
    SliceBReceipt,
    SliceBSessionError,
    create_session_receipt,
    import_guest_baseline,
    verify_guest_authority_from_existing_image,
)
from oc2_slice_b_image_record import ImagePin  # noqa: E402
if TYPE_CHECKING:
    from sandbox.tests.oc2_slice_b_test_support import FakeGuestImageRunner
else:
    from oc2_slice_b_test_support import FakeGuestImageRunner  # noqa: E402


class ImageRequestChanges(TypedDict, total=False):
    expected_docker_daemon_id: str
    expected_record_sha256: str
    docker_host: str


class ReadOnlyImageRunner(FakeGuestImageRunner):
    docker_host = "unix:///var/run/docker.sock"

    def __init__(self, pin: ImagePin) -> None:
        super().__init__(pin)
        self.daemon_ids: list[str] = ["a" * 64]
        self.images: tuple[str, ...] = (pin.config_id,)
        self.containers: tuple[str, ...] = ()
        self.calls: list[str] = []

    def daemon_id(self) -> str:
        self.calls.append("daemon")
        return self.daemon_ids.pop(0) if len(self.daemon_ids) > 1 else self.daemon_ids[0]

    def image_ids(self) -> tuple[str, ...]:
        self.calls.append("images")
        return self.images

    def container_ids(self) -> tuple[str, ...]:
        self.calls.append("containers")
        return self.containers

    def load_image(self, archive: Path) -> None:
        self.calls.append("load")
        raise AssertionError("existing-image verification must never load an image")

    def inspect_config_id(self, config_id: str) -> Mapping[str, Any]:
        self.calls.append("inspect")
        return super().inspect_config_id(config_id)


class ExistingImageAuthorityTests(unittest.TestCase):
    key: object
    art: BundleArtifact
    image_archive: Path
    image_control: Path
    image_pin: ImagePin
    rec: SliceBReceipt
    state: Path
    guest: Path

    def setUp(self) -> None:
        from test_oc2_slice_b_session import SessionTests

        SessionTests.setUp(self)

    def image_request(
        self, runner: ReadOnlyImageRunner, **changes: Unpack[ImageRequestChanges],
    ) -> ExistingGuestImageVerificationRequest:
        """Build an existing-image verifier request with test-controlled overrides."""
        args = {
            "archive_path": self.image_archive,
            "supervisor_root": self.image_control,
            "image_pin": self.image_pin,
            "expected_record_sha256": self.image_pin.record_sha256,
            "docker_host": runner.docker_host,
            "expected_docker_daemon_id": "a" * 64,
        }
        args.update(changes)
        return ExistingGuestImageVerificationRequest(**args)

    def test_reverify_issues_authority_without_docker_load(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        authority = reverify_existing_guest_image(self.image_request(runner), runner)
        self.assertTrue(is_verified_image_authority(authority))
        self.assertNotIn("load", runner.calls)

    def test_reverify_rejects_daemon_change_during_inspection(self) -> None:
        """Reject a daemon identity changed by inspection before the second observation."""
        runner = ReadOnlyImageRunner(self.image_pin)
        inspect = runner.inspect_config_id

        def change_daemon_during_inspection(config_id: str) -> Mapping[str, Any]:
            result = inspect(config_id)
            runner.daemon_ids = ["b" * 64]
            return result

        with patch.object(
            runner, "inspect_config_id", side_effect=change_daemon_during_inspection,
        ), self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_wrong_trusted_daemon_id(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(
                self.image_request(runner, expected_docker_daemon_id="b" * 64), runner
            )
        self.assertNotIn("inspect", runner.calls)

    def test_reverify_rejects_daemon_change_during_verification(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        runner.daemon_ids = ["a" * 64, "b" * 64]
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_nonempty_image_store(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        runner.images = (self.image_pin.config_id, "sha256:" + "e" * 64)
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_missing_expected_image(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        runner.images = ()
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_accepts_duplicate_tags_for_the_same_unique_image_id(self) -> None:
        """Accept duplicate listing rows when the unique image Config ID is pinned."""
        runner = ReadOnlyImageRunner(self.image_pin)
        runner.images = (self.image_pin.config_id, self.image_pin.config_id)

        authority = reverify_existing_guest_image(self.image_request(runner), runner)

        self.assertTrue(is_verified_image_authority(authority))

    def test_reverify_rejects_running_containers(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        runner.containers = ("container-id",)
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_containers_appearing_after_inspection(self) -> None:
        """Reject a container introduced between the two store observations."""
        runner = ReadOnlyImageRunner(self.image_pin)
        inspect = runner.inspect_config_id

        def add_container_during_inspection(config_id: str) -> Mapping[str, Any]:
            result = inspect(config_id)
            runner.containers = ("container-id",)
            return result

        with patch.object(
            runner, "inspect_config_id", side_effect=add_container_during_inspection,
        ), self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_image_store_change_after_inspection(self) -> None:
        """Reject an image store changed by inspection before the second observation."""
        runner = ReadOnlyImageRunner(self.image_pin)
        inspect = runner.inspect_config_id

        def clear_image_store_during_inspection(config_id: str) -> Mapping[str, Any]:
            result = inspect(config_id)
            runner.images = ()
            return result

        with patch.object(
            runner, "inspect_config_id", side_effect=clear_image_store_during_inspection,
        ), self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_wrong_record_hash_before_docker_queries(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(
                self.image_request(runner, expected_record_sha256="0" * 64), runner
            )
        self.assertEqual(runner.calls, [])

    def test_reverify_rejects_docker_socket_mismatch(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        with self.assertRaises(SliceBImageRejected):
            reverify_existing_guest_image(
                self.image_request(runner, docker_host="unix:///tmp/other.sock"), runner
            )

    def test_reverify_rejects_config_id_mismatch(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        inspect = runner.inspect_config_id
        with patch.object(
            runner,
            "inspect_config_id",
            side_effect=lambda config_id: {
                **inspect(config_id), "Id": "sha256:" + "f" * 64
            },
        ):
            with self.assertRaises(SliceBImageRejected):
                reverify_existing_guest_image(self.image_request(runner), runner)

    def test_reverify_rejects_archive_change_during_read_only_verification(self) -> None:
        runner = ReadOnlyImageRunner(self.image_pin)
        with patch(
            "oc2_slice_b_image_guest._supervisor_archive_identity",
            side_effect=((1, 2, 3, 4, 5), (1, 2, 3, 4, 6)),
        ), patch("oc2_slice_b_image_guest.verify_image_archive", return_value=None):
            with self.assertRaises(SliceBImageRejected):
                reverify_existing_guest_image(self.image_request(runner), runner)
        self.assertNotIn("load", runner.calls)

    def test_guest_authority_checks_receipt_and_clean_guest_baseline_twice(self) -> None:
        receipt_path = create_session_receipt(self.state, self.rec, self.art)
        baseline = import_guest_baseline(
            self.art,
            self.guest,
            expected_manifest_sha256=self.art.manifest_sha256,
            expected_key=self.key,
            expected_runtime_sha256=self.art.runtime_sha256,
        )
        runner = ReadOnlyImageRunner(self.image_pin)
        request = ExistingGuestAuthorityVerificationRequest(
            receipt_path=receipt_path,
            expected_key=self.key,
            expected_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            guest_baseline=baseline,
            archive_path=self.image_archive,
            supervisor_image_root=self.image_control,
            docker_host=runner.docker_host,
            expected_docker_daemon_id="a" * 64,
        )
        with patch("oc2_slice_b_session.admit_clean_repo", wraps=admit_clean_repo) as admit:
            authority = verify_guest_authority_from_existing_image(request, runner)
        self.assertEqual(admit.call_count, 2)
        self.assertTrue(authority.image_authority)

    def test_guest_authority_rejects_non_pristine_guest_baseline(self) -> None:
        receipt_path = create_session_receipt(self.state, self.rec, self.art)
        baseline = import_guest_baseline(
            self.art,
            self.guest,
            expected_manifest_sha256=self.art.manifest_sha256,
            expected_key=self.key,
            expected_runtime_sha256=self.art.runtime_sha256,
        )
        baseline = replace(baseline, head_oid="f" * 40)
        runner = ReadOnlyImageRunner(self.image_pin)
        request = ExistingGuestAuthorityVerificationRequest(
            receipt_path=receipt_path,
            expected_key=self.key,
            expected_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            guest_baseline=baseline,
            archive_path=self.image_archive,
            supervisor_image_root=self.image_control,
            docker_host=runner.docker_host,
            expected_docker_daemon_id="a" * 64,
        )
        with patch("oc2_slice_b_session.admit_clean_repo", return_value=baseline):
            with self.assertRaises(SliceBSessionError):
                verify_guest_authority_from_existing_image(request, runner)

    def test_guest_authority_rejects_baseline_change_during_image_check(self) -> None:
        receipt_path = create_session_receipt(self.state, self.rec, self.art)
        baseline = import_guest_baseline(
            self.art,
            self.guest,
            expected_manifest_sha256=self.art.manifest_sha256,
            expected_key=self.key,
            expected_runtime_sha256=self.art.runtime_sha256,
        )
        runner = ReadOnlyImageRunner(self.image_pin)
        request = ExistingGuestAuthorityVerificationRequest(
            receipt_path=receipt_path,
            expected_key=self.key,
            expected_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            guest_baseline=baseline,
            archive_path=self.image_archive,
            supervisor_image_root=self.image_control,
            docker_host=runner.docker_host,
            expected_docker_daemon_id="a" * 64,
        )
        changed = replace(baseline, head_oid="f" * 40)
        with patch(
            "oc2_slice_b_session.admit_clean_repo", side_effect=(baseline, changed)
        ):
            with self.assertRaises(SliceBSessionError):
                verify_guest_authority_from_existing_image(request, runner)
        self.assertIn("inspect", runner.calls)
