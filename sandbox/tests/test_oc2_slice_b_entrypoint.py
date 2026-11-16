from pathlib import Path
import importlib.util
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

TOP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "entrypoint", TOP / "oc2_slice_b" / "entrypoint.py"
)
assert spec is not None and spec.loader is not None
e = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = e
spec.loader.exec_module(e)
sys.path.insert(0, str(TOP / "oc2_slice_b"))
import offline_fixture as f  # noqa: E402


def git(root: Path, *args: str) -> str:
    """Run an isolated fixture Git command and return its decoded output."""
    home = root.parent / "git-home"
    home.mkdir(mode=0o700, exist_ok=True)
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        env={
            "PATH": "/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/dev/null",
            "GIT_CONFIG_KEY_1": "commit.gpgSign", "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "false",
        },
    )
    if p.returncode:
        raise AssertionError(p.stderr.decode())
    return p.stdout.decode().strip()


def frame(kind: int, payload: bytes) -> bytes:
    """Build an OC2T frame independently of the implementation under test."""
    return b"OC2T" + struct.pack(">BI", kind, len(payload)) + payload


TERMINAL = 1
CONTROL = 2
READY = frame(CONTROL, b"FIXTURE_BOUNDARY_READY")
CONTINUE = frame(CONTROL, b"FIXTURE_BOUNDARY_CONTINUE")


def split_frames(raw: bytes) -> list[tuple[int, bytes]]:
    """Split a complete PID 1 output stream into (kind, payload) frames."""
    frames = []
    while raw:
        magic, kind, size = struct.unpack_from(">4sBI", raw)
        if magic != b"OC2T" or len(raw) < 9 + size:
            raise AssertionError(f"unframed PID 1 output: {raw[:32]!r}")
        frames.append((kind, raw[9:9 + size]))
        raw = raw[9 + size:]
    return frames


class Wire:
    """Pipe-backed Supervisor side of a real SupervisorChannel; no PTY involved."""

    def __init__(self, case: unittest.TestCase) -> None:
        self.to_pid1_r, self.to_pid1_w = os.pipe()
        self.from_pid1_r, self.from_pid1_w = os.pipe()
        self.channel = e.SupervisorChannel(self.to_pid1_r, self.from_pid1_w)
        self.captured = bytearray()
        self._open = {self.to_pid1_r, self.to_pid1_w, self.from_pid1_r, self.from_pid1_w}
        self._reader: threading.Thread | None = None
        case.addCleanup(self.close)

    def feed(self, data: bytes) -> None:
        os.write(self.to_pid1_w, data)

    def eof(self) -> None:
        self._close(self.to_pid1_w)

    def reply_after(self, marker: bytes, reply: bytes | None) -> None:
        """Capture PID 1 output in the background; answer once marker is seen.

        A reply of None closes the Supervisor side instead (EOF).
        """
        def run() -> None:
            answered = False
            while True:
                chunk = os.read(self.from_pid1_r, 65536)
                if not chunk:
                    return
                self.captured.extend(chunk)
                if not answered and marker in self.captured:
                    answered = True
                    if reply is None:
                        self.eof()
                    elif reply:
                        self.feed(reply)

        self._reader = threading.Thread(target=run, daemon=True)
        self._reader.start()

    def sent(self) -> bytes:
        """Finish PID 1's side and return every byte it wrote."""
        self._close(self.from_pid1_w)
        if self._reader is not None:
            self._reader.join(5)
        else:
            while chunk := os.read(self.from_pid1_r, 65536):
                self.captured.extend(chunk)
        return bytes(self.captured)

    def _close(self, fd: int) -> None:
        if fd in self._open:
            self._open.discard(fd)
            os.close(fd)

    def close(self) -> None:
        for fd in (self.to_pid1_w, self.from_pid1_w):
            self._close(fd)
        if self._reader is not None:
            self._reader.join(5)
        for fd in list(self._open):
            self._close(fd)


