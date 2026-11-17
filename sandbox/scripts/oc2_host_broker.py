"""Explicit opt-in Host Broker connection contract for the OC2 launcher.

This module only validates and plans. It does not implement the Broker, SIWC,
or the Guest provider (those live in oc-cf-aig-subscription and are consumed as
is). Fixed contract mirrored from that project:

* Guest provider id ``oc-cf-aig``, model ``gpt-6-luna``.
* Acceptance modes ``m1`` (no tools) and ``m2`` (Guest-local ``read_file`` only).
* Broker URL ``http://<host.docker.internal|127.0.0.1>:<port>/v1``.
* Capability ``ocb_`` + 43 base64url characters, delivered once over a pipe or
  socket FD. It is never placed in argv, environment, files, or logs.

Every violation raises HostBrokerError; callers must stop. There is no fallback
to a direct provider, BYOK, or the Cloudflare Gateway credential path.
"""
from __future__ import annotations

import os
import pathlib
import re
import socket
import stat
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

PROVIDER_ID: Final[str] = 'oc-cf-aig'
MODEL_ID: Final[str] = 'gpt-6-luna'
MODES: Final[frozenset[str]] = frozenset({'m1', 'm2'})
BROKER_HOSTS: Final[frozenset[str]] = frozenset({'host.docker.internal', '127.0.0.1'})
CAPABILITY_RE: Final[re.Pattern[str]] = re.compile(r'ocb_[A-Za-z0-9_-]{43}')
MAX_CAPABILITY_BYTES: Final[int] = 256
GUEST_ROOT: Final[str] = '/home/agent/workspace/oc2'
CAPABILITY_ENV: Final[str] = 'OC_CF_AIG_BROKER_CAPABILITY'
_LABEL_RE: Final[re.Pattern[str]] = re.compile(r'[A-Za-z0-9._-]{1,64}')
_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r'[0-9a-f]{64}')


class HostBrokerError(Exception):
    """Fail-closed Host Broker violation. Messages never contain secret values."""


def validate_broker_url(value: object) -> str:
    """Return the canonical Broker URL or raise; same rule as the Guest provider."""
    message = 'Host Broker URL must be http://<host.docker.internal|127.0.0.1>:<port>/v1'
    if not isinstance(value, str) or not value or re.search(r'[?#\s]', value):
        raise HostBrokerError(message)
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise HostBrokerError(message) from None
    if (url.scheme != 'http' or url.hostname not in BROKER_HOSTS or port is None
            or not 1 <= port <= 65535 or url.username or url.password
            or url.query or url.fragment
            or re.fullmatch(r'/v1/?', url.path) is None):
        raise HostBrokerError(message)
    return f'http://{url.hostname}:{port}/v1'


@dataclass(frozen=True, slots=True)
class HostBrokerSelection:
    """Validated, secret-free description of one explicit Broker connection."""

    url: str
    mode: str
    sandbox_label: str
    capability_fd: int
    fixture_root: str | None = None
    provider: str = PROVIDER_ID
    model: str = MODEL_ID


def build_selection(
    *,
    url: object,
    mode: object,
    sandbox_label: object,
    capability_fd: object,
    fixture_root: object = None,
    provider: object = PROVIDER_ID,
    model: object = MODEL_ID,
) -> HostBrokerSelection:
    """Validate every field against the fixed contract (unknown => stop)."""
    if provider != PROVIDER_ID:
        raise HostBrokerError('Host Broker provider must be ' + PROVIDER_ID)
    if model != MODEL_ID:
        raise HostBrokerError('Host Broker model must be ' + MODEL_ID)
    if not isinstance(mode, str) or mode not in MODES:
        raise HostBrokerError('Host Broker mode must be m1 or m2')
    if not isinstance(sandbox_label, str) or _LABEL_RE.fullmatch(sandbox_label) is None:
        raise HostBrokerError('Host Broker sandbox label is missing or invalid')
    if (not isinstance(capability_fd, int) or isinstance(capability_fd, bool)
            or not 3 <= capability_fd <= 1023):
        raise HostBrokerError('Host Broker capability fd must be an integer from 3 to 1023')
    if mode == 'm1' and fixture_root is not None:
        raise HostBrokerError('m1 grants no tools; a fixture root is not allowed')
    if mode == 'm2':
        if not isinstance(fixture_root, str):
            raise HostBrokerError('m2 requires a Guest fixture root')
        posix = pathlib.PurePosixPath(fixture_root)
        if (not posix.is_absolute() or '..' in posix.parts
                or str(posix) != fixture_root or '\0' in fixture_root):
            raise HostBrokerError('Guest fixture root must be a normalized absolute path')
    return HostBrokerSelection(
        validate_broker_url(url), mode, sandbox_label, capability_fd,
        fixture_root if mode == 'm2' else None,
    )


