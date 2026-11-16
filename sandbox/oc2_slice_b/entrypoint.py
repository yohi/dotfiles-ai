#!/usr/bin/env python3
"""Fixed Slice B image PID1: validated Host Baseline → TUI → offline fixture.

PID 1 speaks the Task 5 Supervisor's OC2T framing on the exact-container
attach channel. Everything PID 1 emits is a frame: TUI bytes travel only as
opaque terminal-data frames, and only PID 1 itself emits control frames. The
Supervisor sends the startup line and TUI input as raw bytes and exactly one
framed FIXTURE_BOUNDARY_CONTINUE after its own snapshot. Any unverified
channel state rejects before the fixture. This file alone does not authorize
TUI/Sandbox/Writer execution.
"""

from __future__ import annotations
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty
from typing import NoReturn, Protocol

_WORKSPACE = Path("/workspace")
_TUI = "/opt/oc2/bin/opencode"
_TOKEN = "OC2_SLICE_B_START"
_REF = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]{0,180}\Z")
_OID = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)

# OC2T wire contract; byte-for-byte the Task 5 Supervisor's interactive frame.
_FRAME_MAGIC = b"OC2T"
_FRAME_HEADER = struct.Struct(">4sBI")
_FRAME_TERMINAL = 1
_FRAME_CONTROL = 2
_MAX_FRAME_PAYLOAD = 64 * 1024
_MAX_INBOUND_CONTROL = 64
_CONTROL_READY = b"FIXTURE_BOUNDARY_READY"
_CONTROL_CONTINUE = b"FIXTURE_BOUNDARY_CONTINUE"

_CONTINUE_TIMEOUT_S = 60.0
_FRAME_WRITE_TIMEOUT_S = 30.0
_RELAY_POLL_S = 0.1
_RELAY_CHUNK = 4096
_TUI_INPUT_BACKLOG = 64 * 1024
_TUI_DRAIN_S = 2.0
_TUI_REAP_S = 5.0

_winch_pending = False


@dataclass(frozen=True)
class SliceBStartMessage:
    session_generation: str
    head_oid: str
    branch_ref: str
    manifest_sha256: str


class SliceBEntryRejected(RuntimeError):
    pass


def parse_start_line(line: str) -> SliceBStartMessage:
    """Parse and validate one startup frame's syntax, not Guest baseline equality."""
    try:
        wire = line.encode("ascii", "strict")
    except UnicodeError as e:
        raise SliceBEntryRejected("invalid startup encoding") from e
    if (
        len(wire) > 512
        or not wire.endswith(b"\n")
        or wire.count(b"\n") != 1
        or b"\r" in wire
        or b"\x00" in wire
    ):
        raise SliceBEntryRejected("invalid startup framing")
    parts = line[:-1].split(" ")
    if len(parts) != 5 or parts[0] != _TOKEN:
        raise SliceBEntryRejected("invalid startup token count")
    _, gen, oid, ref, digest = parts
    if not (
        _UUID4.fullmatch(gen)
        and _OID.fullmatch(oid)
        and _REF.fullmatch(ref)
        and _SHA.fullmatch(digest)
    ):
        raise SliceBEntryRejected("invalid startup identity")
    if ".." in ref or "//" in ref or ref.endswith(".lock"):
        raise SliceBEntryRejected("invalid startup branch")
    return SliceBStartMessage(gen, oid, ref, digest)


def encode_frame(kind: int, payload: bytes) -> bytes:
    """Encode one bounded OC2T terminal-data or control frame."""
    if (
        kind not in (_FRAME_TERMINAL, _FRAME_CONTROL)
        or not isinstance(payload, bytes)
        or len(payload) > _MAX_FRAME_PAYLOAD
    ):
        raise SliceBEntryRejected("invalid frame")
    return _FRAME_HEADER.pack(_FRAME_MAGIC, kind, len(payload)) + payload


def decode_frame_header(header: bytes) -> tuple[int, int]:
    """Validate one complete OC2T header and return its kind and payload size."""
    if not isinstance(header, bytes) or len(header) != _FRAME_HEADER.size:
        raise SliceBEntryRejected("malformed frame header")
    magic, kind, size = _FRAME_HEADER.unpack(header)
    if magic != _FRAME_MAGIC or kind not in (_FRAME_TERMINAL, _FRAME_CONTROL):
        raise SliceBEntryRejected("unrecognized frame")
    if size > _MAX_FRAME_PAYLOAD:
        raise SliceBEntryRejected("frame length exceeds bound")
    return kind, size


