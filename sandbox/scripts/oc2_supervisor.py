"""OC2 Alternative A: Guest Supervisor offline integration.

This module wires the Writer lifecycle foundation (``oc2_writer``) to
concrete-but-injectable adapters on the Guest Linux side (Design R0.2
sections 6, 10.1, 10.4, 11-13):

* ``CliDockerRunner`` - a ``DockerRunner`` that only forwards the exact argv
  shapes produced by the ``oc2_writer`` builders to an injected transport,
  prefixed with an explicit absolute docker binary path.
* ``SubprocessTransport`` - the only real process transport (bounded
  ``Popen`` reads, overall deadline, process-group kill, bounded reap).  It
  is never constructed implicitly and no test starts a real process with it.
* ``GuestHostProbe`` - a read-only ``HostProbe`` for the Guest Linux ("host"
  in ``oc2_writer`` terms means the Guest, not the physical machine).  It
  reads through an injected ``GuestFs`` and an injected ``DockerRunner``.
* ``GuestSupervisor`` - a single-Session, single-Writer state machine around
  ``WriterLifecycle``.

Scope and non-goals (fixed by the Owner decision for this task):

* No Relay, no Collector, no Collection finalization, no ApplyAuthorization,
  no Host Apply and no Receipt v3 / Lease persistence.
* No wiring into ``oc2.py`` or the Launcher.
* No restart / relaunch / recovery / exec operation exists.  Process-restart
  Session recovery is NOT implemented.
* ``STOPPED_VERIFIED`` is a limited Writer-stop verdict.  It is NOT proof of
  Git tree immutability, Git transaction consistency or Collection
  finalization.

Unknown observations are always ``None`` and never converted to success.
Error messages are printable ASCII, use short stable codes and at most a
12 character container id prefix, and never contain environment variable
values, argv text or raw docker output.
"""
from __future__ import annotations

import dataclasses
import enum
import errno
import hashlib
import math
import os
import posixpath
import re
import select
import signal
import stat
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_slice_b_git import (
        POLICY as BUNDLE_POLICY,
        SCHEMA as BUNDLE_SCHEMA,
        GitBaseline,
        SliceBBundleManifestV1,
        SliceBGitRejected,
        _manifest_bytes,
    )
    from sandbox.scripts.oc2_slice_b_session import (
        SliceBSessionError,
        SliceBStartMessage,
        VerifiedGuestAuthority,
        build_start_message,
        is_verified_guest_authority,
    )
else:
    import oc2_writer as w
    from oc2_slice_b_git import (
        POLICY as BUNDLE_POLICY,
        SCHEMA as BUNDLE_SCHEMA,
        SliceBBundleManifestV1,
        SliceBGitRejected,
        GitBaseline,
        _manifest_bytes,
    )
    from oc2_slice_b_session import (
        SliceBSessionError,
        SliceBStartMessage,
        VerifiedGuestAuthority,
        build_start_message,
        is_verified_guest_authority,
    )

# --- Initial policy constants (not proven safe values) ---------------------

#: Upper bound (seconds) for any single docker command run by the adapter.
MAX_DOCKER_TIMEOUT_S = 120
#: Upper bound for docker stdout bytes; larger output fails closed.
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
#: Upper bound for a single GuestFs text read.
MAX_FS_READ_BYTES = 1024 * 1024

CGROUP_ROOT = '/sys/fs/cgroup'
PROC_ROOT = '/proc'
BOOT_ID_PATH = '/proc/sys/kernel/random/boot_id'

_DOCKER_VERBS = ('create', 'start', 'stop', 'kill', 'inspect', 'ps')
_CGROUP_COMPONENT_RE = re.compile(r'^[A-Za-z0-9_@:+.-]+$')
_PID_RE = re.compile(r'^[1-9][0-9]{0,9}$')
_ENV_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
_INACTIVE_STATUSES = frozenset({'created', 'exited', 'dead'})
_ACTIVE_STATUSES = frozenset({'running', 'paused', 'restarting', 'removing'})
_INTERACTIVE_FRAME_MAGIC = b'OC2T'
_INTERACTIVE_FRAME_HEADER = struct.Struct('>4sBI')
_INTERACTIVE_TERMINAL_FRAME = 1
_INTERACTIVE_CONTROL_FRAME = 2
_MAX_INTERACTIVE_FRAME_BYTES = 64 * 1024
_INTERACTIVE_POLL_S = 0.1
_POST_TUI_EXIT_TIMEOUT_S = 30.0
_POST_CONTINUE_TIMEOUT_S = 30.0


# --- Failure contract --------------------------------------------------------

class SupervisorError(w.WriterError):
    """Base class for Supervisor failures (still a ``WriterError``)."""


class SupervisorInputError(SupervisorError):
    """Invalid input (key, spec, argument, constructor parameter)."""


class DockerCommandError(SupervisorError):
    """docker exited non-zero or the transport failed to run it."""


class DockerTimeoutError(SupervisorError):
    """docker did not finish within the (clamped) timeout."""


class DockerOutputError(SupervisorError):
    """docker output was malformed, oversized, truncated or not UTF-8."""


class DockerCommandRejected(SupervisorError):
    """argv is not one of the allowed Writer lifecycle shapes."""


class InspectMismatchError(SupervisorError):
    """Writer inspect did not match the validated spec or expected state."""


class IdentityMismatchError(SupervisorError):
    """Container identity was not confirmed, changed, or is foreign."""


class ProbeUnavailableError(SupervisorError):
    """A Guest observation required for identity was unavailable."""


class StopVerificationError(SupervisorError):
    """Stop could not produce a valid verdict."""


class SupervisorStateError(SupervisorError):
    """Operation not allowed in the current Supervisor state."""


class InteractiveTransportError(SupervisorError):
    """The identity-bound raw TTY transport failed."""


class InteractiveDetachedError(InteractiveTransportError):
    """The attach stream reached EOF or was detached."""


class InteractiveProtocolError(SupervisorError):
    """The image-baked PID 1 frame was malformed or out of sequence."""


class FixtureSnapshotError(SupervisorError):
    """The trusted Supervisor snapshot could not be captured."""


class LaunchFailedError(SupervisorError):
    """Launch failed for a reason not covered by a more specific class."""


def _cid_tag(cid: object) -> str:
    """Return at most a 12 char prefix of a valid container id."""
    try:
        validated = w.validate_container_id(cid)
    except w.WriterError:
        return 'invalid'
    if not isinstance(validated, str):
        return 'invalid'
    return validated[:12]


# --- DockerRunner adapter ------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class TransportResult:
    """Raw transport result.  ``stdout`` is excluded from repr."""

    returncode: int
    stdout: bytes = dataclasses.field(repr=False)
    timed_out: bool
    truncated: bool


#: ``transport(argv, timeout, max_output) -> TransportResult``
Transport = Callable[[list[str], int, int], TransportResult]


def _validate_docker_path(docker_path: object) -> str:
    if not isinstance(docker_path, str) or not docker_path:
        raise SupervisorInputError('docker_path: expected non-empty string')
    if any(not 0x20 < ord(c) < 0x7F for c in docker_path):
        raise SupervisorInputError('docker_path: must be printable ASCII without spaces')
    if not docker_path.startswith('/') or docker_path.startswith('//'):
        raise SupervisorInputError('docker_path: must be absolute')
    if posixpath.normpath(docker_path) != docker_path:
        raise SupervisorInputError('docker_path: not in canonical form')
    if posixpath.basename(docker_path) != 'docker':
        raise SupervisorInputError('docker_path: basename must be docker')
    return docker_path


def _validate_docker_host(docker_host: object) -> str:
    if not isinstance(docker_host, str) or not docker_host.startswith('unix:///'):
        raise SupervisorInputError('docker_host: explicit Unix socket required')
    socket_path = docker_host.removeprefix('unix://')
    if '\x00' in socket_path or socket_path.startswith('//') \
            or posixpath.normpath(socket_path) != socket_path \
            or any(part in ('', '.', '..') for part in socket_path.split('/')[1:]):
        raise SupervisorInputError('docker_host: socket path not canonical')
    return docker_host


