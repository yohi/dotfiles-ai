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

import hashlib
import os
import pathlib
import re
import socket
import ssl
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
_FIXTURE_PART_RE: Final[re.Pattern[str]] = re.compile(r'[A-Za-z0-9._-]{1,64}')
FIXTURE_BASE: Final[str] = 'fixtures'
MAX_BROKER_CA_BYTES: Final[int] = 64 * 1024


class HostBrokerError(Exception):
    """Fail-closed Host Broker violation. Messages never contain secret values."""


@dataclass(frozen=True, slots=True)
class BrokerCaCertificate:
    """Public Broker CA bytes and their content identity."""

    data: bytes
    sha256: str


def load_broker_ca(path: pathlib.Path) -> BrokerCaCertificate:
    """Load a bounded PEM CA certificate from a regular, non-symlink file."""
    fd: int | None = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BROKER_CA_BYTES:
            raise HostBrokerError('Broker CA certificate is not a bounded regular file')
        chunks: list[bytes] = []
        size = 0
        while size <= MAX_BROKER_CA_BYTES:
            chunk = os.read(fd, MAX_BROKER_CA_BYTES + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        data = b''.join(chunks)
    except OSError:
        raise HostBrokerError('Broker CA certificate is missing or linked') from None
    finally:
        if fd is not None:
            os.close(fd)
    if len(data) != info.st_size or len(data) > MAX_BROKER_CA_BYTES:
        raise HostBrokerError('Broker CA certificate size changed while reading')
    try:
        ssl.create_default_context(cadata=data.decode('ascii'))
    except (ssl.SSLError, ValueError):
        raise HostBrokerError('Broker CA certificate is not valid PEM') from None
    return BrokerCaCertificate(data, hashlib.sha256(data).hexdigest())


def validate_broker_url(value: object) -> str:
    """Return the canonical Broker URL or raise; same rule as the Guest provider."""
    message = 'Host Broker URL must be https://<host.docker.internal|127.0.0.1>:<port>/v1'
    if not isinstance(value, str) or not value or re.search(r'[?#\s]', value):
        raise HostBrokerError(message)
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise HostBrokerError(message) from None
    if (url.scheme != 'https' or url.hostname not in BROKER_HOSTS or port is None
            or not 1 <= port <= 65535 or url.username or url.password
            or url.query or url.fragment
            or re.fullmatch(r'/v1/?', url.path) is None):
        raise HostBrokerError(message)
    return f'https://{url.hostname}:{port}/v1'


@dataclass(frozen=True, slots=True)
class HostBrokerSelection:
    """Validated, secret-free description of one explicit Broker connection."""

    url: str
    mode: str
    sandbox_label: str
    capability_fd: int
    broker_ca_sha256: str
    # Normalized path RELATIVE to the Runtime directory (m2 only). The absolute
    # Guest path is derived only after the Runtime Identity is fixed.
    fixture_rel: str | None = None
    provider: str = PROVIDER_ID
    model: str = MODEL_ID


def build_selection(
    *,
    url: object,
    mode: object,
    sandbox_label: object,
    capability_fd: object,
    broker_ca_sha256: str,
    fixture_rel: object = None,
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
    if not isinstance(broker_ca_sha256, str) or _DIGEST_RE.fullmatch(broker_ca_sha256) is None:
        raise HostBrokerError('Host Broker CA SHA-256 is invalid')
    if mode == 'm1' and fixture_rel is not None:
        raise HostBrokerError('m1 grants no tools; a fixture is not allowed')
    fixture: str | None = None
    if mode == 'm2':
        fixture = validate_fixture_rel(fixture_rel)
    return HostBrokerSelection(
        validate_broker_url(url), mode, sandbox_label, capability_fd, broker_ca_sha256, fixture,
    )


def validate_fixture_rel(value: object) -> str:
    """Accept only ``fixtures`` or ``fixtures/<name>...`` as a normalized relative path."""
    message = 'm2 requires a normalized relative fixture path under ' + FIXTURE_BASE
    if not isinstance(value, str) or not value or '\0' in value or '\\' in value:
        raise HostBrokerError(message)
    parts = value.split('/')
    if (parts[0] != FIXTURE_BASE or len(parts) > 4
            or any(_FIXTURE_PART_RE.fullmatch(part) is None or part in ('.', '..')
                   for part in parts)):
        raise HostBrokerError(message)
    return value


def fixture_guest_path(selection: HostBrokerSelection, runtime: str) -> str | None:
    """Absolute Guest fixture path under an already-bound Runtime (re-validated)."""
    if selection.fixture_rel is None:
        return None
    return f'{runtime}/{validate_fixture_rel(selection.fixture_rel)}'


def bind_identity(selection: HostBrokerSelection, sandbox_name: str, runtime_digest: str) -> str:
    """Stop unless the Broker is bound to this exact Sandbox and Runtime.

    Returns the Guest Runtime directory. The Broker label is a management label
    (not authorization), so it must at least equal the launching Sandbox name.
    """
    if selection.sandbox_label != sandbox_name:
        raise HostBrokerError('Host Broker sandbox label does not match the launching Sandbox')
    if _DIGEST_RE.fullmatch(runtime_digest) is None:
        raise HostBrokerError('invalid runtime digest')
    if selection.mode == 'm1' and selection.fixture_rel is not None:
        raise HostBrokerError('m1 grants no tools; a fixture is not allowed')
    if selection.mode == 'm2':
        validate_fixture_rel(selection.fixture_rel)
    return f'{GUEST_ROOT}/runtime/{runtime_digest[:16]}'


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
    ca_data: bytes,
    *,
    connect: Callable[..., socket.socket] = socket.create_connection,
) -> None:
    """Verify the loopback Broker TLS certificate and hostname before Sandbox startup."""
    canonical_url = validate_broker_url(url)
    parsed = urlsplit(canonical_url)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        raise HostBrokerError('Host Broker URL is invalid')
    try:
        context = ssl.create_default_context(cadata=ca_data.decode('ascii'))
        connection = connect(('127.0.0.1', port), timeout=3)
        with context.wrap_socket(connection, server_hostname=host):
            pass
    except (OSError, ssl.SSLError, UnicodeError, ValueError):
        raise HostBrokerError('Host Broker TLS verification failed; no fallback provider is used') from None