class SupervisorChannel:
    """PID 1 end of the attach channel: raw bytes in, OC2T frames out.

    Inbound bytes are never scanned for control tokens; the only inbound frame
    is the single one read by `recv_control` after PID 1 has sent READY.
    """

    def __init__(self, in_fd: int, out_fd: int) -> None:
        """Bind the two descriptors and make writes deadline-bounded."""
        self.in_fd = in_fd
        self._out_fd = out_fd
        os.set_blocking(out_fd, False)

    def _write_all(self, data: bytes) -> None:
        """Write every byte despite partial writes, or reject at the deadline."""
        end = time.monotonic() + _FRAME_WRITE_TIMEOUT_S
        view = memoryview(data)
        while view:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise SliceBEntryRejected("Supervisor channel write expired")
            _, ready, _ = select.select([], [self._out_fd], [], remaining)
            if not ready:
                continue
            try:
                written = os.write(self._out_fd, view)
            except BlockingIOError:
                continue
            view = view[written:]

    def send_terminal(self, data: bytes) -> None:
        """Send opaque TUI bytes as terminal-data frames only."""
        for start in range(0, len(data), _MAX_FRAME_PAYLOAD):
            chunk = data[start:start + _MAX_FRAME_PAYLOAD]
            self._write_all(encode_frame(_FRAME_TERMINAL, chunk))

    def send_control(self, payload: bytes) -> None:
        """Send one PID 1-originated control frame."""
        self._write_all(encode_frame(_FRAME_CONTROL, payload))

    def poll_input(self, timeout: float) -> bool:
        """Report whether inbound bytes or EOF are observable within timeout."""
        ready, _, _ = select.select([self.in_fd], [], [], max(0.0, timeout))
        return bool(ready)

    def read_input(self, size: int = _RELAY_CHUNK) -> bytes | None:
        """Read raw inbound bytes; None means nothing yet and b"" means EOF."""
        try:
            return os.read(self.in_fd, size)
        except BlockingIOError:
            return None

    def discard_terminal_input(self) -> None:
        """Drop raw TUI input that arrived before PID 1 announced the TUI exit.

        The Supervisor sends CONTINUE only in response to READY, so bytes
        already pending here cannot be a control frame.
        """
        dropped = 0
        while self.poll_input(0):
            data = self.read_input()
            if data is None:
                return
            if not data:
                raise SliceBEntryRejected("Supervisor detached before TUI exit report")
            dropped += len(data)
            if dropped > _MAX_FRAME_PAYLOAD:
                raise SliceBEntryRejected("terminal input exceeds bound")

    def _read_exact(self, size: int, end: float) -> bytes:
        """Read exactly size bytes before the deadline; partial data is rejected."""
        buf = bytearray()
        while len(buf) < size:
            remaining = end - time.monotonic()
            if remaining <= 0 or not self.poll_input(remaining):
                raise SliceBEntryRejected("Supervisor control frame expired")
            data = self.read_input(size - len(buf))
            if data is None:
                continue
            if not data:
                raise SliceBEntryRejected("Supervisor channel closed mid-frame")
            buf.extend(data)
        return bytes(buf)

    def recv_control(self, timeout: float) -> bytes:
        """Read exactly one bounded inbound control frame and return its payload."""
        end = time.monotonic() + timeout
        magic = self._read_exact(len(_FRAME_MAGIC), end)
        if magic != _FRAME_MAGIC:
            raise SliceBEntryRejected("unrecognized frame")
        rest = self._read_exact(_FRAME_HEADER.size - len(_FRAME_MAGIC), end)
        kind, size = decode_frame_header(magic + rest)
        if kind != _FRAME_CONTROL:
            raise SliceBEntryRejected("terminal data cannot act as control")
        if size > _MAX_INBOUND_CONTROL:
            raise SliceBEntryRejected("control frame exceeds bound")
        return self._read_exact(size, end)


def _read_start_line(deadline_secs: float = 30.0, fd: int = 0) -> str:
    """Read one bounded newline-terminated frame before the deadline."""
    end = time.monotonic() + deadline_secs
    buf = bytearray()
    while time.monotonic() < end and len(buf) <= 512:
        ready, _, _ = select.select([fd], [], [], max(0, end - time.monotonic()))
        if not ready:
            break
        try:
            x = os.read(fd, 1)
        except BlockingIOError:
            continue
        if not x:
            break
        buf.extend(x)
        if x == b"\n":
            break
    if not buf.endswith(b"\n") or len(buf) > 512:
        raise SliceBEntryRejected("missing/expired startup barrier")
    return buf.decode("ascii", "strict")