def bind_identity(selection: HostBrokerSelection, sandbox_name: str, runtime_digest: str) -> str:
    """Stop unless the Broker is bound to this exact Sandbox and Runtime.

    Returns the Guest Runtime directory. The Broker label is a management label
    (not authorization), so it must at least equal the launching Sandbox name.
    """
    if selection.sandbox_label != sandbox_name:
        raise HostBrokerError('Host Broker sandbox label does not match the launching Sandbox')
    if _DIGEST_RE.fullmatch(runtime_digest) is None:
        raise HostBrokerError('invalid runtime digest')
    runtime = f'{GUEST_ROOT}/runtime/{runtime_digest[:16]}'
    if selection.fixture_root is not None and not selection.fixture_root.startswith(runtime + '/'):
        raise HostBrokerError('Guest fixture root is outside the bound Runtime')
    return runtime


class Capability:
    """Opaque one-shot bearer. Never printable; only ``reveal`` exposes it."""

    __slots__ = ('_token',)

    def __init__(self, token: str) -> None:
        if CAPABILITY_RE.fullmatch(token) is None:
            raise HostBrokerError('Host Broker capability is missing or malformed')
        self._token = token

    def reveal(self) -> bytes:
        return (self._token + '\n').encode('ascii')

    def __repr__(self) -> str:
        return 'Capability(<redacted>)'

    __str__ = __repr__

    def __reduce__(self) -> tuple[()]:
        raise TypeError('Capability cannot be serialized')


def check_capability_fd(fd: int, *, fstat: Callable[[int], os.stat_result] = os.fstat) -> None:
    """Accept only an open pipe or socket (never a regular file or TTY)."""
    try:
        mode = fstat(fd).st_mode
    except OSError:
        raise HostBrokerError('Host Broker capability fd is not open') from None
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise HostBrokerError('Host Broker capability must arrive over a pipe or socket')


def read_capability(fd: int, *, read: Callable[[int, int], bytes] = os.read) -> Capability:
    """Read the one-shot capability to EOF (bounded), validate, and close the fd."""
    check_capability_fd(fd)
    chunks: list[bytes] = []
    size = 0
    try:
        while True:
            chunk = read(fd, MAX_CAPABILITY_BYTES + 1 - size)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_CAPABILITY_BYTES:
                raise HostBrokerError('Host Broker capability is too large')
            chunks.append(chunk)
    except OSError:
        raise HostBrokerError('Host Broker capability could not be read') from None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    raw = b''.join(chunks)
    if raw.endswith(b'\n'):
        raw = raw[:-1]
    try:
        return Capability(raw.decode('ascii'))
    except UnicodeDecodeError:
        raise HostBrokerError('Host Broker capability is missing or malformed') from None


def probe_broker(
    url: str,
    *,
    connect: Callable[..., socket.socket] = socket.create_connection,
) -> None:
    """Host-side reachability check on loopback. Failure stops; nothing falls back."""
    port = urlsplit(url).port
    try:
        connect(('127.0.0.1', port), timeout=3).close()
    except OSError:
        raise HostBrokerError('Host Broker is not reachable; no fallback provider is used') from None