def _parse_create_spec(
    argv: list[str], authority: VerifiedGuestAuthority | None,
) -> w.WriterSpec:
    """Rebuild the WriterSpec that ``build_create_argv`` would turn into argv.

    Layout (from ``oc2_writer.build_create_argv``): fixed policy head that
    contains ``-v <repo>:/workspace:rw``, then exactly 5 ``--label`` pairs,
    then zero or more ``-e NAME=VALUE`` pairs, optional ``-i -t`` or legacy
    ``-t``, the image
    reference and the command.  The caller compares ``build_create_argv``
    of the result with ``argv`` for exact equality, so this parser only has
    to locate fields; all policy checks stay in ``oc2_writer``.
    """
    first_label = argv.index('--label')
    head = argv[:first_label]
    bind = head[head.index('-v') + 1]
    suffix = ':' + w.WRITER_WORKDIR + ':rw'
    if not bind.endswith(suffix):
        raise ValueError('bind')
    repo_source = bind[:-len(suffix)]
    labels: dict[str, str] = {}
    i = first_label
    for _ in range(5):
        if argv[i] != '--label':
            raise ValueError('label')
        name, value = argv[i + 1].split('=', 1)
        labels[name] = value
        i += 2
    env: list[tuple[str, str]] = []
    while argv[i] == '-e':
        name, value = argv[i + 1].split('=', 1)
        env.append((name, value))
        i += 2
    stdin_open = False
    if argv[i] == '-i':
        stdin_open = True
        i += 1
    tty = False
    if argv[i] == '-t':
        tty = True
        i += 1
    image_arg = argv[i]
    command = tuple(argv[i + 1:])
    key = w.WriterSessionKey(labels[w.LABEL_WORKSPACE], labels[w.LABEL_SANDBOX],
                             labels[w.LABEL_GENERATION])
    if authority is None:
        return w.WriterSpec(key=key, image_ref=image_arg, repo_source=repo_source,
                            command=command, env=tuple(env), tty=tty,
                            stdin_open=stdin_open)
    if not is_verified_guest_authority(authority) or image_arg != authority.image_config_id:
        raise ValueError('unverified Slice B image Config ID')
    return w.WriterSpec(
        key=key,
        image_ref=None,
        repo_source=repo_source,
        command=command,
        env=tuple(env),
        tty=tty,
        stdin_open=stdin_open,
        image_identity_mode=w.WriterImageIdentityMode.SLICE_B_CONFIG_ID,
        image_config_id=authority.image_config_id,
        image_record_sha256=authority.image_record_sha256,
        runtime_sha256=authority.runtime_sha256,
    )


def _allowed_shape(
    argv: list[str], authority: VerifiedGuestAuthority | None = None,
) -> bool:
    """Return True only for the exact argv shapes of the oc2_writer builders."""
    verb = argv[1]
    if authority is not None and verb != 'create':
        return False
    if verb == 'ps':
        return bool(tuple(argv) == w.LIST_ALL_ARGV)
    if verb == 'start':
        return bool(len(argv) == 3 and w.build_start_argv(argv[2]) == argv)
    if verb == 'kill':
        return bool(len(argv) == 5 and w.build_kill_argv(argv[4]) == argv)
    if verb == 'inspect':
        return bool(len(argv) == 5 and w.build_inspect_argv(argv[4]) == argv)
    if verb == 'stop':
        if len(argv) != 5 or not re.fullmatch(r'[1-9][0-9]{0,2}', argv[3]):
            return False
        return bool(w.build_stop_argv(argv[4], int(argv[3])) == argv)
    if verb == 'create':
        spec = _parse_create_spec(argv, authority)
        return bool(w.build_create_argv(spec, authority=authority) == argv)
    return False


class CliDockerRunner:
    """``DockerRunner`` that forwards only Writer lifecycle argv shapes.

    * ``docker_path`` is explicit, absolute and canonical; no PATH lookup,
      no environment guessing, no implicit ``DOCKER_HOST``.
    * Only argv lists produced by the ``oc2_writer`` builders are allowed
      (create / start / stop / kill / inspect with a 64 hex id, and
      ``ps -a -q --no-trunc``).  Anything else is rejected before the
      transport is called.
    * Timeout is clamped to ``max_timeout``; output above ``max_output`` or a
      truncated transport result fails closed.
    * Non-zero exit, timeout and output problems raise ``SupervisorError``
      subclasses whose messages never contain argv text, environment
      values, stdout or stderr.  A successful call returns ``(0, text)``.
    """

    def __init__(self, docker_path: str, transport: Transport, *, docker_host: str,
                 max_timeout: int = MAX_DOCKER_TIMEOUT_S,
                 max_output: int = MAX_OUTPUT_BYTES) -> None:
        self._docker_path = _validate_docker_path(docker_path)
        self._docker_host = _validate_docker_host(docker_host)
        if not callable(transport):
            raise SupervisorInputError('transport: expected callable')
        for value in (max_timeout, max_output):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SupervisorInputError('limits: expected positive integers')
        self._transport = transport
        self._max_timeout = max_timeout
        self._max_output = max_output

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: int,
    ) -> tuple[int, str]:
        args = self._check_argv(argv)
        return self._run_checked(args, timeout)

    def run_authorized(
        self,
        argv: Sequence[str],
        *,
        timeout: int,
        image_authority: VerifiedGuestAuthority,
    ) -> tuple[int, str]:
        args = self._check_argv(argv, image_authority)
        return self._run_checked(args, timeout)

    def _run_checked(self, args: list[str], timeout: int) -> tuple[int, str]:
        verb = args[1]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise SupervisorInputError('docker timeout: expected positive integer')
        effective = min(timeout, self._max_timeout)
        full = [self._docker_path, '--host', self._docker_host] + args[1:]
        # The transport call is deliberately outside any ``except`` block so
        # no exception context (which may carry argv/env text) is chained.
        failed = False
        result: Any = None
        try:
            result = self._transport(full, effective, self._max_output)
        except Exception:
            failed = True
        if failed:
            raise DockerCommandError(f'docker {verb}: transport failed')
        return 0, self._check_result(verb, result)

    @staticmethod
    def _check_argv(
        argv: object,
        image_authority: VerifiedGuestAuthority | None = None,
    ) -> list[str]:
        if not isinstance(argv, (list, tuple)) or len(argv) < 2:
            raise DockerCommandRejected('docker argv rejected: not an argv list')
        args = list(argv)
        if any(not isinstance(a, str) or '\x00' in a for a in args):
            raise DockerCommandRejected('docker argv rejected: non-string element')
        if args[0] != 'docker' or args[1] not in _DOCKER_VERBS:
            raise DockerCommandRejected('docker argv rejected: verb not allowed')
        verb = args[1]
        ok = False
        try:
            ok = _allowed_shape(args, image_authority)
        except Exception:
            ok = False
        if not ok:
            raise DockerCommandRejected(f'docker argv rejected: {verb} shape not allowed')
        return args

    def _check_result(self, verb: str, result: object) -> str:
        if not isinstance(result, TransportResult) \
                or isinstance(result.returncode, bool) \
                or not isinstance(result.returncode, int) \
                or not isinstance(result.stdout, bytes) \
                or not isinstance(result.timed_out, bool) \
                or not isinstance(result.truncated, bool):
            raise DockerOutputError(f'docker {verb}: malformed transport result')
        if result.timed_out:
            raise DockerTimeoutError(f'docker {verb}: timed out')
        if result.truncated or len(result.stdout) > self._max_output:
            raise DockerOutputError(f'docker {verb}: output limit exceeded')
        if result.returncode != 0:
            raise DockerCommandError(f'docker {verb}: exited rc={result.returncode}')
        text: str | None
        try:
            text = result.stdout.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            text = None
        if text is None or '\x00' in text:
            raise DockerOutputError(f'docker {verb}: output is not valid text')
        return text


class TransportReapError(DockerCommandError):
    """The transport child could not be killed and reaped within the bound.

    Raised instead of returning a result: the command outcome is unknown and
    a child (or its process group) may still be alive.
    """


#: Largest single read from the child's stdout pipe.
_READ_CHUNK_BYTES = 64 * 1024
#: Upper bound (seconds) for reaping a killed child before failing closed.
_REAP_TIMEOUT_S = 5

#: ``reader(stream, size, timeout_s) -> bytes | None``: ``None`` means no
#: data became readable within ``timeout_s``; ``b''`` means EOF.  Must never
#: return more than ``size`` bytes.
Reader = Callable[[Any, int, float], 'bytes | None']


def _poll_read(stream: Any, size: int, timeout_s: float) -> bytes | None:
    """Wait at most ``timeout_s`` for ``stream`` and read at most ``size`` bytes.

    Uses ``poll`` (no FD_SETSIZE limit) and a single ``os.read`` so that no
    more than ``size`` bytes are ever pulled from the pipe per call.
    """
    fd = stream.fileno()
    poller = select.poll()
    poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    if not poller.poll(max(0, math.ceil(timeout_s * 1000))):
        return None
    return os.read(fd, size)


