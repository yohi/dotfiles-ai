from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, cast
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_lifecycle as lifecycle
    from sandbox.scripts.oc2_host_lifecycle import (
        HostControlledStopRequest as HostControlledStopRequestType,
        HostControlledStopResult as HostControlledStopResultType,
    )
    from sandbox.scripts.oc2_host_control import HostVmIdentity as HostVmIdentityType
    import sandbox.scripts.oc2_slice_b as adapter
    import sandbox.scripts.oc2_slice_b_git as git
    import sandbox.scripts.oc2_slice_b_image as image  # noqa: F401
    import sandbox.scripts.oc2_slice_b_session as session
    import sandbox.oc2_slice_b.offline_fixture as offline_fixture
    from sandbox.scripts.oc2_slice_b import (
        SliceBOfflineInputs as SliceBOfflineInputsType,
        SliceBOfflineOutcome as SliceBOfflineOutcomeType,
        SliceBStartMessage as SliceBStartMessageType,
        SliceBWriterObservation as SliceBWriterObservationType,
    )
    from sandbox.scripts.oc2_slice_b_git import GitBaseline
    from sandbox.scripts.oc2_slice_b_image import ImagePin as ImagePinType
    from sandbox.scripts.oc2_slice_b_session import VerifiedGuestAuthority
    from sandbox.scripts.oc2_writer import (
        StopVerdict as WriterStopVerdictType,
        WriterIdentity as WriterIdentityType,
        WriterSessionKey as WriterSessionKeyType,
    )
    from sandbox.tests.oc2_slice_b_test_support import (
        FakeGuestImageRunner as FakeGuestImageRunnerType,
        make_key,  # noqa: F401
    )
    from sandbox.tests.oc2_host_lifecycle_test_support import (
        FakeGuestStopper as FakeGuestStopperType,
        FakeHostControl as FakeHostControlType,
        FakePreserver as FakePreserverType,
        HostFixture as HostFixtureType,
    )
    from sandbox.scripts.oc2_host_control import HostObservation as HostObservationType

    FakeGuestImageRunnerRuntime: type[FakeGuestImageRunnerType]
    FakeGuestStopperRuntime: type[FakeGuestStopperType]
    FakeHostControlRuntime: type[FakeHostControlType]
    FakePreserverRuntime: type[FakePreserverType]
    HostFixtureRuntime: type[HostFixtureType]
    SliceBOfflineInputsRuntime: type[SliceBOfflineInputsType]
    SliceBWriterObservationRuntime: type[SliceBWriterObservationType]
    HostControlledStopRequestRuntime: type[HostControlledStopRequestType]
    StopRequestRuntime: type[HostControlledStopRequestType]
    HostVmIdentityRuntime: type[HostVmIdentityType]
    WriterIdentityRuntime: type[WriterIdentityType]
    WriterStopVerdictRuntime: type[WriterStopVerdictType]
    WriterGuestUnverifiedRuntime: str
    run_slice_b: Callable[..., int]
    op: ModuleType

def git_run(root: Path, *args: str) -> str:
    env = {
        "PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null", "GIT_CONFIG_KEY_1": "commit.gpgSign",
        "GIT_CONFIG_VALUE_1": "false", "GIT_CONFIG_KEY_2": "core.fsmonitor",
        "GIT_CONFIG_VALUE_2": "false",
    }
    result = subprocess.run(["git", "-C", str(root), *args], env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, check=True)
    return result.stdout.decode().strip()


@dataclass
class Scenario:
    root: Path
    host: Path
    guest: Path
    key: WriterSessionKeyType
    pin: ImagePinType
    archive: Path
    bundle: Path
    state: Path
    runtime: str


