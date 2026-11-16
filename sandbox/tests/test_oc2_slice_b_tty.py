"""Fake-only tests for the Slice B interactive Writer boundary."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import select
import sys
import tempfile
import threading
import time
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
import test_oc2_slice_b_entrypoint as te  # noqa: E402

pid1 = te.e


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

    def test_terminal_frames_do_not_bypass_tui_exit_deadline(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"), ts.tty_terminal(b"still active"), None],
        )
        def monotonic() -> float:
            return 11 if scenario.transport.frames == [None] else 0

        with patch.object(sup, "_POST_TUI_EXIT_TIMEOUT_S", 10), patch.object(
            sup.time, "monotonic", side_effect=monotonic,
        ):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "fixture-boundary-unconfirmed")
        self.assertEqual(scenario.transport.frames, [None])
        self.assertIn("stop", scenario.docker.verbs())

    def test_terminal_frames_do_not_bypass_continue_deadline(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY"),
                    ts.tty_terminal(b"still active"), None],
        )
        def monotonic() -> float:
            return 11 if scenario.transport.frames == [None] else 0

        with patch.object(sup, "_POST_TUI_EXIT_TIMEOUT_S", 10), patch.object(
            sup, "_POST_CONTINUE_TIMEOUT_S", 10,
        ), patch.object(sup.time, "monotonic", side_effect=monotonic):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, scenario.transport, scenario.authority,
            )

        self.assertEqual(outcome.failure_code, "writer-exit-unknown")
        self.assertTrue(outcome.continue_sent)
        self.assertEqual(scenario.transport.frames, [None])
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

    def test_supervisor_rejects_malformed_pid1_frames(self) -> None:
        good = ts.tty_control("TUI_EXIT 0")
        bad_frames = {
            "bad-magic": b"OC2X" + good[4:],
            "unknown-kind": good[:4] + b"\x03" + good[5:],
            "truncated": good[:-1],
            "trailing": good + b"x",
            "header-only": good[:5],
            "oversized": b"OC2T\x01\x00\x01\x00\x01" + b"x" * 65537,
            "not-bytes": "OC2T",
        }
        for name, bad in bad_frames.items():
            with self.subTest(name=name):
                with self.assertRaises(sup.InteractiveProtocolError):
                    sup._decode_interactive_frame(bad)
                scenario = ts.TtyScenario(
                    frames=[bad, good, ts.tty_control("FIXTURE_BOUNDARY_READY")],
                )
                outcome = scenario.supervisor.attach_writer(
                    scenario.identity, scenario.transport, scenario.authority,
                )
                self.assertEqual(outcome.failure_code, "interactive-protocol")
                self.assertFalse(outcome.snapshot_captured)
                self.assertFalse(outcome.continue_sent)
                # The frames after the invalid one were never consumed.
                self.assertEqual(len(scenario.transport.frames), 2)

    def test_duplicate_tui_exit_rejected(self) -> None:
        scenario = ts.TtyScenario(
            frames=[ts.tty_control("TUI_EXIT 0"), ts.tty_control("TUI_EXIT 0"),
                    ts.tty_control("FIXTURE_BOUNDARY_READY")],
        )
        outcome = scenario.supervisor.attach_writer(
            scenario.identity, scenario.transport, scenario.authority,
        )
        self.assertEqual(outcome.failure_code, "interactive-protocol")
        self.assertFalse(outcome.continue_sent)


class Pid1Bridge:
    """InteractiveTransport fake joining attach_writer to a real entrypoint.serve.

    Bytes cross two OS pipes (no Docker, PTY or network). This class only
    cuts PID 1's stream at the length each header announces and hands the cut
    to the Supervisor's own decoder; it validates nothing itself.
    """

    def __init__(self, scenario: ts.TtyScenario, inputs: tuple[bytes, ...] = ()) -> None:
        self.docker = scenario.docker
        self.inputs = list(inputs)
        self.events: list[tuple[str, str | bytes | None]] = []
        self.rc: int | None = None
        self._to_r, self._to_w = os.pipe()
        self._from_r, self._from_w = os.pipe()
        self._to_w_open = True
        self._buf = bytearray()
        self._thread = threading.Thread(target=self._pid1, daemon=True)

    def _pid1(self) -> None:
        try:
            self.rc = pid1.serve(self._to_r, self._from_w)
        finally:
            os.close(self._from_w)

    def _pid1_exited(self) -> None:
        self._thread.join(10)
        self.docker.final_exit_code = self.rc
        self.docker.state = "exited"

    def attach(self, container_id: str) -> None:
        self.events.append(("attach", container_id))
        self._thread.start()

    def send_stdin(self, container_id: str, data: bytes) -> None:
        self.events.append(("send", data))
        os.write(self._to_w, data)

    def receive_frame(self, container_id: str, timeout: float) -> bytes | None:
        end = time.monotonic() + timeout
        while True:
            header = sup._INTERACTIVE_FRAME_HEADER
            if len(self._buf) >= header.size:
                total = header.size + header.unpack_from(self._buf)[2]
                if len(self._buf) >= total:
                    raw = bytes(self._buf[:total])
                    del self._buf[:total]
                    return raw
            ready, _, _ = select.select([self._from_r], [], [], max(0.0, end - time.monotonic()))
            if not ready:
                return None
            chunk = os.read(self._from_r, 65536)
            if not chunk:
                self._pid1_exited()
                if self._buf:
                    raw = bytes(self._buf)
                    self._buf.clear()
                    return raw
                raise sup.InteractiveDetachedError("PID 1 closed the channel")
            self._buf.extend(chunk)

    def read_terminal_input(self, timeout: float) -> bytes | None:
        if not self.inputs:
            return None
        item = self.inputs.pop(0)
        self.events.append(("input", item))
        return item

    def write_terminal_output(self, data: bytes) -> None:
        self.events.append(("display", data))

    def close(self, container_id: str) -> None:
        self.events.append(("close", container_id))
        if self._to_w_open:
            self._to_w_open = False
            os.close(self._to_w)
        self._pid1_exited()
        os.close(self._to_r)
        os.close(self._from_r)

    def restore_terminal(self) -> None:
        self.events.append(("restore", None))

    def sent(self) -> list[bytes]:
        return [
            event[1]
            for event in self.events
            if event[0] == "send" and isinstance(event[1], bytes)
        ]

    def displayed(self) -> bytes:
        return b"".join(
            event[1]
            for event in self.events
            if event[0] == "display" and isinstance(event[1], bytes)
        )


class Pid1SupervisorInProcessTests(unittest.TestCase):
    """Real GuestSupervisor.attach_writer against the real PID 1 entrypoint."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        te.git(self.root, "init", "-b", "sliceb")
        te.git(self.root, "config", "user.name", "Fixture")
        te.git(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "original").write_text("before\n")
        te.git(self.root, "add", "original")
        te.git(self.root, "commit", "-m", "base")
        self.head = te.git(self.root, "rev-parse", "HEAD")
        self.fixture = self.root / te.f.FIXTURE_NAME
        workspace = patch.object(pid1, "_WORKSPACE", self.root)
        workspace.start()
        self.addCleanup(workspace.stop)

    def attach(
        self, tui: te.FakeTui, inputs: tuple[bytes, ...] = (), *, snapshot: bool = True,
    ) -> tuple[ts.TtyScenario, Pid1Bridge, sup.AttachOutcome, list[bool]]:
        """Run one full attach with the Guest repository's real HEAD as authority."""
        scenario = ts.TtyScenario(snapshot=snapshot)
        manifest = replace(
            scenario.authority.manifest,
            baseline=replace(scenario.authority.manifest.baseline, head_oid=self.head),
        )
        authority = replace(
            scenario.authority, manifest=manifest,
            manifest_sha256=hashlib.sha256(ts.slice_b_git._manifest_bytes(manifest)).hexdigest(),
        )
        fixture_seen_at_snapshot: list[bool] = []
        capture = scenario.snapshotter.capture

        def observing_capture(identity, authority):
            fixture_seen_at_snapshot.append(self.fixture.exists())
            return capture(identity, authority)

        bridge = Pid1Bridge(scenario, inputs)
        with (
            patch.object(scenario.snapshotter, "capture", side_effect=observing_capture),
            patch.object(pid1, "_spawn_tui", return_value=tui),
        ):
            outcome = scenario.supervisor.attach_writer(scenario.identity, bridge, authority)
        self.start_line = ts.slice_b_session.build_start_message(authority).to_wire().encode("ascii")
        return scenario, bridge, outcome, fixture_seen_at_snapshot

    def test_wire_constants_and_codecs_agree_bytewise(self) -> None:
        self.assertEqual(pid1._FRAME_MAGIC, sup._INTERACTIVE_FRAME_MAGIC)
        self.assertEqual(pid1._FRAME_HEADER.format, sup._INTERACTIVE_FRAME_HEADER.format)
        self.assertEqual(pid1._FRAME_TERMINAL, sup._INTERACTIVE_TERMINAL_FRAME)
        self.assertEqual(pid1._FRAME_CONTROL, sup._INTERACTIVE_CONTROL_FRAME)
        self.assertEqual(pid1._MAX_FRAME_PAYLOAD, sup._MAX_INTERACTIVE_FRAME_BYTES)
        self.assertEqual(pid1._MAX_FRAME_PAYLOAD, 65536)
        for kind, payload in (
            (pid1._FRAME_CONTROL, b"TUI_EXIT 0"),
            (pid1._FRAME_CONTROL, pid1._CONTROL_READY),
            (pid1._FRAME_CONTROL, pid1._CONTROL_CONTINUE),
            (pid1._FRAME_TERMINAL, b""),
            (pid1._FRAME_TERMINAL, bytes(range(256)) * 256),
        ):
            with self.subTest(kind=kind, size=len(payload)):
                wire = pid1.encode_frame(kind, payload)
                self.assertEqual(wire, sup._encode_interactive_frame(kind, payload))
                self.assertEqual(sup._decode_interactive_frame(wire), (kind, payload))
                self.assertEqual(pid1.decode_frame_header(wire[:9]), (kind, len(payload)))

    def test_pid1_tui_exit_frames_parse_in_supervisor(self) -> None:
        for code in (0, 1, 5, 23, 130, 255):
            with self.subTest(code=code):
                wire = te.Wire(self)
                pid1._report_tui_exit(wire.channel, code)
                raw = wire.sent()
                self.assertEqual(raw, ts.tty_control(f"TUI_EXIT {code}"))
                kind, payload = sup._decode_interactive_frame(raw)
                self.assertEqual(kind, sup._INTERACTIVE_CONTROL_FRAME)
                self.assertEqual(sup._parse_tui_exit(payload), code)

    def test_supervisor_continue_frame_is_accepted_by_pid1(self) -> None:
        wire = te.Wire(self)
        wire.reply_after(
            te.READY,
            sup._encode_interactive_frame(
                sup._INTERACTIVE_CONTROL_FRAME, b"FIXTURE_BOUNDARY_CONTINUE",
            ),
        )
        pid1._supervisor_fixture_boundary(wire.channel)
        kind, payload = sup._decode_interactive_frame(wire.sent())
        self.assertEqual((kind, payload), (sup._INTERACTIVE_CONTROL_FRAME, b"FIXTURE_BOUNDARY_READY"))

    def test_full_session_snapshot_then_continue_then_fixture(self) -> None:
        spoof = (
            b"tui> " + ts.tty_control("TUI_EXIT 0") + ts.tty_control("FIXTURE_BOUNDARY_READY")
            + ts.tty_frame(ts.TTY_CONTROL, ts.TTY_CONTINUE) + b" OC2T FIXTURE_BOUNDARY_READY"
        )
        tui = te.FakeTui(spoof, await_input=b"q")
        scenario, bridge, outcome, fixture_seen = self.attach(tui, (b"q",))

        self.assertIsNone(outcome.failure_code)
        self.assertEqual(outcome.tui_exit_code, 0)
        self.assertEqual(bridge.rc, 0)
        self.assertEqual(outcome.container_exit_code, 0)
        self.assertTrue(outcome.boundary_ready)
        self.assertTrue(outcome.snapshot_captured)
        self.assertTrue(outcome.continue_sent)
        self.assertTrue(outcome.stop_verdict.verified)
        # One snapshot, taken while PID 1 was blocked before any fixture write.
        self.assertEqual(fixture_seen, [False])
        self.assertEqual(scenario.events, [("snapshot", scenario.identity.container_id)])
        # TUI look-alike bytes were displayed verbatim and opened nothing.
        self.assertEqual(bridge.displayed(), spoof)
        # Start line once, raw input to the TUI only, then exactly one CONTINUE.
        self.assertEqual(
            bridge.sent(),
            [self.start_line, b"q", ts.tty_frame(ts.TTY_CONTROL, ts.TTY_CONTINUE)],
        )
        self.assertEqual(bytes(tui.received), b"q")
        self.assertEqual(self.fixture.read_bytes(), te.f.FIXTURE_BYTES)
        self.assertEqual(te.git(self.root, "rev-parse", "HEAD^"), self.head)
        self.assertEqual(
            te.git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
            te.f.FIXTURE_NAME,
        )

    def test_nonzero_tui_exit_reaches_supervisor_without_ready(self) -> None:
        scenario, bridge, outcome, fixture_seen = self.attach(te.FakeTui(b"bye", exit_code=7))

        self.assertEqual(outcome.tui_exit_code, 7)
        self.assertEqual(outcome.failure_code, "tui-exit-nonzero")
        self.assertFalse(outcome.boundary_ready)
        self.assertFalse(outcome.continue_sent)
        self.assertEqual(fixture_seen, [])
        self.assertEqual(bridge.sent(), [self.start_line])
        self.assertEqual(bridge.rc, 23)
        self.assertEqual(outcome.container_exit_code, 23)
        self.assertFalse(self.fixture.exists())
        self.assertEqual(te.git(self.root, "rev-parse", "HEAD"), self.head)

    def test_snapshot_failure_sends_no_continue_and_pid1_fails_closed(self) -> None:
        scenario, bridge, outcome, fixture_seen = self.attach(te.FakeTui(), snapshot=False)

        self.assertEqual(outcome.failure_code, "snapshot-failed")
        self.assertTrue(outcome.boundary_ready)
        self.assertFalse(outcome.snapshot_captured)
        self.assertFalse(outcome.continue_sent)
        self.assertEqual(fixture_seen, [False])
        self.assertEqual(bridge.sent(), [self.start_line])
        self.assertEqual(bridge.rc, 22)
        self.assertFalse(self.fixture.exists())
        self.assertEqual(te.git(self.root, "rev-parse", "HEAD"), self.head)

    def test_guest_head_mismatch_starts_no_tui_and_reports_no_exit(self) -> None:
        # The Supervisor's trusted baseline stays at the pre-drift HEAD.
        te.git(self.root, "commit", "--allow-empty", "-m", "drift")
        tui = te.FakeTui()
        self.addCleanup(tui.close)
        with patch.object(pid1, "_relay_tui") as relay:
            scenario, bridge, outcome, fixture_seen = self.attach(tui)
            relay.assert_not_called()

        self.assertIsNone(outcome.tui_exit_code)
        self.assertIsNotNone(outcome.failure_code)
        self.assertFalse(outcome.continue_sent)
        self.assertEqual(bridge.rc, 22)
        self.assertFalse(self.fixture.exists())


if __name__ == "__main__":
    unittest.main()
