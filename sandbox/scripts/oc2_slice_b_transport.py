from __future__ import annotations

import math
import os
import re
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import tty
from collections.abc import Callable
from pathlib import Path
from typing import Any

import oc2_supervisor as supervisor

_HEADER = struct.Struct(">4sBI")
_MAGIC = b"OC2T"
_MAX_FRAME = 64 * 1024
_CHUNK = 64 * 1024
_WRITE_TIMEOUT = 5.0
_REAP_TIMEOUT = 5.0
_CID_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class DockerAttachTransport:
    """Docker attach process and terminal I/O adapter for framed transport.

    Callers own the lifecycle: after a successful or partial ``attach``, call
    ``close`` to reap the attach process and ``restore_terminal`` to restore
    the caller's terminal settings. ``receive_frame`` returns ``None`` only
    when its polling timeout expires without receiving frame bytes.

    Operations raise ``InteractiveTransportError`` for invalid input, I/O,
    framing, timeout, or cleanup failures. ``InteractiveDetachedError`` means
    the Docker attach output stream reached EOF. A poisoned transport has
    encountered a framing or I/O condition that makes further stream use
    unsafe; subsequent frame operations are rejected.
    """

    def __init__(
        self,
        docker_path: str,
        *,
        _popen: Callable[..., Any] = subprocess.Popen,
        _stdin_fd: int | None = 0,
        _stdout_fd: int | None = 1,
        _isatty: Callable[[int], bool] = os.isatty,
        _get_terminal: Callable[[int], list[Any]] = termios.tcgetattr,
        _set_raw: Callable[[int], None] | None = None,
        _set_terminal: Callable[[int, int, list[Any]], None] = termios.tcsetattr,
    ) -> None:
        """Configure the attach adapter and optional terminal descriptors."""
        self._docker_path = supervisor._validate_docker_path(docker_path)
        self._popen = _popen
        self._stdin_fd = _stdin_fd
        self._stdout_fd = _stdout_fd
        self._isatty = _isatty
        self._get_terminal = _get_terminal
        self._set_raw = _set_raw if _set_raw is not None else self._default_set_raw
        self._set_terminal = _set_terminal
        self._container_id: str | None = None
        self._process: Any = None
        self._frame_buffer = bytearray()
        self._terminal_state: list[Any] | None = None
        self._poisoned = False
        self._config_dir: tempfile.TemporaryDirectory[str] | None = None

    @staticmethod
    def _default_set_raw(fd: int) -> None:
        tty.setraw(fd, termios.TCSANOW)

    def _check_container(self, container_id: str) -> None:
        if container_id != self._container_id or self._process is None:
            raise supervisor.InteractiveTransportError("attach identity mismatch")

    def _prepare_terminal(self) -> None:
        fd = self._stdin_fd
        if fd is None or not self._isatty(fd):
            return
        try:
            state = self._get_terminal(fd)
            self._terminal_state = state
            self._set_raw(fd)
        except (OSError, termios.error) as exc:
            raise supervisor.InteractiveTransportError("terminal raw mode failed") from exc

    def attach(self, container_id: str) -> None:
        """Start one Docker attach session for a full container ID."""
        if self._container_id is not None:
            raise supervisor.InteractiveTransportError("attach already attempted")
        if not isinstance(container_id, str) or _CID_PATTERN.fullmatch(container_id) is None:
            raise supervisor.InteractiveTransportError("full Container ID required")
        self._container_id = container_id
        self._prepare_terminal()
        self._config_dir = tempfile.TemporaryDirectory(prefix="oc2-docker-config-")
        directory = Path(self._config_dir.name)
        env = {"HOME": str(directory), "DOCKER_CONFIG": str(directory)}
        try:
            self._process = self._popen(
                [self._docker_path, "attach", container_id],
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
                close_fds=True,
                start_new_session=True,
                bufsize=0,
            )
            process_stdout = self._process.stdout
            process_stdin = self._process.stdin
            if process_stdout is None or process_stdin is None:
                raise OSError("attach pipes unavailable")
            os.set_blocking(process_stdout.fileno(), False)
            os.set_blocking(process_stdin.fileno(), False)
        except (OSError, subprocess.SubprocessError) as exc:
            self._cleanup_config()
            raise supervisor.InteractiveTransportError("docker attach failed") from exc

    def send_stdin(self, container_id: str, data: bytes) -> None:
        """Write bounded raw terminal input to the attached container.

        Raises ``InteractiveTransportError`` for an identity mismatch,
        invalid input, poisoned stream, or failed/partial write.
        """
        self._check_container(container_id)
        if self._poisoned or not isinstance(data, bytes) or len(data) > _MAX_FRAME:
            raise supervisor.InteractiveTransportError("attach input invalid")
        stream = self._process.stdin
        if stream is None:
            self._poisoned = True
            raise supervisor.InteractiveTransportError("attach input unavailable")
        view = memoryview(data)
        deadline = time.monotonic() + _WRITE_TIMEOUT
        try:
            while view:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                _, writable, _ = select.select([], [stream], [], remaining)
                if not writable:
                    raise TimeoutError
                written = os.write(stream.fileno(), view)
                if written <= 0:
                    raise OSError("attach input closed")
                view = view[written:]
        except (OSError, TimeoutError, ValueError) as exc:
            self._poisoned = True
            raise supervisor.InteractiveTransportError("attach input failed") from exc

    def _read_available(self, timeout: float) -> bytes | None:
        process = self._process
        if process is None or process.stdout is None:
            raise supervisor.InteractiveTransportError("attach output unavailable")
        try:
            ready, _, _ = select.select([process.stdout], [], [], timeout)
            if not ready:
                return None
            return os.read(process.stdout.fileno(), _CHUNK)
        except (OSError, ValueError) as exc:
            raise supervisor.InteractiveTransportError("attach output failed") from exc

    def _next_frame_length(self) -> int | None:
        if len(self._frame_buffer) < _HEADER.size:
            return None
        magic = bytes(self._frame_buffer[:4])
        kind = self._frame_buffer[4]
        size = int.from_bytes(self._frame_buffer[5:_HEADER.size], "big")
        if magic != _MAGIC or kind not in (1, 2) or size > _MAX_FRAME:
            self._poisoned = True
            raise supervisor.InteractiveTransportError("malformed OC2T frame")
        return _HEADER.size + size

    def receive_frame(self, container_id: str, timeout: float) -> bytes | None:
        """Return the next complete frame, or ``None`` on an empty poll timeout.

        A partial frame timing out, malformed/boundedness violations, or I/O
        failures raise ``InteractiveTransportError`` and poison the stream.
        Output EOF raises ``InteractiveDetachedError`` and also poisons it.
        """
        self._check_container(container_id)
        if self._poisoned:
            raise supervisor.InteractiveTransportError("attach stream is unusable")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise supervisor.InteractiveTransportError("invalid attach timeout")
        end = time.monotonic() + timeout
        while True:
            length = self._next_frame_length()
            if length is not None and len(self._frame_buffer) >= length:
                frame = bytes(self._frame_buffer[:length])
                del self._frame_buffer[:length]
                return frame
            remaining = end - time.monotonic()
            chunk = self._read_available(max(0.0, remaining))
            if chunk is None:
                if self._frame_buffer:
                    self._poisoned = True
                    raise supervisor.InteractiveTransportError("partial OC2T frame timed out")
                return None
            if not chunk:
                self._poisoned = True
                raise supervisor.InteractiveDetachedError("docker attach stream ended")
            self._frame_buffer.extend(chunk)
            if len(self._frame_buffer) > _CHUNK + _HEADER.size + _MAX_FRAME:
                self._poisoned = True
                raise supervisor.InteractiveTransportError("OC2T buffer exceeded bound")

    def read_terminal_input(self, timeout: float) -> bytes | None:
        """Read terminal input up to the timeout, or return ``None`` if idle."""
        fd = self._stdin_fd
        if fd is None:
            return None
        if not math.isfinite(timeout) or timeout < 0:
            raise supervisor.InteractiveTransportError("invalid terminal input timeout")
        try:
            ready, _, _ = select.select([fd], [], [], timeout)
            data = os.read(fd, _CHUNK) if ready else None
            if data is not None and len(data) > _MAX_FRAME:
                self._poisoned = True
                raise supervisor.InteractiveTransportError("terminal input exceeds bound")
            return data
        except supervisor.InteractiveTransportError:
            raise
        except (OSError, ValueError) as exc:
            raise supervisor.InteractiveTransportError("terminal input failed") from exc

    def write_terminal_output(self, data: bytes) -> None:
        """Write bounded output bytes to the caller's terminal."""
        fd = self._stdout_fd
        if fd is None:
            return
        if not isinstance(data, bytes) or len(data) > _MAX_FRAME:
            raise supervisor.InteractiveTransportError("terminal output exceeds bound")
        view = memoryview(data)
        try:
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("terminal output closed")
                view = view[written:]
        except OSError as exc:
            raise supervisor.InteractiveTransportError("terminal output failed") from exc

    def _cleanup_config(self) -> None:
        if self._config_dir is not None:
            self._config_dir.cleanup()
            self._config_dir = None

    def close(self, container_id: str) -> None:
        """Stop and reap the attached process; the caller must invoke this."""
        if self._container_id is None:
            return
        if container_id != self._container_id:
            raise supervisor.InteractiveTransportError("attach identity mismatch")
        process = self._process
        if process is None:
            return
        failure = False
        try:
            running = process.poll() is None
        except (OSError, subprocess.SubprocessError):
            running = True
            failure = True
        if running:
            pid = getattr(process, "pid", None)
            signalled = False
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1:
                try:
                    os.killpg(pid, signal.SIGTERM)
                    signalled = True
                except ProcessLookupError:
                    signalled = True
                except OSError:
                    signalled = False
            if not signalled:
                try:
                    process.terminate()
                except (OSError, ProcessLookupError):
                    failure = True
            try:
                process.wait(timeout=_REAP_TIMEOUT)
            except subprocess.TimeoutExpired:
                killed = False
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                        killed = True
                    except ProcessLookupError:
                        killed = True
                    except OSError:
                        killed = False
                try:
                    if not killed:
                        process.kill()
                    process.wait(timeout=_REAP_TIMEOUT)
                except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
                    failure = True
            except (OSError, subprocess.SubprocessError):
                try:
                    process.kill()
                    process.wait(timeout=_REAP_TIMEOUT)
                except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
                    failure = True
        try:
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        except OSError:
            failure = True
        self._process = None
        try:
            self._cleanup_config()
        except OSError:
            failure = True
        if failure:
            raise supervisor.InteractiveTransportError("docker attach cleanup unverified")

    def restore_terminal(self) -> None:
        """Restore saved terminal settings; the caller must invoke this."""
        if self._terminal_state is None or self._stdin_fd is None:
            return
        try:
            self._set_terminal(self._stdin_fd, termios.TCSADRAIN, self._terminal_state)
        except (OSError, termios.error) as exc:
            raise supervisor.InteractiveTransportError("terminal restore failed") from exc
        self._terminal_state = None