def _check_guest_baseline(
    expected: SliceBStartMessage, repo: Path = _WORKSPACE
) -> None:
    """Compare only Guest HEAD and symbolic ref with the supplied baseline identity."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }

    def git(*args: str) -> str:
        """Run a bounded read-only Git command in the selected Guest repository."""
        p = subprocess.run(
            ["git", *args],
            cwd=repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if p.returncode or len(p.stdout) > 256:
            raise SliceBEntryRejected("Guest baseline unavailable")
        return p.stdout.strip().decode("ascii")

    if (
        git("rev-parse", "--verify", "HEAD") != expected.head_oid
        or git("symbolic-ref", "HEAD") != expected.branch_ref
    ):
        raise SliceBEntryRejected("Guest HEAD/branch differs from Supervisor baseline")


class TuiSession(Protocol):
    """Running TUI as seen by the relay: one bidirectional fd plus exit state."""

    fd: int

    def poll(self) -> int | None: ...

    def kill(self) -> None: ...

    def resize(self) -> None: ...

    def close(self) -> None: ...


def _copy_winsize(src_fd: int, dst_fd: int) -> None:
    """Best-effort copy of the terminal window size; never a correctness input."""
    try:
        size = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\0" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, size)
    except OSError:
        pass


def _exec_tui(slave_fd: int, env: dict[str, str]) -> NoReturn:
    """Child only: adopt the inner PTY as controlling terminal and exec the TUI."""
    try:
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        for fd in (0, 1, 2):
            os.dup2(slave_fd, fd)
        os.chdir(_WORKSPACE)
        os.execve(_TUI, [_TUI, "--standalone"], env)
    except BaseException:
        pass
    os._exit(127)


class _TuiProcess:
    """The fixed TUI child on its own PTY; PID 1 keeps the master side."""

    def __init__(self, pid: int, fd: int) -> None:
        """Record the child PID and the PTY master descriptor."""
        self.pid = pid
        self.fd = fd
        self._code: int | None = None

    def poll(self) -> int | None:
        """Return the observed exit code (128+signal if signalled), else None."""
        if self._code is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid == self.pid:
                code = os.waitstatus_to_exitcode(status)
                self._code = code if code >= 0 else 128 - code
        return self._code

    def kill(self) -> None:
        """Kill the TUI session after a channel failure and reap it, bounded."""
        if self._code is None:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _wait_tui(self, _TUI_REAP_S)

    def resize(self) -> None:
        """Propagate the outer terminal size to the TUI's PTY."""
        _copy_winsize(0, self.fd)

    def close(self) -> None:
        """Release the PTY master."""
        os.close(self.fd)


def _spawn_tui(env: dict[str, str]) -> TuiSession:
    """Start the fixed standalone TUI on a fresh PTY with a sanitized env."""
    master, slave = os.openpty()
    try:
        _copy_winsize(0, slave)
        pid = os.fork()
        if pid == 0:
            _exec_tui(slave, env)
    except BaseException:
        os.close(master)
        raise
    finally:
        os.close(slave)
    return _TuiProcess(pid, master)


def _wait_tui(tui: TuiSession, timeout: float) -> int | None:
    """Poll for the TUI exit code until the deadline."""
    end = time.monotonic() + timeout
    while True:
        code = tui.poll()
        if code is not None or time.monotonic() >= end:
            return code
        time.sleep(0.05)


def _read_tui_output(fd: int) -> bytes | None:
    """Read TUI bytes; None means nothing yet and b"" means the TUI side closed."""
    try:
        return os.read(fd, _RELAY_CHUNK)
    except BlockingIOError:
        return None
    except OSError:
        # A PTY master reports EIO once every slave descriptor is closed.
        return b""


def _relay_tui(channel: SupervisorChannel, tui: TuiSession) -> int:
    """Shuttle raw input to the TUI and framed output back until it exits.

    Returns the exit code PID 1 itself observed. Supervisor detach or any
    channel failure kills the TUI and propagates so no fixture can follow.
    """
    global _winch_pending
    backlog = bytearray()
    drain_end: float | None = None
    try:
        os.set_blocking(tui.fd, False)
        while True:
            if _winch_pending:
                _winch_pending = False
                tui.resize()
            code = tui.poll()
            if code is not None and drain_end is None:
                drain_end = time.monotonic() + _TUI_DRAIN_S
            readers = [tui.fd]
            if code is None and len(backlog) < _TUI_INPUT_BACKLOG:
                readers.append(channel.in_fd)
            writers = [tui.fd] if backlog and code is None else []
            readable, writable, _ = select.select(
                readers, writers, [], _RELAY_POLL_S if code is None else 0
            )
            closed = False
            if tui.fd in readable:
                output = _read_tui_output(tui.fd)
                if output:
                    channel.send_terminal(output)
                closed = output == b""
            if code is not None:
                # Exit already observed: forward only what is still buffered.
                if (
                    closed
                    or tui.fd not in readable
                    or (drain_end is not None and time.monotonic() >= drain_end)
                ):
                    break
                continue
            if closed:
                code = _wait_tui(tui, _TUI_REAP_S)
                if code is None:
                    raise SliceBEntryRejected("TUI exit status unobservable")
                break
            if channel.in_fd in readable:
                data = channel.read_input()
                if data is not None and not data:
                    raise SliceBEntryRejected("Supervisor detached during TUI")
                backlog.extend(data or b"")
            if backlog and tui.fd in writable:
                try:
                    del backlog[:os.write(tui.fd, backlog)]
                except BlockingIOError:
                    pass
                except OSError:
                    # The TUI stopped reading; its exit is observed via poll().
                    backlog.clear()
        channel.discard_terminal_input()
        if code is None:
            raise SliceBEntryRejected("TUI exit status unobservable")
        return code
    except BaseException:
        tui.kill()
        raise
    finally:
        tui.close()