class SubprocessTransport:
    """Real transport: ``subprocess.Popen`` with ``shell=False``, bounded reads.

    Never constructed implicitly.  The child environment is exactly the
    fixed mapping given to the constructor (default ``{}``); nothing is
    inherited from the caller.  Names starting with ``DOCKER_`` are rejected
    (provisional: keeps the daemon/context/config selection at docker's
    built-in default instead of redirecting it).  stdin is ``/dev/null`` and
    stderr is discarded and never returned.

    Bounded output: stdout is read in chunks of at most ``_READ_CHUNK_BYTES``
    and never more than ``max_output + 1`` bytes are retained in total.  As
    soon as more than ``max_output`` bytes have been read, reading stops,
    the child is killed and the result is ``truncated=True`` (``stdout``
    holds the first ``max_output`` bytes) so ``CliDockerRunner`` fails
    closed.  ``communicate()`` is deliberately not used.

    Timeout: ``timeout`` is one overall wall-clock (monotonic) deadline that
    covers reading and waiting for exit.  On expiry the child is killed and
    the result is ``timed_out=True`` with empty stdout.

    Kill and reap: the child is started with ``start_new_session=True`` so
    it leads its own process group (pgid == pid); kill sends SIGKILL to that
    whole group, so grandchildren in the group do not linger.  The group is
    signalled only while the child is still unreaped (its pid, and thus the
    pgid, cannot be recycled yet).  Grandchildren that leave the group (new
    session / setpgid) are outside this bound.  On the normal EOF path the
    group is not signalled.  After a kill the pipe is closed and the child
    is reaped with a ``_REAP_TIMEOUT_S`` bound; if it cannot be reaped,
    ``TransportReapError`` is raised instead of returning a result.

    Child start failure and read failure raise ``DockerCommandError``.  A
    non-zero exit is returned as ``returncode``.  Error messages never
    contain argv text, environment values, stdout or stderr.

    ``_popen``, ``_clock``, ``_reader`` and ``_killpg`` are private test
    seams (process factory, monotonic clock, bounded pipe reader, process
    group signal); production callers must not pass them.
    """

    def __init__(self, env: Mapping[str, str] | None = None, *,
                 _popen: Callable[..., Any] | None = None,
                 _clock: Callable[[], float] | None = None,
                 _reader: Reader | None = None,
                 _killpg: Callable[[int, int], None] | None = None) -> None:
        fixed: dict[str, str] = {}
        for name, value in dict(env or {}).items():
            if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
                raise SupervisorInputError('transport env: malformed name')
            if name.upper().startswith('DOCKER_'):
                raise SupervisorInputError('transport env: DOCKER_* not allowed')
            if not isinstance(value, str) or '\x00' in value:
                raise SupervisorInputError('transport env: invalid value')
            fixed[name] = value
        self._env = fixed
        self._popen = _popen if _popen is not None else subprocess.Popen
        self._clock = _clock if _clock is not None else time.monotonic
        self._reader = _reader if _reader is not None else _poll_read
        self._killpg = _killpg if _killpg is not None else os.killpg

    def __call__(self, argv: list[str], timeout: int, max_output: int) -> TransportResult:
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv) \
                or not argv[0].startswith('/'):
            raise SupervisorInputError('transport argv: invalid')
        for value in (timeout, max_output):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SupervisorInputError('transport limits: expected positive integers')
        deadline = self._clock() + timeout
        proc: Any = None
        try:
            proc = self._popen(
                list(argv), shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=dict(self._env), close_fds=True, start_new_session=True)
        except Exception:
            proc = None
        if proc is None:
            raise DockerCommandError('transport: process start failed')

        try:
            buf, outcome = self._read_bounded(proc, deadline, max_output)
            if outcome == 'eof':
                self._close(proc)
                remaining = deadline - self._clock()
                rc: Any = None
                if remaining > 0:
                    try:
                        rc = proc.wait(timeout=remaining)
                    except Exception:
                        rc = None
                if isinstance(rc, int) and not isinstance(rc, bool):
                    return TransportResult(rc, bytes(buf), False, False)
                outcome = 'timeout'  # exited stdout but not the process in time
            reaped = self._kill_and_reap(proc)
            if not reaped:
                raise TransportReapError('transport: child not reaped')
            if outcome == 'read-error':
                raise DockerCommandError('transport: read failed')
            if outcome == 'truncated':
                rc = proc.returncode
                if isinstance(rc, bool) or not isinstance(rc, int):
                    rc = -1
                return TransportResult(rc, bytes(buf[:max_output]), False, True)
            return TransportResult(-1, b'', True, False)
        except KeyboardInterrupt:
            self._close(proc)
            if getattr(proc, 'returncode', None) is None:
                try:
                    self._kill_and_reap(proc)
                except KeyboardInterrupt:
                    pass
            raise

    def _read_bounded(self, proc: Any, deadline: float,
                      max_output: int) -> tuple[bytearray, str]:
        """Read stdout until EOF, overflow, deadline or error.

        Returns ``(buffer, outcome)`` with outcome ``eof``, ``truncated``,
        ``timeout`` or ``read-error``.  ``len(buffer) <= max_output + 1``.
        """
        buf = bytearray()
        limit = max_output + 1
        stream = getattr(proc, 'stdout', None)
        if stream is None:
            return buf, 'read-error'
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return buf, 'timeout'
            size = min(limit - len(buf), _READ_CHUNK_BYTES)
            try:
                chunk = self._reader(stream, size, remaining)
            except Exception:
                return buf, 'read-error'
            if chunk is None:
                continue
            if not isinstance(chunk, (bytes, bytearray)) or len(chunk) > size:
                return buf, 'read-error'
            if not chunk:
                return buf, 'eof'
            buf += chunk
            if len(buf) > max_output:
                return buf, 'truncated'

    @staticmethod
    def _close(proc: Any) -> None:
        stream = getattr(proc, 'stdout', None)
        if stream is None:
            return
        try:
            stream.close()
        except Exception:
            pass

    def _kill_and_reap(self, proc: Any) -> bool:
        """SIGKILL the child's process group, close the pipe, bounded reap.

        At most one group signal, one direct kill fallback and one wait.
        Returns True only if the child was reaped within the bound.
        """
        signalled = False
        pid = getattr(proc, 'pid', None)
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1:
            try:
                self._killpg(pid, signal.SIGKILL)
                signalled = True
            except ProcessLookupError:
                signalled = True  # group already gone
            except Exception:
                signalled = False
        if not signalled:
            try:
                proc.kill()
            except Exception:
                pass
        self._close(proc)
        try:
            proc.wait(timeout=_REAP_TIMEOUT_S)
        except Exception:
            return False
        rc = getattr(proc, 'returncode', None)
        return isinstance(rc, int) and not isinstance(rc, bool)


# --- Guest filesystem abstraction ----------------------------------------------

class GuestFsAbsent(Exception):
    """The path definitely does not exist (ENOENT / ESRCH)."""


class GuestFsUnknown(Exception):
    """The path state could not be determined (never treated as absent)."""


@dataclasses.dataclass(frozen=True)
class FsStat:
    """No-follow stat result.  ``kind`` is dir, file, symlink or other."""

    inode: int
    kind: str


class GuestFs(Protocol):
    """Read-only, no-follow Guest filesystem access.

    Every method raises ``GuestFsAbsent`` when the final path definitely does
    not exist and ``GuestFsUnknown`` for any other failure.  Implementations
    must not follow a symlink in the final component.
    """

    def read_text(self, path: str) -> str: ...

    def lstat(self, path: str) -> FsStat: ...

    def listdir(self, path: str) -> tuple[str, ...]: ...


def _check_abs_path(path: object) -> str:
    if not isinstance(path, str) or '\x00' in path or not path.startswith('/') \
            or path.startswith('//') or posixpath.normpath(path) != path:
        raise GuestFsUnknown('invalid path')
    return path