class FakeOps:
    def __init__(self, s: Scenario, mode: str = "success") -> None:
        self.s: Scenario = s
        self.mode: str = mode
        self.writer_calls: int = 0
        self.recorded: list[tuple[str, str | None, object | None]] = []
        self.events: list[str] = []
        self.observation: SliceBWriterObservationType | None = None
        self.pre_writer_guest: GitBaseline | None = None
        self.stop_identity: WriterIdentityType | None = None
        self.authority_seen: VerifiedGuestAuthority | None = None
        self.start_seen: Any = None
        self.runner: FakeGuestImageRunnerType = FakeGuestImageRunnerRuntime(s.pin)
        self.key: WriterSessionKeyType = s.key
        self.lifecycle_events: list[str] = []
        self.real_infrastructure_calls: list[str] = []

    def inputs(self, baseline: GitBaseline, sandbox_name: str) -> SliceBOfflineInputsType:
        self.events.append("inputs")
        values = SliceBOfflineInputsRuntime(
            self.key, self.s.runtime, self.s.pin, self.s.archive,
            self.s.root / "image-control", "unix:///var/run/docker.sock",
            self.s.state, self.s.bundle, self.s.guest, self.runner,
        )
        from dataclasses import replace
        if self.mode == "overlap":
            return replace(values, guest_repo_path=self.s.host)
        if self.mode == "drift-runtime":
            return replace(values, runtime_sha256="e" * 64)
        return values

    def run_writer(
        self, authority: VerifiedGuestAuthority, start: SliceBStartMessageType,
        guest_repo: Path,
    ) -> SliceBWriterObservationType:
        self.writer_calls += 1
        self.events.append("writer")
        self.authority_seen = authority
        self.start_seen = start
        self.pre_writer_guest = git.admit_clean_repo(guest_repo)
        identity = WriterIdentityRuntime("a" * 64, authority.image_config_id,
                                         "2026-11-21T12:00:00Z", 123, "boot-id")
        if self.mode == "bad-cid":
            identity = WriterIdentityRuntime("a", identity.image_id, identity.started_at,
                                             123, "boot-id")
        if self.mode == "bad-image":
            identity = WriterIdentityRuntime(identity.container_id, "sha256:" + "f" * 64,
                                             identity.started_at, 123, "boot-id")
        if self.mode == "bad-time":
            identity = WriterIdentityRuntime(identity.container_id, identity.image_id,
                                             "0001-01-01T00:00:00Z", 123, "boot-id")
        if self.mode == "missing-time":
            identity = WriterIdentityRuntime(identity.container_id, identity.image_id,
                                          cast(str, cast(object, None)), 123, "boot-id")
        if self.mode == "invalid-time":
            identity = WriterIdentityRuntime(identity.container_id, identity.image_id,
                                             "not-a-date", 123, "boot-id")
        if self.mode == "bad-tui":
            self.observation = SliceBWriterObservationRuntime(identity, 1, None)
            assert self.observation is not None
            return self.observation
        commit = offline_fixture.run_offline_fixture(guest_repo, start.head_oid, start.branch_ref)
        self.observation = SliceBWriterObservationRuntime(
            identity, 0, commit,
        )
        if self.mode == "bad-fixture":
            commit = git_run(guest_repo, "rev-parse", "HEAD^:")
            self.observation = SliceBWriterObservationRuntime(identity, 0, commit)
        assert self.observation is not None
        return self.observation

    def stop_request(
        self, authority: VerifiedGuestAuthority, writer: WriterIdentityType,
    ) -> HostControlledStopRequestType:
        self.events.append("stop")
        if self.mode == "changed-time":
            writer = WriterIdentityRuntime(
                writer.container_id, writer.image_id, "2026-11-21T12:00:01Z",
                writer.cgroup_inode, writer.boot_id,
            )
        self.stop_identity = writer
        host_fixture_root = self.s.root / "host-fixture"
        host_fixture_root.mkdir()
        fixture = HostFixtureRuntime.create(host_fixture_root)
        baseline = authority.manifest.baseline
        evidence = replace(
            fixture.preservation_evidence(), session_key=authority.key,
            receipt_sha256=authority.receipt_sha256,
            manifest_sha256=authority.manifest_sha256,
            branch_ref=baseline.branch_ref, head_oid=baseline.head_oid,
            tree_oid=baseline.tree_oid, object_format=baseline.object_format,
            index_sha256=baseline.index_sha256,
            worktree_sha256=baseline.worktree_sha256,
        )
        if self.mode == "preservation-unknown":
            evidence = replace(evidence, filesystem_state=op.FilesystemState.UNKNOWN)
        if self.mode == "digest-mismatch":
            evidence = replace(evidence, source_sha256="f" * 64)
        host_identity = HostVmIdentityRuntime(
            fixture.host_identity.vm_id, fixture.host_identity.vm_name,
            fixture.host_identity.host_boot_id, fixture.qemu, fixture.disk,
            authority.key, fixture.host_identity.ssh_forward_host,
            fixture.host_identity.ssh_forward_port,
        )
        observations: tuple[
            HostObservationType | None, HostObservationType | None, HostObservationType | None,
        ] = (fixture.observation(), fixture.observation(),
             fixture.observation(stopped=True))
        if self.mode == "restart-epoch-drift":
            observations = (observations[0], replace(fixture.observation(), restart_epoch=5),
                            observations[2])
        if self.mode == "isolation-unknown":
            observations = (observations[0], observations[1], None)
        stopper = FakeGuestStopperRuntime(
            authority.key, writer, authority, self.lifecycle_events,
            stop_verdict=(WriterStopVerdictRuntime(
                WriterGuestUnverifiedRuntime, ("stop not proven",),
            ) if self.mode in {"guest-unverified", "guest-unverified-mismatch"} else None),
        )
        host = FakeHostControlRuntime(observations, self.lifecycle_events)
        preserver = FakePreserverRuntime(evidence, self.lifecycle_events)
        return HostControlledStopRequestRuntime(
            stopper, authority, writer, host_identity, host, preserver,
        )

    def record_result(
        self, outcome: SliceBOfflineOutcomeType, reason: str | None, result: object | None,
    ) -> None:
        self.recorded.append((outcome, reason, result))