class FakeTui:
    """Scripted in-memory TUI on a socketpair: emit output, await input, exit."""

    def __init__(self, output: bytes = b"", exit_code: int = 0,
                 await_input: bytes = b"", hang: bool = False) -> None:
        self._near, self._far = socket.socketpair()
        self.fd = self._near.fileno()
        self.received = bytearray()
        self.killed = False
        self.closed = False
        self._code: int | None = None
        self._stop = threading.Event()
        self._script = (output, exit_code, await_input, hang)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        output, exit_code, await_input, hang = self._script
        try:
            self._far.sendall(output)
            self._far.settimeout(5)
            while await_input and await_input not in self.received:
                chunk = self._far.recv(4096)
                if not chunk:
                    break
                self.received.extend(chunk)
            if hang:
                self._stop.wait(5)
        except OSError:
            pass
        finally:
            self._code = 137 if self.killed else exit_code
            self._far.close()

    def poll(self) -> int | None:
        return self._code

    def kill(self) -> None:
        self.killed = True
        self._stop.set()
        self._thread.join(5)

    def resize(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self._near.close()


class EntryTests(unittest.TestCase):
    def setUp(self) -> None:
        """Create a clean Guest repository and capture its baseline HEAD/ref."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "sliceb")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "original").write_text("before\n")
        git(self.root, "add", "original")
        git(self.root, "commit", "-m", "base")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.line = f"OC2_SLICE_B_START {uuid.uuid4()} {self.head} refs/heads/sliceb {'a' * 64}\n"

    def test_wire_strict_validation(self) -> None:
        """Syntax validation rejects malformed frames; baseline equality is separate."""
        a = e.parse_start_line(self.line)
        self.assertEqual(a.head_oid, self.head)
        for wrong in [
            self.line.rstrip("\n"),
            self.line.replace(" ", "  ", 1),
            self.line + "x",
            self.line.replace(self.head, "f" * 40),
            self.line.replace("sliceb", "..bad"),
        ]:
            if wrong == self.line.replace(self.head, "f" * 40):
                # valid syntax but changed expected head: reject in Guest comparison
                continue
            with self.assertRaises(e.SliceBEntryRejected):
                e.parse_start_line(wrong)

    def test_tui_nonzero_never_fixtures(self) -> None:
        """A nonzero TUI exit code returns its dedicated status without fixture use."""
        wire = Wire(self)
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=5),
            patch.object(e, "_supervisor_fixture_boundary") as b,
        ):
            self.assertEqual(e.run_entrypoint(self.line, wire.channel), 23)
            b.assert_not_called()
        self.assertEqual(wire.sent(), frame(CONTROL, b"TUI_EXIT 5"))

    def test_missing_boundary_blocks_fixture(self) -> None:
        """The unavailable trusted fixture boundary blocks execution after baseline checks."""
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=0),
        ):
            self.assertEqual(e.run_entrypoint(self.line), 22)
            self.assertFalse((self.root / f.FIXTURE_NAME).exists())

    def test_fixture_exact_commit_and_preserves_other_staged(self) -> None:
        """Fixture commit changes only its path and retains other staged state."""
        (self.root / "original").write_text("modified\n")
        git(self.root, "add", "original")
        before = git(self.root, "ls-files", "--stage", "original")
        commit = f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")
        self.assertEqual(
            git(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split(),
            [commit, self.head],
        )
        self.assertEqual(
            git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
            f.FIXTURE_NAME,
        )
        self.assertEqual((self.root / f.FIXTURE_NAME).read_bytes(), f.FIXTURE_BYTES)
        self.assertEqual(git(self.root, "ls-files", "--stage", "original"), before)
        self.assertEqual(
            git(self.root, "show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD"),
            f"{f.FIXTURE_USER}|{f.FIXTURE_EMAIL}|{f.FIXTURE_USER}|{f.FIXTURE_EMAIL}",
        )

    def test_refuse_existing_fixture(self) -> None:
        """An existing fixture path is preserved and rejected."""
        (self.root / f.FIXTURE_NAME).write_text("original")
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")
        self.assertEqual((self.root / f.FIXTURE_NAME).read_text(), "original")

    def test_refuse_different_baseline(self) -> None:
        """A mismatched expected baseline is refused before fixture creation."""
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, "f" * 40, "refs/heads/sliceb")

    def test_reject_commit_with_unexpected_fixture_blob(self) -> None:
        """Committed fixture blob is checked independently of working file bytes."""
        def commit_wrong_blob(root: Path, *args: str) -> bytes:
            if args and args[0] == "commit":
                fixture = root / f.FIXTURE_NAME
                fixture.write_bytes(b"unexpected committed fixture\n")
                result = git(root, *args).encode()
                fixture.write_bytes(f.FIXTURE_BYTES)
                return result
            return git(root, *args).encode()

        with patch.object(f, "_git", side_effect=commit_wrong_blob):
            with self.assertRaises(f.SliceBFixtureError):
                f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")


class Oc2tBridgeTests(unittest.TestCase):
    """PID 1 side of the OC2T contract, driven over pipes with a scripted TUI."""

    def setUp(self) -> None:
        """Create a clean Guest repository standing in for /workspace."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "sliceb")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "original").write_text("before\n")
        git(self.root, "add", "original")
        git(self.root, "commit", "-m", "base")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.line = f"OC2_SLICE_B_START {uuid.uuid4()} {self.head} refs/heads/sliceb {'a' * 64}\n"
        workspace = patch.object(e, "_WORKSPACE", self.root)
        workspace.start()
        self.addCleanup(workspace.stop)

    def run_with_tui(self, wire: Wire, tui: FakeTui) -> int:
        """Run the real entrypoint flow with only the TUI process replaced."""
        with patch.object(e, "_spawn_tui", return_value=tui):
            result = e.run_entrypoint(self.line, wire.channel)
        if not isinstance(result, int):
            raise AssertionError("entrypoint returned a non-integer exit code")
        return result

    def assert_no_fixture(self) -> None:
        self.assertFalse((self.root / f.FIXTURE_NAME).exists())
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.head)

    def test_frame_layout_and_bounds(self) -> None:
        """Frames are magic, one kind byte, big-endian u32 length, then payload."""
        self.assertEqual(
            e.encode_frame(CONTROL, b"TUI_EXIT 0"),
            b"OC2T\x02\x00\x00\x00\x0aTUI_EXIT 0",
        )
        self.assertEqual(e.encode_frame(TERMINAL, b""), b"OC2T\x01\x00\x00\x00\x00")
        self.assertEqual(len(e.encode_frame(TERMINAL, b"x" * 65536)), 9 + 65536)
        self.assertEqual(e.decode_frame_header(b"OC2T\x02\x00\x01\x00\x00"), (CONTROL, 65536))
        for kind, payload in ((0, b""), (3, b""), (CONTROL, b"x" * 65537), (CONTROL, "x")):
            with self.subTest(kind=kind), self.assertRaises(e.SliceBEntryRejected):
                e.encode_frame(kind, payload)
        for header in (b"OC2X\x02\x00\x00\x00\x00", b"OC2T\x00\x00\x00\x00\x00",
                       b"OC2T\x03\x00\x00\x00\x00", b"OC2T\x02\x00\x01\x00\x01",
                       b"OC2T\x02\x00\x00\x00", b"OC2T\x02\x00\x00\x00\x00\x00"):
            with self.subTest(header=header), self.assertRaises(e.SliceBEntryRejected):
                e.decode_frame_header(header)

    def test_ready_then_continue_runs_fixture(self) -> None:
        """Exit 0 is reported, READY follows, and only CONTINUE releases the fixture."""
        wire = Wire(self)
        wire.reply_after(READY, CONTINUE)
        self.assertEqual(self.run_with_tui(wire, FakeTui(b"bye")), 0)
        self.assertEqual(
            split_frames(wire.sent()),
            [(TERMINAL, b"bye"), (CONTROL, b"TUI_EXIT 0"), (CONTROL, b"FIXTURE_BOUNDARY_READY")],
        )
        self.assertEqual(
            git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
            f.FIXTURE_NAME,
        )
        self.assertEqual(git(self.root, "rev-parse", "HEAD^"), self.head)

    def test_rejected_continue_never_fixtures(self) -> None:
        """Every malformed, spoofed, partial, duplicated or absent CONTINUE fails closed."""
        body = b"FIXTURE_BOUNDARY_CONTINUE"
        replies: dict[str, bytes | None] = {
            "eof": None,
            "raw-text": body,
            "bad-magic": b"OC2X" + CONTINUE[4:],
            "unknown-kind": frame(3, body),
            "terminal-spoof": frame(TERMINAL, body),
            "oversized-length": b"OC2T\x02\x00\x01\x00\x01",
            "control-too-long": frame(CONTROL, b"x" * 65),
            "length-mismatch": b"OC2T\x02" + struct.pack(">I", len(body) - 1) + body,
            "other-control": READY,
            "tui-exit-echo": frame(CONTROL, b"TUI_EXIT 0"),
            "empty-control": frame(CONTROL, b""),
            "duplicate-continue": CONTINUE + CONTINUE,
            "trailing-byte": CONTINUE + b"\n",
        }
        for name, reply in replies.items():
            with self.subTest(name=name):
                wire = Wire(self)
                wire.reply_after(READY, reply)
                self.assertEqual(self.run_with_tui(wire, FakeTui()), 22)
                self.assertEqual(
                    split_frames(wire.sent()),
                    [(CONTROL, b"TUI_EXIT 0"), (CONTROL, b"FIXTURE_BOUNDARY_READY")],
                )
                self.assert_no_fixture()

    def test_partial_frame_then_eof_or_timeout_never_fixtures(self) -> None:
        """A truncated CONTINUE is never completed, skipped or accepted."""
        for name, close in (("eof", True), ("timeout", False)):
            with self.subTest(name=name):
                wire = Wire(self)
                wire.reply_after(READY, CONTINUE[:-3])
                with patch.object(e, "_CONTINUE_TIMEOUT_S", 0.3):
                    if close:
                        closer = threading.Timer(0.1, wire.eof)
                        closer.start()
                        self.addCleanup(closer.cancel)
                    self.assertEqual(self.run_with_tui(wire, FakeTui()), 22)
                self.assert_no_fixture()

    def test_missing_continue_times_out_without_fixture(self) -> None:
        """Silence after READY is bounded and fails closed."""
        wire = Wire(self)
        with patch.object(e, "_CONTINUE_TIMEOUT_S", 0.2):
            self.assertEqual(self.run_with_tui(wire, FakeTui()), 22)
        self.assertEqual(split_frames(wire.sent())[-1], (CONTROL, b"FIXTURE_BOUNDARY_READY"))
        self.assert_no_fixture()

    def test_input_before_ready_is_an_order_violation(self) -> None:
        """Bytes pending before READY cannot be a legitimate CONTINUE."""
        wire = Wire(self)
        wire.feed(CONTINUE)
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=0),
        ):
            self.assertEqual(e.run_entrypoint(self.line, wire.channel), 22)
        self.assertEqual(split_frames(wire.sent()), [(CONTROL, b"TUI_EXIT 0")])
        self.assert_no_fixture()

    def test_tui_output_is_never_control(self) -> None:
        """Control look-alikes printed by the TUI stay opaque terminal data."""
        spoof = b"x" + frame(CONTROL, b"TUI_EXIT 0") + READY + b"FIXTURE_BOUNDARY_CONTINUE OC2T"
        wire = Wire(self)
        self.assertEqual(self.run_with_tui(wire, FakeTui(spoof, exit_code=3)), 23)
        frames = split_frames(wire.sent())
        self.assertEqual(frames[-1], (CONTROL, b"TUI_EXIT 3"))
        self.assertEqual({kind for kind, _ in frames[:-1]}, {TERMINAL})
        self.assertEqual(b"".join(payload for _, payload in frames[:-1]), spoof)
        self.assert_no_fixture()

    def test_supervisor_input_during_tui_is_raw_tui_input(self) -> None:
        """A CONTINUE frame sent while the TUI runs is TUI input, not authorization."""
        wire = Wire(self)
        wire.feed(CONTINUE + b"q")
        tui = FakeTui(await_input=b"q")
        with patch.object(e, "_CONTINUE_TIMEOUT_S", 0.2):
            self.assertEqual(self.run_with_tui(wire, tui), 22)
        self.assertEqual(bytes(tui.received), CONTINUE + b"q")
        self.assertTrue(tui.closed)
        self.assert_no_fixture()

    def test_large_tui_output_survives_partial_writes(self) -> None:
        """Output beyond the pipe capacity is framed completely and in order."""
        output = bytes(range(256)) * 1024
        wire = Wire(self)
        wire.reply_after(READY, None)
        self.assertEqual(self.run_with_tui(wire, FakeTui(output, exit_code=9)), 23)
        frames = split_frames(wire.sent())
        self.assertEqual(frames[-1], (CONTROL, b"TUI_EXIT 9"))
        self.assertEqual(b"".join(payload for _, payload in frames[:-1]), output)

    def test_supervisor_detach_during_tui_kills_tui(self) -> None:
        """Losing the Supervisor mid-TUI kills the TUI and reports nothing as success."""
        wire = Wire(self)
        wire.eof()
        tui = FakeTui(hang=True)
        self.assertEqual(self.run_with_tui(wire, tui), 22)
        self.assertTrue(tui.killed)
        self.assertEqual(wire.sent(), b"")
        self.assert_no_fixture()

    def test_baseline_drift_after_continue_blocks_fixture(self) -> None:
        """Guest HEAD is rechecked after CONTINUE and before any fixture write."""
        wire = Wire(self)
        wire.reply_after(READY, CONTINUE)
        calls = []

        def check(expected: object, repo: Path) -> None:
            calls.append(repo)
            if len(calls) == 3:
                raise e.SliceBEntryRejected("drift")

        with patch.object(e, "_check_guest_baseline", side_effect=check):
            self.assertEqual(self.run_with_tui(wire, FakeTui()), 22)
        self.assertEqual(calls, [self.root] * 3)
        self.assert_no_fixture()

    def test_unobservable_tui_exit_is_never_reported(self) -> None:
        """An exit status outside 0..255 is rejected instead of being guessed."""
        for code in (None, -9, 256, True):
            with self.subTest(code=code):
                wire = Wire(self)
                with (
                    patch.object(e, "_check_guest_baseline"),
                    patch.object(e, "_run_tui", return_value=code),
                ):
                    self.assertEqual(e.run_entrypoint(self.line, wire.channel), 22)
                self.assertEqual(wire.sent(), b"")

    def test_startup_line_constraints_are_kept(self) -> None:
        """serve() keeps the bounded one-line startup gate and consumes nothing beyond it."""
        for name, data in (("no-newline-eof", self.line[:-1].encode()),
                           ("too-long", b"x" * 600 + b"\n"),
                           ("non-ascii", b"\xff" + self.line.encode())):
            with self.subTest(name=name):
                wire = Wire(self)
                wire.feed(data)
                wire.eof()
                with patch.object(e, "run_entrypoint") as run:
                    self.assertEqual(e.serve(wire.to_pid1_r, wire.from_pid1_w), 21)
                    run.assert_not_called()
                self.assertEqual(wire.sent(), b"")
        wire = Wire(self)
        with self.assertRaises(e.SliceBEntryRejected):
            e._read_start_line(0.05, wire.to_pid1_r)
        wire.feed(self.line.encode() + b"k")
        with patch.object(e, "run_entrypoint", return_value=0) as run:
            self.assertEqual(e.serve(wire.to_pid1_r, wire.from_pid1_w), 0)
        self.assertEqual(run.call_args.args[0], self.line)
        self.assertIsInstance(run.call_args.args[1], e.SupervisorChannel)
        self.assertEqual(os.read(wire.to_pid1_r, 16), b"k")


if __name__ == "__main__":
    unittest.main()