class LocalGuestFs:
    """``GuestFs`` over the local Linux filesystem (read-only, no-follow).

    Intended to run inside the Guest.  Reads use ``O_NOFOLLOW`` on the final
    component; callers that need intermediate components checked must walk
    them with ``lstat`` (``GuestHostProbe`` does this for cgroup paths).
    """

    _ABSENT = (errno.ENOENT, errno.ESRCH)

    def read_text(self, path: str) -> str:
        path = _check_abs_path(path)
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        data, err = b'', 0
        try:
            fd = os.open(path, flags)
            try:
                data = os.read(fd, MAX_FS_READ_BYTES + 1)
            finally:
                os.close(fd)
        except OSError as exc:
            err = exc.errno or -1
        self._raise_for(err)
        if len(data) > MAX_FS_READ_BYTES:
            raise GuestFsUnknown('read limit exceeded')
        try:
            return data.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            raise GuestFsUnknown('not utf-8') from None

    def lstat(self, path: str) -> FsStat:
        path = _check_abs_path(path)
        st, err = None, 0
        try:
            st = os.lstat(path)
        except OSError as exc:
            err = exc.errno or -1
        self._raise_for(err)
        if st is None:
            raise GuestFsUnknown('unavailable')
        if stat.S_ISLNK(st.st_mode):
            kind = 'symlink'
        elif stat.S_ISDIR(st.st_mode):
            kind = 'dir'
        elif stat.S_ISREG(st.st_mode):
            kind = 'file'
        else:
            kind = 'other'
        return FsStat(int(st.st_ino), kind)

    def listdir(self, path: str) -> tuple[str, ...]:
        path = _check_abs_path(path)
        if self.lstat(path).kind != 'dir':
            raise GuestFsUnknown('not a directory')
        names: list[str] = []
        err = 0
        try:
            names = os.listdir(path)
        except OSError as exc:
            err = exc.errno or -1
        self._raise_for(err)
        return tuple(names)

    def _raise_for(self, err: int) -> None:
        if not err:
            return
        if err in self._ABSENT:
            raise GuestFsAbsent('absent')
        raise GuestFsUnknown('unavailable')


# --- HostProbe adapter -----------------------------------------------------------

def _cgroup_candidates(cid: str) -> tuple[str, ...]:
    """Documented cgroup v2 paths of a container (relative to CGROUP_ROOT).

    systemd driver: ``/system.slice/docker-<id>.scope``;
    cgroupfs driver: ``/docker/<id>``.  Derived only from a validated id.
    """
    return (f'/system.slice/docker-{cid}.scope', f'/docker/{cid}')


def _safe_cgroup_rel(rel: object) -> list[str] | None:
    """Return path components of a safe cgroup-relative path, else None."""
    if not isinstance(rel, str) or not rel.startswith('/') or rel.startswith('//') \
            or '\x00' in rel or posixpath.normpath(rel) != rel or rel == '/':
        return None
    parts = rel[1:].split('/')
    for part in parts:
        if part in ('', '.', '..') or not _CGROUP_COMPONENT_RE.match(part):
            return None
    return parts


