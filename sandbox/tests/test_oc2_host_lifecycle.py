from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from typing import TYPE_CHECKING, final
from unittest import mock

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_lifecycle as lifecycle
    import sandbox.scripts.oc2_offline_preservation as op
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_supervisor import SupervisorState
    from sandbox.tests.oc2_host_lifecycle_test_support import (
        FakeGuestStopper,
        FakeHostControl,
        FakePreserver,
        HostFixture,
    )
else:
    import oc2_host_lifecycle as lifecycle
    import oc2_offline_preservation as op
    import oc2_writer as w
    from oc2_host_lifecycle_test_support import (
        FakeGuestStopper,
        FakeHostControl,
        FakePreserver,
        HostFixture,
    )
    from oc2_supervisor import SupervisorState


@final
class HostControlledLifecycleTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: HostFixture = HostFixture.create(Path(temporary.name))

    def test_coordinator_stops_guest_then_host_then_preserves(self) -> None:
        f = self.fixture
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        host = FakeHostControl((f.observation(), f.observation(),
                                f.observation(stopped=True)), events)
        preserver = FakePreserver(f.preservation_evidence(), events)
        request = lifecycle.HostControlledStopRequest(
            guest, f.authority, f.writer, f.host_identity, host, preserver,
        )

        result = lifecycle.coordinate_host_controlled_stop(request)

        self.assertEqual(events, [
            'host.observe', 'guest.stop', 'host.observe', 'host.shutdown',
            'host.wait', 'preserve',
        ])
        self.assertIn(lifecycle.HostLifecycleStage.GUEST_QUIESCENCE_VERIFIED,
                      result.stages)
        self.assertIn(lifecycle.HostLifecycleStage.VM_ISOLATION_VERIFIED,
                      result.stages)
        if result.preservation is None:
            self.fail('preservation decision missing')
        self.assertEqual(result.preservation.disposition.value, 'verified')

    def test_coordinator_resumes_from_verified_guest_stop_without_reissuing_shutdown(self) -> None:
        """Resume isolation and preservation after a verified Writer stop."""
        f = self.fixture
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        guest.state = SupervisorState.STOPPED_VERIFIED
        host = FakeHostControl((
            f.observation(stopped=True), f.observation(stopped=True),
            f.observation(stopped=True),
        ), events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, host, preserver,
            )
        )

        self.assertEqual(events, ['host.observe', 'host.observe', 'host.wait', 'preserve'])
        self.assertIn(lifecycle.HostLifecycleStage.VM_ISOLATION_VERIFIED, result.stages)
        self.assertEqual(result.failures, ())

    def test_coordinator_retries_shutdown_when_resumed_guest_vm_is_running(self) -> None:
        f = self.fixture
        request, events, guest = f.make_request((
            f.observation(), f.observation(), f.observation(stopped=True),
        ))
        guest.state = SupervisorState.STOPPED_VERIFIED

        result = lifecycle.coordinate_host_controlled_stop(request)

        self.assertEqual(events, [
            'host.observe', 'host.observe', 'host.shutdown', 'host.wait', 'preserve',
        ])
        self.assertEqual(result.failures, ())
        self.assertIn(lifecycle.HostLifecycleStage.VM_ISOLATION_VERIFIED, result.stages)

    def test_host_identity_mismatch_stops_before_guest_stop(self) -> None:
        f = self.fixture
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        host = FakeHostControl((replace(f.observation(), vm_id='foreign'),), events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, host, preserver,
            )
        )

        self.assertEqual(events, ['host.observe'])
        self.assertIsNone(result.guest_verdict)
        self.assertNotIn(lifecycle.HostLifecycleStage.VM_STOP_REQUESTED, result.stages)

    def test_guest_unverified_status_is_preserved_separately(self) -> None:
        f = self.fixture
        events: list[str] = []
        verdict = w.StopVerdict(w.STATUS_GUEST_QUIESCENCE_UNVERIFIED,
                                ('rw mount holders unknown',))
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events,
                                 stop_verdict=verdict)
        host = FakeHostControl((f.observation(), f.observation(),
                                f.observation(stopped=True)), events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, host, preserver,
            )
        )

        self.assertIn(lifecycle.HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED,
                      result.stages)
        self.assertNotIn(lifecycle.HostLifecycleStage.GUEST_QUIESCENCE_VERIFIED,
                         result.stages)
        if result.guest_verdict is None:
            self.fail('Guest stop verdict missing')
        self.assertFalse(result.guest_verdict.verified)
        self.assertIs(guest.state, SupervisorState.UNVERIFIED)
        self.assertIn(lifecycle.HostLifecycleStage.VM_ISOLATION_VERIFIED,
                      result.stages)

    def test_conditionally_accepted_preservation_has_distinct_stage(self) -> None:
        f = self.fixture
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        host = FakeHostControl((f.observation(), f.observation(),
                                f.observation(stopped=True)), events)
        preserver = FakePreserver(f.preservation_evidence(), events)
        decision = op.PreservationDecision(
            op.PreservationDisposition.CONDITIONALLY_ACCEPTED,
            (op.PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,),
        )

        with mock.patch.object(lifecycle, 'evaluate_offline_preservation',
                               return_value=decision):
            result = lifecycle.coordinate_host_controlled_stop(
                lifecycle.HostControlledStopRequest(
                    guest, f.authority, f.writer, f.host_identity, host, preserver,
                )
            )

        self.assertIn(lifecycle.HostLifecycleStage.OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED,
                      result.stages)
        self.assertNotIn(lifecycle.HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED,
                         result.stages)

    def test_vm_shutdown_request_failure_has_no_force_fallback(self) -> None:
        f = self.fixture
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        host = FakeHostControl((f.observation(), f.observation()), events,
                               request_ok=False)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, host, preserver,
            )
        )

        self.assertIn(lifecycle.LifecycleFailure.VM_SHUTDOWN_REQUEST_FAILED,
                      result.failures)
        self.assertEqual(events, [
            'host.observe', 'guest.stop', 'host.observe', 'host.shutdown',
        ])

    def test_authority_from_another_session_blocks_all_operations(self) -> None:
        f = self.fixture
        other_root = f.root / 'foreign'
        other_root.mkdir(mode=0o700)
        other = HostFixture.create(other_root)
        authority = other.authority
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        host = FakeHostControl((), events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        self.assertNotEqual(other.key, f.key)
        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, authority, f.writer, f.host_identity, host, preserver,
            )
        )

        self.assertIn(lifecycle.LifecycleFailure.SESSION_AUTHORITY_MISMATCH,
                      result.failures)
        self.assertEqual(events, [])