class SliceBAdapterTests(unittest.TestCase):
    tmp: tempfile.TemporaryDirectory[str] = cast(
        tempfile.TemporaryDirectory[str], cast(object, None),
    )
    s: Scenario = cast(Scenario, cast(object, None))
    _last_lifecycle_result: HostControlledStopResultType | None = None

    def setUp(self):
        global adapter, git, image, lifecycle, offline_fixture, session
        global FakeGuestImageRunnerRuntime, SliceBOfflineInputsRuntime
        global SliceBWriterObservationRuntime, StopRequestRuntime
        global WriterIdentityRuntime, make_key, run_slice_b
        global HostFixtureRuntime, FakeGuestStopperRuntime, FakeHostControlRuntime
        global FakePreserverRuntime, HostVmIdentityRuntime, HostControlledStopRequestRuntime
        global WriterStopVerdictRuntime, WriterGuestUnverifiedRuntime, op
        from importlib import import_module
        adapter = import_module("oc2_slice_b")
        lifecycle = import_module("oc2_host_lifecycle")
        StopRequestRuntime = lifecycle.HostControlledStopRequest
        HostControlledStopRequestRuntime = lifecycle.HostControlledStopRequest
        host_control = import_module("oc2_host_control")
        op = import_module("oc2_offline_preservation")
        support = import_module("oc2_host_lifecycle_test_support")
        HostFixtureRuntime = support.HostFixture
        FakeGuestStopperRuntime = support.FakeGuestStopper
        FakeHostControlRuntime = support.FakeHostControl
        FakePreserverRuntime = support.FakePreserver
        HostVmIdentityRuntime = host_control.HostVmIdentity
        writer_module = import_module("oc2_writer")
        WriterStopVerdictRuntime = writer_module.StopVerdict
        WriterGuestUnverifiedRuntime = writer_module.STATUS_GUEST_QUIESCENCE_UNVERIFIED
        git = import_module("oc2_slice_b_git")
        image = import_module("oc2_slice_b_image")
        session = import_module("oc2_slice_b_session")
        support = import_module("oc2_slice_b_test_support")
        from sandbox.oc2_slice_b import offline_fixture
        FakeGuestImageRunnerRuntime = support.FakeGuestImageRunner
        make_key = support.make_key
        WriterIdentityRuntime = import_module("oc2_writer").WriterIdentity
        SliceBOfflineInputsRuntime = adapter.SliceBOfflineInputs
        SliceBWriterObservationRuntime = adapter.SliceBWriterObservation
        run_slice_b = adapter.run_slice_b

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        host = root / "host"
        host.mkdir()
        git_run(host, "init", "-b", "main")
        git_run(host, "config", "user.name", "Fixture")
        git_run(host, "config", "user.email", "fixture@example.invalid")
        (host / "source.txt").write_text("baseline\n")
        git_run(host, "add", "source.txt")
        git_run(host, "commit", "-m", "baseline")
        runtime = "b" * 64
        archive_bytes = b"offline test image archive"
        control = root / "image-control"
        control.mkdir(mode=0o700)
        pin = image.ImagePin(
            "f" * 40, "c" * 64, runtime, "alpine@sha256:" + "d" * 64,
            "1" * 64, "2" * 64, None, "sha256:" + "e" * 64,
            hashlib.sha256(archive_bytes).hexdigest(), len(archive_bytes), "linux/amd64",
        )
        archive = control / (pin.archive_sha256 + ".tar")
        archive.write_bytes(archive_bytes)
        archive.chmod(0o600)
        self.s = Scenario(root, host, root / "guest", make_key(), pin, archive,
                          root / "bundle.bundle", root / "state", runtime)

    def test_imported_guest_git_and_verified_authority_reach_same_writer(self):
        ops = FakeOps(self.s)
        host_before = git.admit_clean_repo(self.s.host)
        status = run_slice_b(self.s.root, self.s.host, "oc2-offline-test",
                             dry_run=False, ops=ops)
        self.assertEqual(status, 0)
        self.assertEqual(ops.writer_calls, 1)
        assert ops.pre_writer_guest is not None
        assert ops.observation is not None
        assert ops.stop_identity is not None
        assert ops.authority_seen is not None
        assert ops.start_seen is not None
        outcome, reason, _ = ops.recorded[-1]
        self.assertEqual((outcome, reason), ("OFFLINE_FAKE_PASS", None))
        guest = git.admit_clean_repo(self.s.guest)
        self.assertEqual(ops.pre_writer_guest.head_oid, host_before.head_oid)
        self.assertEqual(ops.pre_writer_guest.tree_oid, host_before.tree_oid)
        self.assertEqual(ops.pre_writer_guest.branch_ref, host_before.branch_ref)
        self.assertRegex(ops.pre_writer_guest.index_sha256, r"[0-9a-f]{64}")
        self.assertNotEqual(ops.pre_writer_guest.root, host_before.root)
        self.assertEqual(guest.head_oid, ops.observation.fixture_commit_oid)
        self.assertEqual(git_run(self.s.guest, "rev-list", "--parents", "-n", "1", "HEAD").split()[1],
                         host_before.head_oid)
        self.assertEqual((self.s.guest / offline_fixture.FIXTURE_NAME).read_bytes(),
                         offline_fixture.FIXTURE_BYTES)
        assert ops.stop_identity is not None
        assert ops.observation is not None
        self.assertEqual(ops.stop_identity, ops.observation.identity)
        self.assertEqual(ops.stop_identity.container_id, "a" * 64)
        self.assertEqual(ops.stop_identity.image_id, self.s.pin.config_id)
        self.assertEqual(ops.stop_identity.started_at, "2026-11-21T12:00:00Z")
        self.assertEqual(ops.authority_seen.manifest.baseline.head_oid, host_before.head_oid)
        self.assertEqual(ops.authority_seen.key, self.s.key)
        self.assertEqual(ops.start_seen.head_oid, host_before.head_oid)
        receipt_path = (self.s.state / self.s.key.workspace_id /
                        self.s.key.session_generation / "receipt.json")
        verified_receipt = session.verify_session_receipt(
            receipt_path, self.s.key, hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(verified_receipt.receipt.state, "PENDING")
        self.assertEqual(verified_receipt.receipt.reason, "NOT_RUN")
        self.assertIsNone(verified_receipt.receipt.writer_id)
        self.assertIsNone(verified_receipt.receipt.started_at)
        self.assertEqual(verified_receipt.receipt.baseline, host_before)
        self.assertEqual(git.admit_clean_repo(self.s.host), host_before)
        self.assertEqual(ops.events, ["inputs", "writer", "stop"])
        self.assertEqual(ops.lifecycle_events,
                         ["host.observe", "guest.stop", "host.observe", "host.shutdown",
                          "host.wait", "preserve"])

    def test_dirty_or_changed_host_rejected_before_writer(self):
        (self.s.host / "dirty.txt").write_text("dirty")
        ops = FakeOps(self.s)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_guest_path_already_exists_or_overlaps_host_rejected(self):
        self.s.guest.mkdir()
        ops = FakeOps(self.s)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_guest_path_overlapping_host_rejected(self):
        ops = FakeOps(self.s)
        ops.mode = "overlap"
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_writer_identity_or_tui_failure_preserves_guest(self):
        ops = FakeOps(self.s, "bad-tui")
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.recorded[-1][:2], ("REJECTED", "OBSERVED_MISMATCH"))
        self.assertEqual(ops.writer_calls, 1)
        self.assertFalse((self.s.guest / offline_fixture.FIXTURE_NAME).exists())

    def test_writer_image_id_differs_from_authority_rejected(self):
        self._assert_writer_rejected("bad-image")

    def test_writer_invalid_full_cid_rejected(self):
        self._assert_writer_rejected("bad-cid")

    def test_writer_invalid_or_changed_started_at_rejected(self):
        for mode in ("bad-time", "missing-time", "invalid-time", "changed-time"):
            with self.subTest(mode=mode):
                self._reset_fixture()
                self._assert_writer_rejected(mode)

    def test_wrong_fixture_commit_rejected(self):
        self._assert_writer_rejected("bad-fixture")

    def test_fake_host_stop_order_and_zero_real_infrastructure_calls(self):
        ops = FakeOps(self.s)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "offline", dry_run=False, ops=ops), 0)
        self.assertEqual(ops.recorded[-1][:2], ("OFFLINE_FAKE_PASS", None))
        result = cast("HostControlledStopResultType", ops.recorded[-1][2])
        self.assertEqual(result.failures, ())
        assert result.guest_verdict is not None
        assert result.host_isolation is not None
        self.assertTrue(result.guest_verdict.verified)
        self.assertTrue(result.host_isolation.verified)
        self.assertEqual(
            [stage.value for stage in result.stages],
            ["WRITER_STOP_REQUESTED", "GUEST_QUIESCENCE_VERIFIED", "VM_STOP_REQUESTED",
             "VM_STOPPED_OBSERVED", "VM_ISOLATION_VERIFIED", "OFFLINE_PRESERVATION_VERIFIED"],
        )
        self.assertEqual(ops.lifecycle_events,
                         ["host.observe", "guest.stop", "host.observe", "host.shutdown",
                          "host.wait", "preserve"])
        self.assertEqual(ops.real_infrastructure_calls, [])
        self.assertEqual(len(ops.recorded), 1)
        assert ops.stop_identity is not None
        assert ops.observation is not None
        self.assertEqual(ops.stop_identity, ops.observation.identity)
        receipt_path = (self.s.state / self.s.key.workspace_id /
                        self.s.key.session_generation / "receipt.json")
        saved = session.verify_session_receipt(
            receipt_path, self.s.key, hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        ).receipt
        self.assertEqual(saved.state, "PENDING")
        self.assertNotEqual(saved.state, "OFFLINE_FAKE_PASS")

    def test_guest_stop_unverified_is_pending_despite_later_success(self):
        self._assert_lifecycle_outcome("guest-unverified", "PENDING",
                                       "GUEST_QUIESCENCE_UNVERIFIED")
        result = self._get_lifecycle_result()
        self.assertIn(lifecycle.LifecycleFailure.GUEST_STOP_UNVERIFIED, result.failures)
        self.assertIn(lifecycle.HostLifecycleStage.VM_ISOLATION_VERIFIED, result.stages)
        self.assertIn(lifecycle.HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED, result.stages)

    def test_guest_quiescence_unverified_precedes_preservation_mismatch(self):
        decision = op.PreservationDecision(
            op.PreservationDisposition.MISMATCH,
            (op.PreservationFailure.COPY_INTEGRITY_MISMATCH,),
        )
        with patch.object(lifecycle, "evaluate_offline_preservation", return_value=decision):
            self._assert_lifecycle_outcome("guest-unverified-mismatch", "PENDING",
                                           "GUEST_QUIESCENCE_UNVERIFIED")

    def test_restart_epoch_drift_or_isolation_unknown_not_success(self):
        self._assert_lifecycle_outcome("restart-epoch-drift", "PENDING",
                                       "GUEST_QUIESCENCE_UNVERIFIED")
        self._reset_fixture()
        self._assert_lifecycle_outcome("isolation-unknown", "PENDING",
                                       "HOST_ISOLATION_UNVERIFIED")
        result = self._get_lifecycle_result()
        assert result.host_isolation is not None
        self.assertFalse(result.host_isolation.verified)

    def test_preservation_readback_unknown_remains_unverified(self):
        self._assert_lifecycle_outcome("preservation-unknown", "PRESERVATION_UNVERIFIED",
                                       "PRESERVATION_UNVERIFIED")
        self.assertEqual(self._get_lifecycle_result().failures,
                         (lifecycle.LifecycleFailure.PRESERVATION_UNVERIFIED,))

    def test_conditionally_accepted_preservation_never_passes_even_without_failures(self):
        decision = op.PreservationDecision(
            op.PreservationDisposition.CONDITIONALLY_ACCEPTED,
            (op.PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,),
        )
        with patch.object(lifecycle, "evaluate_offline_preservation", return_value=decision):
            self._assert_lifecycle_outcome("success", "PRESERVATION_UNVERIFIED",
                                           "PRESERVATION_UNVERIFIED")
        result = self._get_lifecycle_result()
        self.assertEqual(result.failures, ())
        self.assertIn(lifecycle.HostLifecycleStage.OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED,
                      result.stages)
        self.assertNotIn(lifecycle.HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED,
                         result.stages)

    def test_observed_digest_mismatch_is_rejected_not_unknown(self):
        self._assert_lifecycle_outcome("digest-mismatch", "REJECTED", "OBSERVED_MISMATCH")
        result = self._get_lifecycle_result()
        assert result.preservation is not None
        self.assertEqual(result.preservation.disposition,
                         op.PreservationDisposition.MISMATCH)

    def test_wrong_writer_image_id_never_reaches_fake_success(self):
        ops = FakeOps(self.s, "bad-image")
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "offline", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.recorded[-1][:2], ("REJECTED", "OBSERVED_MISMATCH"))
        self.assertEqual(ops.lifecycle_events, [])

    def test_fake_success_does_not_persist_receipt_success(self):
        ops = FakeOps(self.s)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "offline", dry_run=False, ops=ops), 0)
        receipt_path = (self.s.state / self.s.key.workspace_id /
                        self.s.key.session_generation / "receipt.json")
        saved = session.verify_session_receipt(
            receipt_path, self.s.key, hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        ).receipt
        self.assertEqual(saved.state, "PENDING")
        self.assertEqual(saved.reason, "NOT_RUN")
        self.assertIsNone(saved.writer_id)
        self.assertIsNone(saved.started_at)

    def _assert_lifecycle_outcome(self, mode, expected_outcome, expected_reason):
        ops = FakeOps(self.s, mode)
        self._last_lifecycle_result = None
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "offline", dry_run=False, ops=ops),
                         0 if expected_outcome == "OFFLINE_FAKE_PASS" else 1)
        self.assertEqual(ops.recorded[-1][:2], (expected_outcome, expected_reason))
        self.assertEqual(len(ops.recorded), 1)
        self._last_lifecycle_result = cast(
            "HostControlledStopResultType", ops.recorded[-1][2],
        )
        self.assertTrue(self.s.guest.exists())
        receipt_path = (self.s.state / self.s.key.workspace_id /
                        self.s.key.session_generation / "receipt.json")
        self.assertEqual(session.verify_session_receipt(
            receipt_path, self.s.key, hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        ).receipt.state, "PENDING")
        self.assertEqual(ops.real_infrastructure_calls, [])
        self.assertEqual(ops.events.count("writer"), 1)

    def _get_lifecycle_result(self) -> HostControlledStopResultType:
        assert self._last_lifecycle_result is not None
        return self._last_lifecycle_result

    def test_manifest_archive_runtime_or_config_id_drift_rejected(self):
        for drift in ("archive", "runtime", "image-record"):
            with self.subTest(drift=drift):
                self._reset_fixture()
                ops = FakeOps(self.s)
                if drift == "archive":
                    self.s.archive.write_bytes(b"tampered")
                elif drift == "runtime":
                    ops.mode = "drift-runtime"
                else:
                    with patch.object(ops.runner, "inspect_config_id",
                                      lambda config_id: {"Id": "sha256:" + "f" * 64}):
                        result = run_slice_b(self.s.root, self.s.host, "bad",
                                              dry_run=False, ops=ops)
                    self.assertEqual(result, 1)
                if drift != "image-record":
                    self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                                 dry_run=False, ops=ops), 1)
                self.assertEqual(ops.writer_calls, 0)
                self.assertEqual(ops.recorded[-1][:2],
                                 ("REJECTED", "OBSERVED_MISMATCH"))

    def test_unverified_guest_baseline_or_forged_authority_rejected(self):
        original = adapter.verify_guest_authority_from_host_record
        def forge(*args, **kwargs):
            original(*args, **kwargs)
            return object()
        with patch.object(adapter, "verify_guest_authority_from_host_record", side_effect=forge):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)
        self.assertEqual(ops.recorded[-1][:2], ("REJECTED", "OBSERVED_MISMATCH"))
        from dataclasses import replace
        original_import = adapter.import_guest_baseline
        def forge_baseline(*args, **kwargs):
            return replace(original_import(*args, **kwargs), head_oid="0" * 40)
        with patch.object(adapter, "import_guest_baseline", side_effect=forge_baseline):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)
        self.assertEqual(ops.recorded[-1][:2], ("REJECTED", "OBSERVED_MISMATCH"))

    def test_guest_mutated_after_import_rejected_before_authority(self):
        original = adapter.import_guest_baseline
        def mutate(*args, **kwargs):
            baseline = original(*args, **kwargs)
            (baseline.root / "source.txt").write_text("mutated\n")
            return baseline
        with patch.object(adapter, "import_guest_baseline", side_effect=mutate):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_guest_mutated_after_authority_rejected_before_writer(self):
        original = adapter.verify_guest_authority_from_host_record
        def mutate(*args, **kwargs):
            authority = original(*args, **kwargs)
            (self.s.guest / "source.txt").write_text("mutated\n")
            return authority
        with patch.object(adapter, "verify_guest_authority_from_host_record", side_effect=mutate):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_host_changed_after_authority_rejected_before_writer(self):
        original = adapter.verify_guest_authority_from_host_record
        def mutate(*args, **kwargs):
            authority = original(*args, **kwargs)
            (self.s.host / "source.txt").write_text("host changed\n")
            return authority
        with patch.object(adapter, "verify_guest_authority_from_host_record", side_effect=mutate):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_changed_manifest_rejected_before_guest_import(self):
        original = adapter.verify_bundle_manifest
        def tamper(artifact, **kwargs):
            artifact.manifest_path.write_bytes(artifact.manifest_path.read_bytes() + b" ")
            return original(artifact, **kwargs)
        with patch.object(adapter, "verify_bundle_manifest", side_effect=tamper):
            ops = FakeOps(self.s)
            self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad",
                                         dry_run=False, ops=ops), 1)
        self.assertEqual(ops.writer_calls, 0)

    def test_dry_run_exits_before_inputs(self):
        ops = FakeOps(self.s)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=True, ops=ops), 1)
        self.assertEqual(ops.events, [])

    def _assert_writer_rejected(self, mode):
        ops = FakeOps(self.s, mode)
        self.assertEqual(run_slice_b(self.s.root, self.s.host, "bad", dry_run=False, ops=ops), 1)
        self.assertEqual(ops.recorded[-1][:2], ("REJECTED", "OBSERVED_MISMATCH"))
        self.assertEqual(ops.writer_calls, 1)
        self.assertTrue(self.s.guest.exists())
        receipt_path = (self.s.state / self.s.key.workspace_id /
                        self.s.key.session_generation / "receipt.json")
        self.assertEqual(session.verify_session_receipt(
            receipt_path, self.s.key, hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        ).receipt.state, "PENDING")

    def _reset_fixture(self):
        self.setUp()


if __name__ == "__main__":
    unittest.main()