class GuestHostProbe:
    """Read-only ``HostProbe`` for the Guest Linux.

    cgroup source decision: the primary source is the kernel view
    ``/proc/<State.Pid>/cgroup`` (cgroup v2 ``0::<path>`` line) of the pid
    reported by ``docker inspect``; it is cross-checked against the
    documented systemd / cgroupfs scope paths derived from the validated
    64 hex id.  Disagreement, a pid/StartedAt change across the read, a
    non-Writer uid on that pid, a symlink component, ``..``, or any unknown
    yields ``None``.  Container names and Writer-controlled paths are never
    trusted.

    A successful ``cgroup_inode`` also records that this probe's ``/proc``
    shows the Writer's processes (same pid namespace as dockerd, no hiding
    of uid 10001 processes).  ``observe`` only reports cgroup absence and the
    Writer uid process scan for container ids confirmed this way; otherwise
    those sub-observations are ``None``.

    ``rw_mount_holders`` enumerates ALL containers (``ps -a -q --no-trunc``)
    and inspects each.  That is the docker daemon's view only, so its
    result is fail-closed by observation scope:

    * non-empty tuple - RW holders actually observed (Docker-visible
      containers whose bind source equals, contains or is inside the repo
      path); verification is blocked.
    * ``None`` - absence NOT established: enumeration / inspect failure,
      unknown mount or status, or a Docker-side count of zero.  Docker
      cannot see non-docker processes, other runtimes or other mount
      namespaces, and no independent kernel-side observation is
      implemented here, so Docker-side zero is never reported as ``()``.
    * ``()`` - reserved for an independent, sufficient kernel-side
      observation that no holder exists in the required scope.  This probe
      never returns it (``/proc/self/mountinfo`` does not cover other mount
      namespaces, and a per-pid mountinfo scan is blind under hidepid or a
      separate pid namespace), so kernel-wide absence cannot be proven and
      a ``GuestHostProbe`` alone never yields ``STOPPED_VERIFIED``.
    """

    def __init__(self, runner: w.DockerRunner, fs: GuestFs,
                 repo_source: str | None = None) -> None:
        if repo_source is not None:
            if not isinstance(repo_source, str) or not repo_source.startswith('/') \
                    or repo_source.startswith('//') or '\x00' in repo_source \
                    or posixpath.normpath(repo_source) != repo_source:
                raise SupervisorInputError('repo_source: expected canonical absolute path')
        self._runner = runner
        self._fs = fs
        self._repo_source = repo_source
        self._cgroup_paths: dict[str, str] = {}
        self._confirmed: set[str] = set()

    # -- docker helpers (unknown => None) --

    def _docker(self, argv: Sequence[str]) -> str | None:
        try:
            result = self._runner.run(list(argv), timeout=w.DOCKER_CMD_TIMEOUT_S)
        except Exception:
            return None
        if not isinstance(result, tuple) or len(result) != 2:
            return None
        rc, out = result
        if rc != 0 or not isinstance(out, str):
            return None
        return out

    def _inspect(self, cid: str) -> dict[str, Any] | None:
        out = self._docker(w.build_inspect_argv(cid))
        if out is None:
            return None
        try:
            info: dict[str, Any] = w.parse_inspect_output(out)
        except w.WriterError:
            return None
        if info.get('Id') != cid:
            return None
        return info

    # -- boot id --

    def boot_id(self) -> str | None:
        try:
            value = self._fs.read_text(BOOT_ID_PATH).strip()
        except Exception:
            return None
        return value if w._is_canonical_uuid(value) else None

    # -- cgroup --

    def _running_pid(self, info: Mapping[str, Any]) -> tuple[int, str] | None:
        """Return (PID, StartedAt) only for a verified running process.

        ``None`` means the inspect is malformed, the process is not running,
        or its identity is incomplete; it never implies that the process is
        absent. Callers must treat that indeterminate state as failure.
        """
        state = info.get('State')
        if not isinstance(state, Mapping):
            return None
        pid, started = state.get('Pid'), state.get('StartedAt')
        if state.get('Running') is not True or isinstance(pid, bool) \
                or not isinstance(pid, int) or pid <= 0 or not isinstance(started, str) \
                or not started:
            return None
        return pid, started

    def _proc_cgroup_rel(self, pid: int) -> str | None:
        try:
            text = self._fs.read_text(f'{PROC_ROOT}/{pid}/cgroup')
        except Exception:
            return None
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) != 1 or not lines[0].startswith('0::'):
            return None
        return lines[0][3:]

    def _proc_uids(self, pid: int | str) -> tuple[int, ...]:
        """Return (real, effective, saved, fs) uids; raise GuestFs* on failure."""
        text = self._fs.read_text(f'{PROC_ROOT}/{pid}/status')
        for line in text.splitlines():
            if line.startswith('Uid:'):
                fields = line[4:].split()
                if len(fields) != 4 or not all(f.isdigit() for f in fields):
                    break
                return tuple(int(f) for f in fields)
        raise GuestFsUnknown('malformed status')

    def _walk_cgroup(self, rel: str) -> tuple[str, int | None]:
        """Return ('present', inode) / ('absent', None) / ('unknown', None).

        Every component is checked with no-follow ``lstat``; a symlink or
        non-directory component is unknown.  Absence of the final component
        is trusted only if its parent directory is a readable directory
        whose listing does not contain the name.
        """
        parts = _safe_cgroup_rel(rel)
        if parts is None:
            return 'unknown', None
        cur = CGROUP_ROOT
        try:
            if self._fs.lstat(cur).kind != 'dir':
                return 'unknown', None
        except Exception:
            return 'unknown', None
        for index, part in enumerate(parts):
            parent, cur = cur, cur + '/' + part
            try:
                st = self._fs.lstat(cur)
            except GuestFsAbsent:
                if index != len(parts) - 1:
                    return 'unknown', None
                try:
                    listing = self._fs.listdir(parent)
                except Exception:
                    return 'unknown', None
                if not isinstance(listing, tuple) or part in listing:
                    return 'unknown', None
                return 'absent', None
            except Exception:
                return 'unknown', None
            if not isinstance(st, FsStat) or st.kind != 'dir':
                return 'unknown', None
            if index == len(parts) - 1:
                if isinstance(st.inode, bool) or not isinstance(st.inode, int) \
                        or st.inode <= 0:
                    return 'unknown', None
                return 'present', st.inode
        return 'unknown', None

    def cgroup_inode(self, cid: str) -> int | None:
        try:
            return self._cgroup_inode(cid)
        except Exception:
            return None

    def _cgroup_inode(self, cid: str) -> int | None:
        try:
            cid = w.validate_container_id(cid)
        except w.WriterError:
            return None
        before = self._inspect(cid)
        running = self._running_pid(before) if before is not None else None
        if running is None:
            return None
        pid, started = running
        rel = self._proc_cgroup_rel(pid)
        if rel is None or rel not in _cgroup_candidates(cid):
            return None
        try:
            uids = self._proc_uids(pid)
        except Exception:
            return None
        if any(u != w.WRITER_UID for u in uids):
            return None
        status, inode = self._walk_cgroup(rel)
        if status != 'present':
            return None
        after = self._inspect(cid)
        if after is None or self._running_pid(after) != (pid, started):
            return None
        self._cgroup_paths[cid] = rel
        self._confirmed.add(cid)
        return inode

    # -- observe --

    def observe(self, identity: w.WriterIdentity) -> w.StopObservation:
        cid: str | None = None
        if isinstance(identity, w.WriterIdentity):
            try:
                cid = w.validate_container_id(identity.container_id)
            except w.WriterError:
                cid = None
        if cid is None:
            return w.StopObservation(None, None, None, None)
        return w.StopObservation(
            cgroup_exists=self._guard(self._cgroup_exists, cid),
            writer_uid_pids=self._guard(self._writer_uid_pids, cid),
            rw_mount_holders=self._guard(self._rw_mount_holders),
            boot_id=self.boot_id(),
        )

    @staticmethod
    def _guard(func: Callable[..., Any], *args: Any) -> Any:
        """Return an observation, or ``None`` when its probe raises.

        A rejected or failed observation is not evidence of absence, so
        consumers must fail closed on ``None``.
        """
        try:
            return func(*args)
        except Exception:
            return None

    def _cgroup_exists(self, cid: str) -> bool | None:
        rel = self._cgroup_paths.get(cid)
        if rel is None:
            return None
        status, _ = self._walk_cgroup(rel)
        if status == 'present':
            return True
        if status == 'absent':
            return False
        return None

    def _writer_uid_pids(self, cid: str) -> tuple[int, ...] | None:
        if cid not in self._confirmed:
            return None
        names = self._fs.listdir(PROC_ROOT)
        if not isinstance(names, tuple):
            return None
        found: list[int] = []
        for name in names:
            if not isinstance(name, str) or not _PID_RE.match(name):
                continue
            try:
                uids = self._proc_uids(name)
            except GuestFsAbsent:
                continue  # vanished between listing and read: gone
            except Exception:
                return None  # cannot be excluded: fail closed
            if w.WRITER_UID in uids:
                found.append(int(name))
        return tuple(sorted(found))

    def _rw_mount_holders(self) -> tuple[str, ...] | None:
        """Return observed RW holders, or ``None`` if absence is not established.

        A non-empty Docker-side result is reported as is.  A Docker-side
        zero is NOT proof of absence (non-docker processes, other runtimes
        and other mount namespaces are invisible to docker) and no
        independent kernel-side check exists, so it yields ``None``, never
        ``()``.
        """
        holders = self._docker_rw_mount_holders()
        if holders is None or not holders:
            return None
        return holders

    def _docker_rw_mount_holders(self) -> tuple[str, ...] | None:
        """Docker-visible RW holders only (``()`` = none visible to docker).

        The result is limited to the docker daemon's view and must not be
        used as proof of kernel-wide absence; see ``_rw_mount_holders``.
        """
        repo = self._repo_source
        if repo is None:
            return None
        out = self._docker(w.LIST_ALL_ARGV)
        if out is None:
            return None
        holders: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                cid = w.validate_container_id(line)
            except w.WriterError:
                return None
            info = self._inspect(cid)
            if info is None:
                return None
            active = self._is_active(info)
            if active is None:
                return None
            if not active:
                continue
            holds = self._holds_rw(info, repo)
            if holds is None:
                return None
            if holds:
                holders.append(cid)
        return tuple(sorted(holders))

    @staticmethod
    def _is_active(info: Mapping[str, Any]) -> bool | None:
        state = info.get('State')
        if not isinstance(state, Mapping):
            return None
        running, status = state.get('Running'), state.get('Status')
        if not isinstance(running, bool) or not isinstance(status, str):
            return None
        if status in _ACTIVE_STATUSES or running:
            return True
        if status in _INACTIVE_STATUSES:
            return False
        return None

    @staticmethod
    def _overlaps(src: str, repo: str) -> bool:
        src = posixpath.normpath(src)
        if src == '/':
            return True
        return src == repo or repo.startswith(src + '/') or src.startswith(repo + '/')

    def _holds_rw(self, info: Mapping[str, Any], repo: str) -> bool | None:
        mounts = info.get('Mounts')
        if not isinstance(mounts, list):
            return None
        holds = False
        for mount in mounts:
            if not isinstance(mount, Mapping):
                return None
            src, rw = mount.get('Source'), mount.get('RW')
            if not isinstance(rw, bool):
                return None
            if not isinstance(src, str):
                if mount.get('Type') == 'bind':
                    return None
                continue
            if src.startswith('/') and rw and self._overlaps(src, repo):
                holds = True
        host_config = info.get('HostConfig')
        binds = host_config.get('Binds') if isinstance(host_config, Mapping) else None
        if binds is not None and not isinstance(binds, list):
            return None
        for bind in binds or []:
            if not isinstance(bind, str):
                return None
            parts = bind.split(':')
            opts = parts[2].split(',') if len(parts) > 2 else []
            if parts[0].startswith('/') and self._overlaps(parts[0], repo) \
                    and 'ro' not in opts and 'readonly' not in opts:
                holds = True
        return holds


# --- Guest Supervisor --------------------------------------------------------------

class SupervisorState(enum.Enum):
    NEW = 'NEW'
    STARTING = 'STARTING'
    RUNNING = 'RUNNING'
    ATTACHING = 'ATTACHING'
    STOPPING = 'STOPPING'
    STOPPED_VERIFIED = 'STOPPED_VERIFIED'
    UNVERIFIED = 'UNVERIFIED'


LifecycleFactory = Callable[[w.WriterSpec], w.WriterLifecycle]


@runtime_checkable
class InteractiveTransport(Protocol):
    """Raw-byte, full-container-ID-bound TTY transport; it cannot run commands.

    `receive_frame` returns one complete outer frame or None on poll timeout;
    it raises InteractiveDetachedError on channel EOF. TUI bytes are delivered
    only as terminal-data frames, never as independently parsed control tokens.
    """

    def attach(self, container_id: str) -> None: ...

    def send_stdin(self, container_id: str, data: bytes) -> None: ...

    def receive_frame(self, container_id: str, timeout: float) -> bytes | None: ...

    def read_terminal_input(self, timeout: float) -> bytes | None: ...

    def write_terminal_output(self, data: bytes) -> None: ...

    def close(self, container_id: str) -> None: ...

    def restore_terminal(self) -> None: ...


class FixtureSnapshotter(Protocol):
    """Supervisor-owned, pre-fixture snapshot seam; no Writer data is accepted."""

    def capture(self, identity: w.WriterIdentity,
                authority: VerifiedGuestAuthority) -> bool: ...


@dataclasses.dataclass(frozen=True, slots=True)
class AttachOutcome:
    """Observed attach evidence; this is not Task 7 fixture acceptance."""

    tui_exit_code: int | None
    container_exit_code: int | None
    boundary_ready: bool
    snapshot_captured: bool
    continue_sent: bool
    stop_verdict: w.StopVerdict
    failure_code: str | None


