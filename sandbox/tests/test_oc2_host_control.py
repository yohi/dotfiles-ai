from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from typing import TYPE_CHECKING, final

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    from sandbox.tests.oc2_host_lifecycle_test_support import HostFixture
else:
    import oc2_host_control as hc
    from oc2_host_lifecycle_test_support import HostFixture


@final
class HostIsolationGateTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: HostFixture = HostFixture.create(Path(temporary.name))

    def evaluate(self, after: hc.HostObservation) -> hc.HostIsolationResult:
        f = self.fixture
        return hc.verify_host_isolation(
            f.host_identity,
            hc.HostStopObservations(f.observation(), f.observation(), after),
        )

    def test_complete_host_stop_observations_verify_isolation(self) -> None:
        result = self.evaluate(self.fixture.observation(stopped=True))

        self.assertTrue(result.vm_stopped_observed)
        self.assertTrue(result.verified)
        self.assertEqual(result.failures, ())

    def test_qemu_residual_and_pid_reuse_are_rejected(self) -> None:
        qemu_residual = self.evaluate(self.fixture.observation())
        reused = self.evaluate(replace(
            self.fixture.observation(stopped=True), expected_pid_start_ticks=54321,
        ))

        self.assertFalse(qemu_residual.verified)
        self.assertIn(hc.HostFailureCode.VM_STATE_UNEXPECTED, qemu_residual.failures)
        self.assertIn(hc.HostFailureCode.QEMU_REMAINS, qemu_residual.failures)
        self.assertIn(hc.HostFailureCode.PID_REUSED_OR_UNKNOWN, reused.failures)

    def test_qemu_command_identity_must_match_the_fixed_vm(self) -> None:
        f = self.fixture
        changed_process = replace(f.qemu, argv_sha256='d' * 64)
        changed = replace(f.observation(), qemu_process=changed_process)
        result = hc.verify_host_isolation(
            f.host_identity,
            hc.HostStopObservations(changed, changed, f.observation(stopped=True)),
        )

        self.assertIn(hc.HostFailureCode.QEMU_IDENTITY_MISMATCH, result.failures)

    def test_incomplete_kernel_inventory_is_unverified(self) -> None:
        result = self.evaluate(replace(
            self.fixture.observation(stopped=True),
            qemu_inventory_complete=None,
            disk_openers_complete=None,
            expected_pid_observation_complete=None,
        ))

        self.assertFalse(result.verified)
        self.assertIn(hc.HostFailureCode.QEMU_INVENTORY_INCOMPLETE, result.failures)
        self.assertIn(hc.HostFailureCode.DISK_OPENERS_UNKNOWN, result.failures)
        self.assertIn(hc.HostFailureCode.PID_REUSED_OR_UNKNOWN, result.failures)

    def test_disk_opener_or_shared_writer_blocks_isolation(self) -> None:
        opener = hc.HostProcessReference(902, 67890)
        with_opener = self.evaluate(replace(
            self.fixture.observation(stopped=True), disk_openers=(opener,),
        ))
        with_shared_write = self.evaluate(replace(
            self.fixture.observation(stopped=True), shared_write_possible=True,
        ))

        self.assertIn(hc.HostFailureCode.DISK_OPENERS_PRESENT, with_opener.failures)
        self.assertIn(hc.HostFailureCode.SHARED_WRITE_POSSIBLE, with_shared_write.failures)

    def test_unknown_shared_write_and_autostart_state_are_unverified(self) -> None:
        shared_unknown = self.evaluate(replace(
            self.fixture.observation(stopped=True), shared_write_possible=None,
        ))
        autostart_unknown = self.evaluate(replace(
            self.fixture.observation(stopped=True),
            autostart_policy=hc.AutostartPolicy.UNKNOWN,
        ))

        self.assertIn(hc.HostFailureCode.SHARED_WRITE_UNKNOWN, shared_unknown.failures)
        self.assertIn(hc.HostFailureCode.AUTOSTART_NOT_DISABLED,
                      autostart_unknown.failures)

    def test_unknown_continuous_controls_allow_identity_preflight_only(self) -> None:
        f = self.fixture
        preflight = replace(
            f.observation(), autostart_policy=hc.AutostartPolicy.UNKNOWN,
            restart_audit_complete=False, shared_write_possible=None,
            shared_write_scope_complete=False,
        )
        stopped = replace(
            f.observation(stopped=True), autostart_policy=hc.AutostartPolicy.UNKNOWN,
            restart_audit_complete=False, shared_write_possible=None,
            shared_write_scope_complete=False,
        )

        failures = hc.verify_host_running(f.host_identity, preflight)
        isolation = hc.verify_host_isolation(
            f.host_identity, hc.HostStopObservations(preflight, preflight, stopped),
        )

        self.assertEqual(failures, ())
        self.assertFalse(isolation.verified)
        self.assertIn(hc.HostFailureCode.AUTOSTART_NOT_DISABLED, isolation.failures)
        self.assertIn(hc.HostFailureCode.RESTART_AUDIT_INCOMPLETE, isolation.failures)
        self.assertIn(hc.HostFailureCode.SHARED_WRITE_UNKNOWN, isolation.failures)

    def test_disk_identity_ssh_and_restart_changes_fail_closed(self) -> None:
        f = self.fixture
        disk_changed = self.evaluate(replace(
            f.observation(stopped=True), disk=hc.HostDiskIdentity(
                f.disk.path, f.disk.device, f.disk.inode + 1,
            ),
        ))
        ssh_remains = self.evaluate(replace(
            f.observation(stopped=True), ssh_forward_listener_present=True,
        ))
        restarted = self.evaluate(replace(
            f.observation(stopped=True), restart_epoch=5,
        ))

        self.assertIn(hc.HostFailureCode.DISK_IDENTITY_MISMATCH, disk_changed.failures)
        self.assertIn(hc.HostFailureCode.SSH_FORWARD_PRESENT, ssh_remains.failures)
        self.assertIn(hc.HostFailureCode.VM_RESTARTED, restarted.failures)

    def test_missing_pre_stop_forward_is_distinct_from_listener_remaining(self) -> None:
        f = self.fixture
        initial = replace(f.observation(), ssh_forward_listener_present=False)
        result = hc.verify_host_isolation(
            f.host_identity,
            hc.HostStopObservations(initial, initial, f.observation(stopped=True)),
        )

        self.assertIn(hc.HostFailureCode.SSH_FORWARD_ABSENT, result.failures)

    def test_observed_forward_endpoint_must_match_fixed_host_and_port(self) -> None:
        f = self.fixture
        observed = replace(f.observation(), ssh_forward_port=2224)
        failures = hc.verify_host_running(f.host_identity, observed)

        self.assertIn(hc.HostFailureCode.SSH_FORWARD_IDENTITY_MISMATCH, failures)