def _run_tui(channel: SupervisorChannel) -> int:
    """Run the fixed standalone TUI behind the framing relay; return its exit code."""
    # No credentials, no provider bootstrap, no untrusted repo entrypoint.
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    with tempfile.TemporaryDirectory(prefix="oc2-home-") as home:
        env["HOME"] = home
        return _relay_tui(channel, _spawn_tui(env))


def _report_tui_exit(channel: SupervisorChannel, code: int) -> None:
    """Tell the Supervisor the exit code PID 1 observed, zero or not."""
    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 255:
        raise SliceBEntryRejected("TUI exit status unobservable")
    channel.send_control(b"TUI_EXIT %d" % code)


def _supervisor_fixture_boundary(channel: SupervisorChannel) -> None:
    """Send READY, then block for exactly one Supervisor CONTINUE frame.

    No untrusted TUI bytes or Writer self-reported result can open this
    barrier: bytes that precede READY, a non-control or oversized frame, any
    other payload, EOF, timeout, or trailing bytes all reject before fixture.
    """
    if channel.poll_input(0):
        raise SliceBEntryRejected("Supervisor input preceded READY")
    channel.send_control(_CONTROL_READY)
    if channel.recv_control(_CONTINUE_TIMEOUT_S) != _CONTROL_CONTINUE:
        raise SliceBEntryRejected("unexpected Supervisor control frame")
    if channel.poll_input(0):
        raise SliceBEntryRejected("unexpected bytes after CONTINUE")


def run_entrypoint(start_line: str, channel: SupervisorChannel | None = None) -> int:
    """Run syntax, HEAD/ref checks, TUI and the framed boundary; return 0/22/23/24.

    The fixture runs only after PID 1 observed TUI exit 0, reported it, and
    received the Supervisor's CONTINUE. Status 22 covers expected
    validation/I/O/protocol/subprocess rejection (including a missing
    channel), 23 is the TUI's reported nonzero exit, and 24 is an unexpected
    failure.
    """
    try:
        data = parse_start_line(start_line)
        if channel is None:
            raise SliceBEntryRejected("trusted Supervisor channel unavailable")
        _check_guest_baseline(data, _WORKSPACE)
        tui_exit = _run_tui(channel)
        _report_tui_exit(channel, tui_exit)
        if tui_exit != 0:
            return 23
        _check_guest_baseline(data, _WORKSPACE)
        _supervisor_fixture_boundary(channel)
        _check_guest_baseline(data, _WORKSPACE)
        import offline_fixture

        offline_fixture.run_offline_fixture(_WORKSPACE, data.head_oid, data.branch_ref)
        return 0
    except (SliceBEntryRejected, OSError, ValueError, subprocess.SubprocessError):
        return 22
    except Exception:
        return 24


def serve(in_fd: int, out_fd: int) -> int:
    """Read the startup line from in_fd, then run the framed session; 21 on startup failure."""
    try:
        channel = SupervisorChannel(in_fd, out_fd)
        start = _read_start_line(30, in_fd)
    except (SliceBEntryRejected, UnicodeError, OSError):
        return 21
    return run_entrypoint(start, channel)


def _on_winch(signum: int, frame: object) -> None:
    """Note a window-size change for the relay loop."""
    global _winch_pending
    _winch_pending = True


def _prepare_outer_terminal() -> None:
    """Make the attach PTY 8-bit clean and keep stray stderr off the frame stream."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    if os.isatty(0):
        # TCSANOW: do not flush a startup line that has already arrived.
        tty.setraw(0, termios.TCSANOW)
        signal.signal(signal.SIGWINCH, _on_winch)


def main(argv: list[str] | None = None) -> int:
    """Dispatch only `run`; return 20 for other argv and 21 for startup-frame failure."""
    args = sys.argv[1:] if argv is None else argv
    if args != ["run"]:
        return 20
    try:
        _prepare_outer_terminal()
    except (OSError, termios.error):
        return 21
    return serve(0, 1)


if __name__ == "__main__":
    raise SystemExit(main())