def _encode_interactive_frame(kind: int, payload: bytes) -> bytes:
    """Encode one length-bounded terminal-data or Supervisor-control frame."""
    if kind not in (_INTERACTIVE_TERMINAL_FRAME, _INTERACTIVE_CONTROL_FRAME) \
            or not isinstance(payload, bytes) or len(payload) > _MAX_INTERACTIVE_FRAME_BYTES:
        raise InteractiveProtocolError('invalid frame')
    return _INTERACTIVE_FRAME_HEADER.pack(
        _INTERACTIVE_FRAME_MAGIC, kind, len(payload),
    ) + payload


def _decode_interactive_frame(raw: object) -> tuple[int, bytes]:
    """Decode exactly one outer frame without inspecting terminal-data payloads."""
    if not isinstance(raw, bytes) or len(raw) < _INTERACTIVE_FRAME_HEADER.size:
        raise InteractiveProtocolError('malformed frame')
    magic, kind, size = _INTERACTIVE_FRAME_HEADER.unpack_from(raw)
    if magic != _INTERACTIVE_FRAME_MAGIC or kind not in (
        _INTERACTIVE_TERMINAL_FRAME, _INTERACTIVE_CONTROL_FRAME,
    ):
        raise InteractiveProtocolError('unrecognized frame')
    if size > _MAX_INTERACTIVE_FRAME_BYTES \
            or len(raw) != _INTERACTIVE_FRAME_HEADER.size + size:
        raise InteractiveProtocolError('frame length mismatch')
    return kind, raw[_INTERACTIVE_FRAME_HEADER.size:]


def _parse_tui_exit(payload: bytes) -> int:
    """Parse one canonical ASCII TUI exit-code control payload."""
    try:
        text = payload.decode('ascii')
    except UnicodeDecodeError as exc:
        raise InteractiveProtocolError('invalid TUI exit frame') from exc
    match = re.fullmatch(r'TUI_EXIT (0|[1-9][0-9]{0,2})', text)
    if match is None:
        raise InteractiveProtocolError('invalid TUI exit frame')
    code = int(match.group(1))
    if code > 255:
        raise InteractiveProtocolError('invalid TUI exit code')
    return code


def guest_lifecycle_factory(runner: w.DockerRunner, fs: GuestFs,
                            sleep: Callable[[float], None] = time.sleep
                            ) -> LifecycleFactory:
    """Return a factory building ``WriterLifecycle`` with a ``GuestHostProbe``.

    The probe receives ``repo_source`` from the validated ``WriterSpec`` so
    that ``WriterIdentity`` does not need to change.
    """
    def factory(spec: w.WriterSpec) -> w.WriterLifecycle:
        probe = GuestHostProbe(runner, fs, repo_source=spec.repo_source)
        return w.WriterLifecycle(runner, probe, sleep=sleep)
    return factory


_LAUNCH_TEXT_RULES: tuple[tuple[tuple[str, ...], type[SupervisorError], str], ...] = (
    (('Id mismatch', 'identity not confirmed'), IdentityMismatchError,
     'identity-mismatch'),
    (('cgroup inode', 'boot id', 'host probe'), ProbeUnavailableError,
     'probe-unavailable'),
    (('writer inspect rejected', 'pre-start state', 'post-start state',
      'inspect output'), InspectMismatchError, 'inspect-mismatch'),
    (('did not return a container id',), DockerOutputError, 'create-output'),
    (('conflict',), LaunchFailedError, 'conflict'),
)


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and cur not in chain and len(chain) < 16:
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__
    return chain


def _classify_launch_failure(exc: BaseException) -> tuple[type[SupervisorError], str]:
    """Map a launch exception chain to a safe public error type and code.

    Returns a fixed code without exposing exception text. Unknown failures
    become ``LaunchFailedError``/``unclassified``; they are never success.
    """
    chain = _exception_chain(exc)
    for item in reversed(chain):
        if isinstance(item, SupervisorError) and type(item) is not SupervisorError:
            return type(item), type(item).__name__
    text = ' | '.join(str(item) for item in chain if isinstance(item, w.WriterError))
    for needles, cls, code in _LAUNCH_TEXT_RULES:
        if any(n in text for n in needles):
            return cls, code
    return LaunchFailedError, 'unclassified'


