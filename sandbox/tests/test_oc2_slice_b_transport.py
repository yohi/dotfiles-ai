from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import oc2_supervisor as sup  # noqa: E402
import oc2_slice_b_transport as transport  # noqa: E402
import test_oc2_slice_b_tty as tty_tests  # noqa: E402

CID = "a" * 64
OTHER_CID = "b" * 64
FRAME = struct.Struct(">4sBI")


class FakeProcess:
    def __init__(self, returncode: int | None = None) -> None:
        self.output_read, self.output_write = os.pipe()
        self.input_read, self.input_write = os.pipe()
        self.stdout = os.fdopen(self.output_read, "rb", buffering=0)
        self.stdin = os.fdopen(self.input_write, "wb", buffering=0)
        self.returncode = returncode
        self.terminated = False
        self.waited = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.waited = True
        if self.returncode is None:
            self.returncode = -15
        return self.returncode

    def emit(self, data: bytes) -> None:
        os.write(self.output_write, data)

    def received_stdin(self) -> bytes:
        os.set_blocking(self.input_read, False)
        try:
            return os.read(self.input_read, 65536)
        except BlockingIOError:
            return b""

    def finish_output(self) -> None:
        os.close(self.output_write)

    def dispose(self) -> None:
        for stream in (self.stdout, self.stdin):
            if not stream.closed:
                stream.close()
        for fd in (self.input_read, self.output_write):
            try:
                os.close(fd)
            except OSError:
                pass


class AttachTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.processes: list[FakeProcess] = []
        self.transport = self._make_transport()

    def _make_transport(self) -> transport.DockerAttachTransport:
        """Create a fake-backed transport with cleanup registered immediately."""
        processes: list[FakeProcess] = []

        def popen(argv: list[str], **kwargs: object) -> FakeProcess:
            self.calls.append((argv, kwargs))
            process = FakeProcess()
            processes.append(process)
            self.processes.append(process)
            return process

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=popen,
            _stdin_fd=None, _stdout_fd=None,
        )
        self.addCleanup(self._cleanup_transport, adapter, processes)
        return adapter

    def _cleanup_transport(
        self,
        adapter: transport.DockerAttachTransport,
        processes: list[FakeProcess],
    ) -> None:
        """Close a transport before disposing all fake process pipes it created."""
        try:
            adapter.close(CID)
        finally:
            try:
                adapter.restore_terminal()
            finally:
                for process in processes:
                    process.dispose()

    def test_rejects_non_full_container_ids_before_process_start(self) -> None:
        for invalid in ("a" * 12, "A" * 64, "a" * 63, "a" * 65, "name"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(sup.InteractiveTransportError):
                    self.transport.attach(invalid)
        self.assertEqual(self.calls, [])

    def test_attach_uses_one_exact_argv_and_shell_false(self) -> None:
        self.transport.attach(CID)
        self.assertEqual(self.calls[0][0], ["/usr/bin/docker", "attach", CID])
        self.assertIs(self.calls[0][1]["shell"], False)
        env = self.calls[0][1]["env"]
        assert isinstance(env, dict)
        self.assertEqual(
            set(env),
            {"HOME", "DOCKER_CONFIG"},
        )
        self.assertEqual(len(self.calls), 1)

    def test_rejects_second_attach_and_foreign_id(self) -> None:
        self.transport.attach(CID)
        with self.assertRaises(sup.InteractiveTransportError):
            self.transport.attach(CID)
        for action in (
            lambda: self.transport.send_stdin(OTHER_CID, b"x"),
            lambda: self.transport.receive_frame(OTHER_CID, 0),
            lambda: self.transport.close(OTHER_CID),
        ):
            with self.assertRaises(sup.InteractiveTransportError):
                action()
        self.assertEqual(len(self.calls), 1)

    def test_accumulates_partial_header_and_payload(self) -> None:
        self.transport.attach(CID)
        frame = FRAME.pack(b"OC2T", 1, 4) + b"data"
        self.processes[0].emit(frame[:3])
        original_read = self.transport._read_available
        chunks = iter((frame[3:FRAME.size + 2], frame[FRAME.size + 2:]))

        def read_after_chunk(timeout: float) -> bytes | None:
            chunk = original_read(timeout)
            try:
                self.processes[0].emit(next(chunks))
            except StopIteration:
                pass
            if chunk is not None and not isinstance(chunk, bytes):
                raise AssertionError("fake pipe returned non-bytes")
            return chunk

        with patch.object(self.transport, "_read_available", side_effect=read_after_chunk):
            self.assertEqual(self.transport.receive_frame(CID, 1), frame)

    def test_returns_concatenated_frames_one_at_a_time(self) -> None:
        self.transport.attach(CID)
        first = FRAME.pack(b"OC2T", 1, 1) + b"x"
        second = FRAME.pack(b"OC2T", 2, 1) + b"y"
        self.processes[0].emit(first + second)
        self.assertEqual(self.transport.receive_frame(CID, 1), first)
        self.assertEqual(self.transport.receive_frame(CID, 1), second)

    def test_rejects_malformed_frames_and_oversized_length(self) -> None:
        malformed = (
            b"NOPE" + FRAME.pack(b"OC2T", 1, 0)[4:],
            FRAME.pack(b"OC2T", 3, 0),
            FRAME.pack(b"OC2T", 1, 65537),
        )
        for frame in malformed:
            with self.subTest(frame=frame):
                self.transport = self._make_transport()
                self.transport.attach(CID)
                self.processes[-1].emit(frame)
                with self.assertRaises(sup.InteractiveTransportError):
                    self.transport.receive_frame(CID, 1)

    def test_timeout_without_partial_bytes_is_poll_timeout(self) -> None:
        self.transport.attach(CID)
        self.assertIsNone(self.transport.receive_frame(CID, 0))

    def test_zero_timeout_reads_a_frame_already_available_on_pipe(self) -> None:
        self.transport.attach(CID)
        frame = FRAME.pack(b"OC2T", 1, 4) + b"data"
        self.processes[0].emit(frame)

        self.assertEqual(self.transport.receive_frame(CID, 0), frame)

    def test_zero_timeout_completes_a_buffered_partial_frame_when_remainder_is_ready(self) -> None:
        self.transport.attach(CID)
        frame = FRAME.pack(b"OC2T", 1, 4) + b"data"
        self.transport._frame_buffer.extend(frame[:3])
        self.processes[0].emit(frame[3:])

        self.assertEqual(self.transport.receive_frame(CID, 0), frame)

    def test_timeout_with_partial_frame_fails_closed(self) -> None:
        self.transport.attach(CID)
        self.processes[0].emit(b"OC2")
        with self.assertRaises(sup.InteractiveTransportError):
            self.transport.receive_frame(CID, 0.01)

    def test_eof_is_detach_even_when_cli_returncode_is_zero(self) -> None:
        self.transport.attach(CID)
        self.processes[0].returncode = 0
        self.processes[0].finish_output()
        with self.assertRaises(sup.InteractiveDetachedError):
            self.transport.receive_frame(CID, 1)

    def test_terminal_bytes_are_output_only_and_not_control_scanned(self) -> None:
        self.transport.attach(CID)
        payload = b"OC2T FIXTURE_BOUNDARY_READY"
        frame = FRAME.pack(b"OC2T", 1, len(payload)) + payload
        self.processes[0].emit(frame)
        self.assertEqual(self.transport.receive_frame(CID, 1), frame)

    def test_start_line_echoed_as_non_frame_fails_closed(self) -> None:
        self.transport.attach(CID)
        self.transport.send_stdin(CID, b"OC2_SLICE_B_START ...\n")
        self.processes[0].emit(b"OC2_SLICE_B_START ...\n")
        with self.assertRaises(sup.InteractiveTransportError):
            self.transport.receive_frame(CID, 1)

    def test_close_reaps_and_restores_after_attach(self) -> None:
        self.transport.attach(CID)
        process = self.processes[0]
        self.transport.close(CID)
        self.transport.close(CID)
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)
        self.transport.restore_terminal()
        self.transport.restore_terminal()

    def test_ctrl_c_is_forwarded_as_raw_terminal_byte(self) -> None:
        self.transport.attach(CID)
        self.transport.send_stdin(CID, b"\x03")
        self.assertEqual(self.processes[0].received_stdin(), b"\x03")

    def test_invalid_docker_paths_are_rejected(self) -> None:
        for path in ("docker", "/usr/bin/docker/..", "/usr/bin/other", "/a b/docker"):
            with self.subTest(path=path), self.assertRaises(sup.SupervisorInputError):
                transport.DockerAttachTransport(path, _stdin_fd=None, _stdout_fd=None)

    def test_raw_terminal_setup_failure_does_not_start_docker(self) -> None:
        restored: list[list[int]] = []

        def fail_raw(fd: int) -> None:
            del fd
            raise OSError("raw mode unavailable")

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=lambda *args, **kwargs: self.fail("spawned"),
            _stdin_fd=0, _stdout_fd=None, _isatty=lambda fd: True,
            _get_terminal=lambda fd: [0], _set_raw=fail_raw,
            _set_terminal=lambda fd, when, state: restored.append(state),
        )
        with self.assertRaises(sup.InteractiveTransportError):
            adapter.attach(CID)
        adapter.restore_terminal()
        self.assertEqual(restored, [[0]])

    def test_terminal_restore_failure_is_not_silenced(self) -> None:
        calls = 0

        def fail_restore(fd: int, when: int, state: list[object]) -> None:
            nonlocal calls
            del fd, when, state
            calls += 1
            raise OSError("restore denied")

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=lambda *args, **kwargs: None,
            _stdin_fd=0, _stdout_fd=None, _isatty=lambda fd: True,
            _get_terminal=lambda fd: [0], _set_raw=lambda fd: None,
            _set_terminal=fail_restore,
        )
        adapter._terminal_state = [0]
        for _ in range(2):
            with self.assertRaises(sup.InteractiveTransportError):
                adapter.restore_terminal()
        self.assertEqual(calls, 2)

    def test_terminal_state_is_restored_after_successful_raw_setup(self) -> None:
        observed: list[tuple[str, object]] = []
        saved_state = [1, 2, 3]

        def popen(argv: list[str], **kwargs: object) -> FakeProcess:
            del argv, kwargs
            process = FakeProcess()
            self.processes.append(process)
            return process

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=popen,
            _stdin_fd=0, _stdout_fd=None, _isatty=lambda fd: True,
            _get_terminal=lambda fd: saved_state,
            _set_raw=lambda fd: observed.append(("raw", fd)),
            _set_terminal=lambda fd, when, state: observed.append(("restore", state)),
        )
        adapter.attach(CID)
        adapter.close(CID)
        adapter.restore_terminal()
        self.assertEqual(observed, [("raw", 0), ("restore", saved_state)])

    def test_unreaped_attach_process_is_reported_unverified(self) -> None:
        class FailReapProcess(FakeProcess):
            def wait(self, timeout: float | None = None) -> int:
                raise subprocess.TimeoutExpired(
                    "docker attach", timeout if timeout is not None else 5,
                )

            def kill(self) -> None:
                raise OSError("process state unknown")

        failed_process: list[FailReapProcess] = []

        def popen(argv: list[str], **kwargs: object) -> FailReapProcess:
            del argv, kwargs
            process = FailReapProcess()
            failed_process.append(process)
            return process

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=popen,
            _stdin_fd=None, _stdout_fd=None,
        )
        adapter.attach(CID)
        with self.assertRaises(sup.InteractiveTransportError):
            adapter.close(CID)
        failed_process[0].dispose()

    def test_real_supervisor_and_pid1_run_over_fake_docker_attach_pipes(self) -> None:
        harness = tty_tests.Pid1SupervisorInProcessTests()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        scenario = tty_tests.ts.TtyScenario()
        manifest = tty_tests.replace(
            scenario.authority.manifest,
            baseline=tty_tests.replace(
                scenario.authority.manifest.baseline,
                head_oid=harness.head,
            ),
        )
        authority = tty_tests.replace(
            scenario.authority,
            manifest=manifest,
            manifest_sha256=tty_tests.hashlib.sha256(
                tty_tests.ts.slice_b_git._manifest_bytes(manifest),
            ).hexdigest(),
        )
        bridge = tty_tests.Pid1Bridge(scenario)

        class AttachProcess:
            def __init__(self) -> None:
                self.stdin = os.fdopen(bridge._to_w, "wb", buffering=0)
                self.stdout = os.fdopen(bridge._from_r, "rb", buffering=0)
                self.returncode: int | None = None
                bridge._thread = threading.Thread(target=self.run_pid1, daemon=True)

            def run_pid1(inner_self: AttachProcess) -> None:
                del inner_self
                try:
                    bridge.rc = tty_tests.pid1.serve(bridge._to_r, bridge._from_w)
                finally:
                    os.close(bridge._from_w)
                    scenario.docker.final_exit_code = bridge.rc
                    scenario.docker.state = "exited"

            def poll(inner_self: AttachProcess) -> int | None:
                if not bridge._thread.is_alive() and bridge._thread.ident is not None:
                    inner_self.returncode = bridge.rc
                return inner_self.returncode

            def wait(inner_self: AttachProcess, timeout: float | None = None) -> int:
                bridge._thread.join(timeout)
                if bridge._thread.is_alive():
                    raise subprocess.TimeoutExpired(
                        "docker attach", timeout if timeout is not None else 5,
                    )
                inner_self.returncode = bridge.rc
                return bridge.rc if bridge.rc is not None else -1

            def terminate(inner_self: AttachProcess) -> None:
                inner_self.returncode = -15

            def kill(inner_self: AttachProcess) -> None:
                inner_self.returncode = -9

        process: AttachProcess | None = None

        def popen(argv: list[str], **kwargs: object) -> AttachProcess:
            nonlocal process
            self.assertEqual(
                argv,
                ["/usr/bin/docker", "attach", scenario.identity.container_id],
            )
            self.assertIs(kwargs["shell"], False)
            process = AttachProcess()
            bridge._thread.start()
            return process

        adapter = transport.DockerAttachTransport(
            "/usr/bin/docker", _popen=popen,
            _stdin_fd=None, _stdout_fd=None,
        )

        def cleanup_attach() -> None:
            if process is not None and not process.stdin.closed:
                process.stdin.close()
            try:
                adapter.close(scenario.identity.container_id)
            finally:
                if bridge._thread.ident is not None:
                    bridge._thread.join(5)
                if bridge._thread.is_alive():
                    os.close(bridge._to_r)
                    bridge._thread.join(5)
                if process is not None and not process.stdout.closed:
                    process.stdout.close()
                if bridge._thread.is_alive():
                    raise AssertionError("PID 1 daemon thread did not stop")
                if bridge._to_r >= 0:
                    os.close(bridge._to_r)
                    bridge._to_r = -1
                adapter.restore_terminal()

        self.addCleanup(cleanup_attach)
        scenario.transport = adapter
        tui = tty_tests.te.FakeTui(b"offline TUI output")
        with (
            patch.object(tty_tests.pid1, "_spawn_tui", return_value=tui),
        ):
            outcome = scenario.supervisor.attach_writer(
                scenario.identity, adapter, authority,
            )
        self.assertIsNone(outcome.failure_code)
        self.assertTrue(outcome.snapshot_captured)
        self.assertTrue(outcome.continue_sent)
        self.assertEqual(bridge.rc, 0)
        self.assertIsNotNone(process)
        self.assertEqual(scenario.docker.final_exit_code, 0)


if __name__ == "__main__":
    unittest.main()
