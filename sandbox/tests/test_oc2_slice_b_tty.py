"""Fake-only tests for the Slice B interactive Writer boundary."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
import oc2_writer as w  # noqa: E402
import oc2_supervisor as sup  # noqa: E402
import test_oc2_writer as tw  # noqa: E402
import test_oc2_supervisor as ts  # noqa: E402


class SliceBTtyTests(unittest.TestCase):
    def test_attach_identity_mismatch(self) -> None:
        scenario = ts.TtyScenario()
        before = list(scenario.docker.calls)
        for identity in (
            replace(scenario.identity, container_id=tw.CID2),
            replace(scenario.identity, image_id="sha256:" + "f" * 64),
            replace(scenario.identity, started_at="2026-11-15T00:00:00Z"),
        ):
            with self.subTest(identity=identity):
                with self.assertRaises(sup.IdentityMismatchError):
                    scenario.supervisor.attach_writer(
                        identity, scenario.transport, scenario.authority,
                    )
        self.assertEqual(scenario.transport.events, [])
        self.assertEqual(scenario.docker.calls, before)

    def test_reject_short_id_and_unlisted_attach_shape(self) -> None:
        scenario = ts.TtyScenario()
        short = replace(scenario.identity, container_id=tw.CID[:12])
        with self.assertRaises(sup.IdentityMismatchError):
            scenario.supervisor.attach_writer(short, scenario.transport, scenario.authority)
        raw = ts.FakeTransport()
        with self.assertRaises(sup.DockerCommandRejected):
            ts.runner_for(raw).run(["docker", "attach", tw.CID], timeout=10)
        self.assertEqual(raw.calls, [])

    def test_attach_transport_failure_stops_and_preserves(self) -> None:
        scenario = ts.TtyScenario(fail_attach=True)
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertEqual(outcome.failure_code, "attach-transport")
        self.assertEqual(scenario.docker.verbs().count("create"), 1)
        self.assertEqual(scenario.docker.verbs().count("stop"), 1)
        self.assertEqual(scenario.events, [])
        self.assertFalse(
            any(event[1] == ts.tty_frame(ts.TTY_CONTROL, ts.TTY_CONTINUE)
                for event in scenario.transport.events if event[0] == "send")
        )
        self.assertIn(("restore", None), scenario.transport.events)

    def test_unverified_stop_never_reported_verified(self) -> None:
        scenario = ts.TtyScenario(
            fail_attach=True, probe=tw.FakeProbe(observations=[None, None]),
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertFalse(outcome.stop_verdict.verified)
        self.assertEqual(outcome.stop_verdict.status, w.STATUS_GUEST_QUIESCENCE_UNVERIFIED)
        self.assertIs(scenario.supervisor.state, sup.SupervisorState.UNVERIFIED)

    def test_attach_rejects_missing_or_tampered_authority(self) -> None:
        for mode in ("missing", "digest", "session-key"):
            scenario = ts.TtyScenario()
            if mode == "missing":
                authority = None
            elif mode == "digest":
                authority = replace(scenario.authority, manifest_sha256="0" * 64)
            else:
                authority = replace(scenario.authority, key=tw.make_key(tw.GEN2))
            with self.subTest(mode=mode):
                outcome = scenario.supervisor.attach_writer(
                    scenario.identity, scenario.transport, authority,
                )
                self.assertIsNotNone(outcome.failure_code)
                self.assertFalse(any(event[0] == "attach" for event in scenario.transport.events))

    def test_start_line_emitted_once_after_identity_verification(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_terminal(b"FIXTURE_BOUNDARY_READY"), ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
            inputs=[b"test input"],
        )
        prior_docker_calls = len(scenario.docker.calls)
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        start = ts.slice_b_session.build_start_message(scenario.authority).to_wire().encode("ascii")
        sent = [event[1] for event in scenario.transport.events if event[0] == "send"]
        self.assertEqual(sent.count(start), 1)
        self.assertEqual(scenario.transport.verbs_at_attach[prior_docker_calls:], ["inspect"])
        self.assertLess(
            next(i for i, event in enumerate(scenario.transport.events) if event == ("send", start)),
            next(i for i, event in enumerate(scenario.transport.events) if event[0] == "input"),
        )
        self.assertTrue(outcome.snapshot_captured)
        self.assertTrue(outcome.continue_sent)

    def test_normal_attach_reports_verified_zero_exit(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )

        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )

        self.assertIsNone(outcome.failure_code)
        self.assertEqual(outcome.tui_exit_code, 0)
        self.assertEqual(outcome.container_exit_code, 0)
        self.assertTrue(outcome.stop_verdict.verified)

    def test_snapshot_exception_still_stops_writer(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        with patch.object(scenario.snapshotter, "capture", side_effect=RuntimeError):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "snapshot-failed")
        self.assertIn("stop", scenario.docker.verbs())

    def test_close_exception_does_not_skip_restore_or_stop(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        with patch.object(scenario.transport, "close", side_effect=RuntimeError):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "attach-close-failed")
        self.assertIn(("restore", None), scenario.transport.events)
        self.assertIn("stop", scenario.docker.verbs())

    def test_close_interrupt_does_not_skip_restore_or_stop(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        with patch.object(scenario.transport, "close", side_effect=KeyboardInterrupt):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "attach-close-failed")
        self.assertIn(("restore", None), scenario.transport.events)
        self.assertIn("stop", scenario.docker.verbs())

    def test_unexpected_final_inspect_error_still_stops_writer(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        inspect_identity = scenario.supervisor._inspect_attach_identity
        inspect_count = 0

        def fail_final_inspect(identity, *, require_running):
            nonlocal inspect_count
            inspect_count += 1
            if inspect_count == 2:
                raise RuntimeError("simulated final inspect failure")
            return inspect_identity(identity, require_running=require_running)

        with patch.object(
            scenario.supervisor, "_inspect_attach_identity", side_effect=fail_final_inspect,
        ):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "writer-exit-unknown")
        self.assertIn("stop", scenario.docker.verbs())

    def test_restore_exception_does_not_skip_stop(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        with patch.object(scenario.transport, "restore_terminal", side_effect=RuntimeError):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "terminal-restore-failed")
        self.assertIn(("close", scenario.identity.container_id), scenario.transport.events)
        self.assertIn("stop", scenario.docker.verbs())

    def test_empty_poll_before_tui_exit_preserves_interaction(self) -> None:
        scenario = ts.TtyScenario(
            frames=[None, ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
            inputs=[b"interactive input"],
        )

        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )

        self.assertIsNone(outcome.failure_code)
        self.assertIn(("input", b"interactive input"), scenario.transport.events)

    def test_missing_frame_after_tui_exit_is_bounded(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"), None],
        )
        with patch.object(sup, "_POST_TUI_EXIT_TIMEOUT_S", 0):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "fixture-boundary-unconfirmed")
        self.assertEqual(outcome.tui_exit_code, 0)
        self.assertIn("stop", scenario.docker.verbs())

    def test_missing_frame_after_continue_is_bounded(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY"), None],
        )
        with patch.object(sup, "_POST_CONTINUE_TIMEOUT_S", 0):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "writer-exit-unknown")
        self.assertTrue(outcome.continue_sent)
        self.assertIn("stop", scenario.docker.verbs())

    def test_live_inspect_label_and_started_at_mismatch_blocks_attach(self) -> None:
        for tamper in ("labels", "started-at"):
            scenario = ts.TtyScenario()
            scenario.docker.tamper = tamper
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )
            with self.subTest(tamper=tamper):
                expected = "inspect-mismatch" if tamper == "labels" else "identity-mismatch"
                self.assertEqual(outcome.failure_code, expected)
                self.assertFalse(any(event[0] == "attach" for event in scenario.transport.events))

    def test_post_attach_image_change_is_not_accepted(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"), ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        scenario.docker.tamper_on_exit = "image"
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertEqual(outcome.failure_code, "writer-exit-unknown")
        self.assertFalse(outcome.stop_verdict.verified)

    def test_ready_duplicate_and_reversed_order_rejected(self) -> None:
        scenarios = (
            ts.TtyScenario(frames=[ts.tty_control("FIXTURE_BOUNDARY_READY"),
                                   ts.tty_control("TUI_EXIT 0")]),
            ts.TtyScenario(frames=[ts.tty_control("TUI_EXIT 0"),
                                   ts.tty_control("FIXTURE_BOUNDARY_READY"),
                                   ts.tty_control("FIXTURE_BOUNDARY_READY")]),
        )
        for scenario in scenarios:
            with self.subTest(frames=scenario.transport.frames):
                outcome = scenario.supervisor.attach_writer(
                    scenario.identity, scenario.transport, scenario.authority,
                )
                self.assertIsNotNone(outcome.failure_code)
                self.assertLessEqual(
                    sum(event[1] == ts.tty_frame(ts.TTY_CONTROL, ts.TTY_CONTINUE)
                        for event in scenario.transport.events if event[0] == "send"),
                    1,
                )

    def test_terminal_data_cannot_spoof_boundary_control(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_terminal(b"FIXTURE_BOUNDARY_READY"),
                    ts.tty_control("TUI_EXIT 0")],
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertFalse(outcome.snapshot_captured)
        self.assertFalse(outcome.continue_sent)
        self.assertIn(("display", b"FIXTURE_BOUNDARY_READY"), scenario.transport.events)

    def test_snapshot_failure_never_continues(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"), ts.tty_control("FIXTURE_BOUNDARY_READY")],
            snapshot=False,
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertFalse(outcome.snapshot_captured)
        self.assertFalse(outcome.continue_sent)
        self.assertNotIn(
            ("send", ts.tty_frame(ts.TTY_CONTROL, ts.TTY_CONTINUE)),
            scenario.transport.events,
        )

    def test_unknown_exit_codes_remain_pending(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
            exit_code=None,
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertEqual(outcome.tui_exit_code, 0)
        self.assertIsNone(outcome.container_exit_code)
        self.assertEqual(outcome.failure_code, "writer-exit-unknown")

    def test_unknown_tui_exit_code_never_continues(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT unknown"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertIsNone(outcome.tui_exit_code)
        self.assertFalse(outcome.continue_sent)
        self.assertEqual(outcome.failure_code, "interactive-protocol")

    def test_nonzero_tui_exit_never_continues(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 5"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertEqual(outcome.tui_exit_code, 5)
        self.assertFalse(outcome.continue_sent)
        self.assertEqual(outcome.failure_code, "tui-exit-nonzero")

    def test_ctrl_c_is_forwarded_and_terminal_is_restored(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_terminal(b"tui started"), ts.tty_control("TUI_EXIT 130")],
            inputs=[KeyboardInterrupt()],
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertIn(("send", b"\x03"), scenario.transport.events)
        self.assertIn(("restore", None), scenario.transport.events)
        self.assertEqual(outcome.failure_code, "interrupted")


if __name__ == "__main__":
    unittest.main()