class GuestSupervisor:
    """Single-Session, single-Writer Guest Supervisor.

    States: NEW -> STARTING -> RUNNING -> ATTACHING -> STOPPING ->
    STOPPED_VERIFIED, with any failure or unknown outcome going to UNVERIFIED.
    STOPPED_VERIFIED
    and UNVERIFIED are terminal: there is no restart, relaunch, exec or
    recovery API, and a failed launch is never retried or replaced by a new
    container.

    STOPPED_VERIFIED is a limited Writer-stop verdict.  It is NOT proof of
    Git tree immutability, Git transaction consistency or Collection
    finalization.  Process-restart Session recovery is NOT implemented (no
    Receipt v3, no Lease persistence): the state lives only in this object.

    Pure input validation failures in ``launch`` (before any docker call)
    leave the state at NEW; every other launch failure moves to UNVERIFIED.
    Concurrent calls are not serialized by blocking: a second caller while
    STARTING / STOPPING (or while the state lock is held) gets
    ``SupervisorStateError``.
    """

    def __init__(
        self,
        key: w.WriterSessionKey,
        lifecycle_factory: LifecycleFactory,
        *,
        image_authority: VerifiedGuestAuthority | None = None,
        snapshotter: FixtureSnapshotter | None = None,
    ) -> None:
        if not isinstance(key, w.WriterSessionKey):
            raise SupervisorInputError('session key: invalid type')
        try:
            key.validate()
        except w.WriterError as exc:
            raise SupervisorInputError('session key: invalid') from exc
        if not callable(lifecycle_factory):
            raise SupervisorInputError('lifecycle factory: expected callable')
        if image_authority is not None and (
            not is_verified_guest_authority(image_authority)
            or image_authority.key != key
        ):
            raise SupervisorInputError('verified Guest image authority does not match SessionKey')
        if snapshotter is not None and not callable(getattr(snapshotter, 'capture', None)):
            raise SupervisorInputError('snapshotter: expected capture capability')
        self._key = key
        self._factory = lifecycle_factory
        self._image_authority = image_authority
        self._snapshotter = snapshotter
        self._lock = threading.Lock()
        self._state = SupervisorState.NEW
        self._identity: w.WriterIdentity | None = None
        self._lifecycle: w.WriterLifecycle | None = None
        self._spec: w.WriterSpec | None = None

    @property
    def session_key(self) -> w.WriterSessionKey:
        return self._key

    @property
    def state(self) -> SupervisorState:
        return self._state

    @property
    def identity(self) -> w.WriterIdentity | None:
        return self._identity

    def _transition(self, expected: SupervisorState, target: SupervisorState) -> None:
        if not self._lock.acquire(blocking=False):
            raise SupervisorStateError('state conflict: busy')
        try:
            if self._state is not expected:
                raise SupervisorStateError(
                    f'state conflict: {self._state.value} (need {expected.value})')
            self._state = target
        finally:
            self._lock.release()

    def _set_state(self, target: SupervisorState) -> None:
        with self._lock:
            self._state = target

    @staticmethod
    def _forward_terminal_input(
        transport: InteractiveTransport, container_id: str,
    ) -> None:
        """Forward only raw local terminal bytes to the already-bound full Container ID."""
        data = transport.read_terminal_input(_INTERACTIVE_POLL_S)
        if data is None:
            return
        if not isinstance(data, bytes) or len(data) > _MAX_INTERACTIVE_FRAME_BYTES:
            raise InteractiveTransportError('terminal input invalid')
        if data:
            transport.send_stdin(container_id, data)

    def _authority_start_line(
        self,
        identity: w.WriterIdentity,
        spec: w.WriterSpec,
        authority: VerifiedGuestAuthority,
    ) -> bytes:
        """Revalidate the immutable Task 2 authority before producing its wire line."""
        if not is_verified_guest_authority(authority) or authority is not self._image_authority:
            raise SupervisorInputError('attach: verified Guest authority required')
        if not isinstance(authority.manifest, SliceBBundleManifestV1):
            raise SupervisorInputError('attach: verified manifest required')
        manifest = authority.manifest
        if authority.key != self._key or manifest.key != self._key:
            raise IdentityMismatchError('attach: SessionKey mismatch')
        if manifest.schema != BUNDLE_SCHEMA or not isinstance(manifest.baseline, GitBaseline):
            raise SupervisorInputError('attach: manifest schema or baseline invalid')
        if (
            authority.image_config_id != spec.image_config_id
            or authority.image_record_sha256 != spec.image_record_sha256
            or authority.runtime_sha256 != spec.runtime_sha256
            or authority.image_config_id != identity.image_id
        ):
            raise IdentityMismatchError('attach: image authority mismatch')
        if not isinstance(manifest.baseline.object_format, str):
            raise SupervisorInputError('attach: invalid Git object format')
        baseline = manifest.baseline
        oid_lengths = {'sha1': 40, 'sha256': 64}
        oid_length = oid_lengths.get(baseline.object_format)
        if (
            manifest.transfer_policy_id != BUNDLE_POLICY
            or not isinstance(manifest.bundle_sha256, str)
            or re.fullmatch(r'[0-9a-f]{64}', manifest.bundle_sha256) is None
            or not isinstance(manifest.runtime_sha256, str)
            or re.fullmatch(r'[0-9a-f]{64}', manifest.runtime_sha256) is None
            or oid_length is None
            or not isinstance(baseline.head_oid, str)
            or re.fullmatch(rf'[0-9a-f]{{{oid_length}}}', baseline.head_oid) is None
            or not isinstance(baseline.tree_oid, str)
            or re.fullmatch(rf'[0-9a-f]{{{oid_length}}}', baseline.tree_oid) is None
            or isinstance(manifest.bundle_size_bytes, bool)
            or not isinstance(manifest.bundle_size_bytes, int)
            or manifest.bundle_size_bytes < 0
        ):
            raise SupervisorInputError('attach: invalid trusted manifest fields')
        try:
            canonical = _manifest_bytes(manifest)
        except (SliceBGitRejected, TypeError, ValueError) as exc:
            raise SupervisorInputError('attach: invalid trusted manifest') from exc
        if hashlib.sha256(canonical).hexdigest() != authority.manifest_sha256:
            raise SupervisorInputError('attach: trusted manifest digest mismatch')
        try:
            task2_message = build_start_message(authority)
            start_message = SliceBStartMessage(
                self._key.session_generation,
                baseline.head_oid,
                baseline.branch_ref,
                authority.manifest_sha256,
            )
            if task2_message != start_message:
                raise SupervisorInputError('attach: Task 2 start message mismatch')
            line = (
                'OC2_SLICE_B_START '
                + ' '.join((
                    self._key.session_generation,
                    baseline.head_oid,
                    baseline.branch_ref,
                    authority.manifest_sha256,
                ))
                + '\n'
            )
            start_line = line.encode('ascii')
        except (SliceBGitRejected, SliceBSessionError, UnicodeError, TypeError, ValueError) as exc:
            raise SupervisorInputError('attach: invalid trusted start authority') from exc
        if len(start_line) > 512:
            raise SupervisorInputError('attach: trusted start line exceeds bound')
        return start_line

    def _inspect_attach_identity(
        self, identity: w.WriterIdentity, *, require_running: bool,
    ) -> Mapping[str, Any]:
        lifecycle, spec = self._lifecycle, self._spec
        authority = self._image_authority
        if lifecycle is None or spec is None or not is_verified_guest_authority(authority):
            raise IdentityMismatchError('attach: Writer lifecycle unavailable')
        try:
            info = lifecycle._inspect(identity.container_id)
        except w.WriterError as exc:
            raise IdentityMismatchError('attach: container inspect unavailable') from exc
        if not isinstance(info, Mapping):
            raise IdentityMismatchError('attach: container inspect malformed')
        try:
            w.validate_writer_inspect(info, spec, authority=authority)
        except w.WriterError as exc:
            raise InspectMismatchError('attach: Writer inspect mismatch') from exc
        if info.get('Id') != identity.container_id or info.get('Image') != identity.image_id:
            raise IdentityMismatchError('attach: container or image identity mismatch')
        state = info.get('State')
        if not isinstance(state, Mapping) or state.get('StartedAt') != identity.started_at:
            raise IdentityMismatchError('attach: StartedAt mismatch')
        if require_running:
            pid = state.get('Pid')
            if state.get('Status') != 'running' or state.get('Running') is not True:
                raise InspectMismatchError('attach: Writer is not running')
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise InspectMismatchError('attach: Writer PID invalid')
        return state

    def launch(self, spec: w.WriterSpec) -> w.WriterIdentity:
        """Launch the single Writer for this Session (only from NEW)."""
        authority = self._image_authority
        if not is_verified_guest_authority(authority):
            raise SupervisorInputError('launch: verified Guest image authority required')
        if isinstance(spec, w.WriterSpec) and spec.key != self._key:
            raise SupervisorInputError('launch: spec session key mismatch')
        try:
            w.validate_writer_spec(spec, authority=authority)
        except w.WriterError as exc:
            raise SupervisorInputError('launch: invalid spec') from exc
        self._transition(SupervisorState.NEW, SupervisorState.STARTING)
        failure: SupervisorError | None = None
        lifecycle: w.WriterLifecycle | None = None
        identity: w.WriterIdentity | None = None
        try:
            lifecycle = self._factory(spec)
            if not isinstance(lifecycle, w.WriterLifecycle):
                raise SupervisorInputError('launch: factory did not return WriterLifecycle')
            identity = lifecycle.launch(spec, authority=authority)
            if not isinstance(identity, w.WriterIdentity):
                raise IdentityMismatchError('launch: no identity returned')
            w.validate_container_id(identity.container_id)
        except BaseException as exc:
            self._set_state(SupervisorState.UNVERIFIED)
            if not isinstance(exc, Exception):
                raise
            cls, code = _classify_launch_failure(exc)
            failure = cls(f'launch failed: {code}')
        if failure is not None:
            raise failure
        if lifecycle is None or identity is None:
            self._set_state(SupervisorState.UNVERIFIED)
            raise LaunchFailedError('launch failed: identity unavailable')
        with self._lock:
            self._identity = identity
            self._lifecycle = lifecycle
            self._spec = spec
            self._state = SupervisorState.RUNNING
        return identity

    def attach_writer(
        self,
        identity: w.WriterIdentity,
        transport: InteractiveTransport,
        authority: VerifiedGuestAuthority,
    ) -> AttachOutcome:
        """Attach once to the launched Writer and return bounded evidence only.

        The trusted start line is sent before any host terminal input. Only
        framed PID 1 controls can open the snapshot/CONTINUE barrier; terminal
        bytes are always opaque. This does not establish Task 7 acceptance.
        """
        if not isinstance(identity, w.WriterIdentity):
            raise IdentityMismatchError('attach: identity type invalid')
        try:
            cid = w.validate_container_id(identity.container_id)
        except w.WriterError as exc:
            raise IdentityMismatchError('attach: full Container ID required') from exc
        if not self._lock.acquire(blocking=False):
            raise SupervisorStateError('state conflict: busy')
        try:
            if self._state is not SupervisorState.RUNNING:
                raise SupervisorStateError(
                    f'state conflict: {self._state.value} (need RUNNING)'
                )
            if identity != self._identity:
                raise IdentityMismatchError('attach: foreign Writer identity')
            self._state = SupervisorState.ATTACHING
            spec = self._spec
        finally:
            self._lock.release()

        tui_exit_code: int | None = None
        container_exit_code: int | None = None
        boundary_ready = False
        snapshot_captured = False
        continue_sent = False
        failure_code: str | None = None
        attach_attempted = False
        post_tui_exit_deadline: float | None = None
        post_continue_deadline: float | None = None

        try:
            if spec is None:
                raise IdentityMismatchError('attach: Writer spec unavailable')
            snapshotter = self._snapshotter
            if snapshotter is None:
                raise FixtureSnapshotError('snapshotter unavailable')
            if not isinstance(transport, InteractiveTransport):
                raise InteractiveTransportError('interactive transport invalid')
            start_line = self._authority_start_line(identity, spec, authority)
            state = self._inspect_attach_identity(identity, require_running=True)
            pid = state.get('Pid')
            if state.get('Status') != 'running' or state.get('Running') is not True \
                    or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise InspectMismatchError('attach: Writer is not running')

            attach_attempted = True
            transport.attach(cid)
            transport.send_stdin(cid, start_line)
            while True:
                if continue_sent and (post_continue_deadline is not None
                                      and time.monotonic() >= post_continue_deadline):
                    failure_code = 'writer-exit-unknown'
                    break
                if (tui_exit_code is not None and not continue_sent
                        and post_tui_exit_deadline is not None
                        and time.monotonic() >= post_tui_exit_deadline):
                    failure_code = 'fixture-boundary-unconfirmed'
                    break
                raw_frame = transport.receive_frame(cid, _INTERACTIVE_POLL_S)
                if raw_frame is None:
                    if tui_exit_code is None:
                        self._forward_terminal_input(transport, cid)
                    continue
                kind, payload = _decode_interactive_frame(raw_frame)
                if kind == _INTERACTIVE_TERMINAL_FRAME:
                    transport.write_terminal_output(payload)
                else:
                    if payload.startswith(b'TUI_EXIT'):
                        if tui_exit_code is not None:
                            raise InteractiveProtocolError('duplicate TUI exit frame')
                        tui_exit_code = _parse_tui_exit(payload)
                        if tui_exit_code != 0:
                            failure_code = 'tui-exit-nonzero'
                            break
                        post_tui_exit_deadline = (
                            time.monotonic() + _POST_TUI_EXIT_TIMEOUT_S
                        )
                    elif payload == b'FIXTURE_BOUNDARY_READY':
                        if tui_exit_code != 0 or boundary_ready:
                            raise InteractiveProtocolError('READY out of sequence')
                        boundary_ready = True
                        try:
                            captured = snapshotter.capture(identity, authority)
                        except Exception as exc:  # noqa: BLE001
                            raise FixtureSnapshotError('snapshot unavailable') from exc
                        if captured is not True:
                            raise FixtureSnapshotError('snapshot unavailable')
                        snapshot_captured = True
                        transport.send_stdin(
                            cid,
                            _encode_interactive_frame(
                                _INTERACTIVE_CONTROL_FRAME, b'FIXTURE_BOUNDARY_CONTINUE',
                            ),
                        )
                        continue_sent = True
                        post_continue_deadline = (
                            time.monotonic() + _POST_CONTINUE_TIMEOUT_S
                        )
                    else:
                        raise InteractiveProtocolError('unknown control frame')
                if tui_exit_code is None:
                    self._forward_terminal_input(transport, cid)
        except InteractiveDetachedError:
            pass
        except KeyboardInterrupt:
            failure_code = 'interrupted'
            if attach_attempted:
                try:
                    transport.send_stdin(cid, b'\x03')
                except (InteractiveTransportError, OSError, TimeoutError, KeyboardInterrupt):
                    failure_code = 'interrupt-forward-failed'
        except InteractiveProtocolError:
            failure_code = 'interactive-protocol'
        except FixtureSnapshotError:
            failure_code = 'snapshot-failed'
        except InteractiveTransportError:
            failure_code = 'attach-transport'
        except IdentityMismatchError:
            failure_code = 'identity-mismatch'
        except InspectMismatchError:
            failure_code = 'inspect-mismatch'
        except (SupervisorInputError, SliceBGitRejected, SliceBSessionError,
                w.WriterError, OSError, TimeoutError, TypeError, ValueError):
            failure_code = 'attach-validation-failed'
        except Exception:  # noqa: BLE001
            failure_code = 'attach-failed'
        finally:
            if attach_attempted:
                try:
                    transport.close(cid)
                except KeyboardInterrupt:
                    if failure_code is None:
                        failure_code = 'attach-close-failed'
                except Exception:  # noqa: BLE001
                    if failure_code is None:
                        failure_code = 'attach-close-failed'
                try:
                    transport.restore_terminal()
                except KeyboardInterrupt:
                    if failure_code is None:
                        failure_code = 'terminal-restore-failed'
                except Exception:  # noqa: BLE001
                    if failure_code is None:
                        failure_code = 'terminal-restore-failed'

        stop_verdict = w.StopVerdict(
            w.STATUS_GUEST_QUIESCENCE_UNVERIFIED, ('attach stop not attempted',),
        )
        try:
            if attach_attempted:
                try:
                    final_state = self._inspect_attach_identity(identity, require_running=False)
                    pid = final_state.get('Pid')
                    exit_code = final_state.get('ExitCode')
                    if (
                        final_state.get('Status') != 'exited'
                        or final_state.get('Running') is not False
                        or isinstance(pid, bool)
                        or not isinstance(pid, int)
                        or pid != 0
                        or isinstance(exit_code, bool)
                        or not isinstance(exit_code, int)
                        or not 0 <= exit_code <= 255
                    ):
                        if failure_code is None:
                            failure_code = 'writer-exit-unknown'
                    else:
                        container_exit_code = exit_code
                        if exit_code != 0 and failure_code is None:
                            failure_code = 'writer-exit-nonzero'
                except (IdentityMismatchError, InspectMismatchError, w.WriterError):
                    if failure_code is None:
                        failure_code = 'writer-exit-unknown'
                except KeyboardInterrupt:
                    if failure_code is None:
                        failure_code = 'interrupted'
                except (OSError, TimeoutError):
                    if failure_code is None:
                        failure_code = 'writer-exit-unknown'
                except Exception:  # noqa: BLE001
                    if failure_code is None:
                        failure_code = 'writer-exit-unknown'
            if failure_code is None and tui_exit_code is None:
                failure_code = 'tui-exit-unknown'
            if failure_code is None and not (boundary_ready and snapshot_captured and continue_sent):
                failure_code = 'fixture-boundary-incomplete'
        finally:
            try:
                lifecycle, current = self._begin_stop(
                    identity, SupervisorState.ATTACHING, 'attach',
                )
                stop_verdict = self._finish_stop(lifecycle, current)
            except KeyboardInterrupt:
                self._set_state(SupervisorState.UNVERIFIED)
                stop_verdict = w.StopVerdict(
                    w.STATUS_GUEST_QUIESCENCE_UNVERIFIED, ('attach stop interrupted',),
                )
                if failure_code is None:
                    failure_code = 'interrupted'
            except SupervisorError:
                self._set_state(SupervisorState.UNVERIFIED)
                stop_verdict = w.StopVerdict(
                    w.STATUS_GUEST_QUIESCENCE_UNVERIFIED, ('attach stop unverified',),
                )
            if not stop_verdict.verified and failure_code is None:
                failure_code = 'stop-unverified'
        return AttachOutcome(
            tui_exit_code,
            container_exit_code,
            boundary_ready,
            snapshot_captured,
            continue_sent,
            stop_verdict,
            failure_code,
        )

    def stop(self, identity: w.WriterIdentity | None = None) -> w.StopVerdict:
        """Stop and verify the Writer (only from RUNNING).

        ``identity``, if given, must equal the identity returned by
        ``launch``; a stale or foreign identity is rejected without any
        docker call and without changing state.  The verdict is returned in
        both cases; the state becomes STOPPED_VERIFIED only for a verified
        verdict and UNVERIFIED otherwise.
        """
        lifecycle, current = self._begin_stop(identity, SupervisorState.RUNNING, 'stop')
        return self._finish_stop(lifecycle, current)

    def _begin_stop(
        self,
        identity: w.WriterIdentity | None,
        expected: SupervisorState,
        operation: str,
    ) -> tuple[w.WriterLifecycle | None, w.WriterIdentity | None]:
        if not self._lock.acquire(blocking=False):
            raise SupervisorStateError('state conflict: busy')
        try:
            if self._state is not expected:
                raise SupervisorStateError(
                    f'state conflict: {self._state.value} (need {expected.value})'
                )
            if identity is not None and (
                not isinstance(identity, w.WriterIdentity) or identity != self._identity
            ):
                tag = _cid_tag(getattr(identity, 'container_id', None))
                raise IdentityMismatchError(f'{operation}: foreign identity cid={tag}')
            self._state = SupervisorState.STOPPING
            return self._lifecycle, self._identity
        finally:
            self._lock.release()

    def _finish_stop(
        self,
        lifecycle: w.WriterLifecycle | None,
        current: w.WriterIdentity | None,
    ) -> w.StopVerdict:
        failure: StopVerificationError | None = None
        verdict: w.StopVerdict | None = None
        try:
            if lifecycle is None or current is None:
                raise StopVerificationError('stop: lifecycle unavailable')
            verdict = lifecycle.stop(current)
            if not isinstance(verdict, w.StopVerdict):
                raise StopVerificationError('stop: no verdict')
        except BaseException as exc:
            self._set_state(SupervisorState.UNVERIFIED)
            if not isinstance(exc, Exception):
                raise
            failure = StopVerificationError(
                'stop failed: unexpected error cid='
                + _cid_tag(getattr(current, 'container_id', None))
            )
        if failure is not None:
            raise failure
        if verdict is None:
            self._set_state(SupervisorState.UNVERIFIED)
            raise StopVerificationError('stop: verdict unavailable')
        self._set_state(SupervisorState.STOPPED_VERIFIED if verdict.verified
                        else SupervisorState.UNVERIFIED)
        return verdict
