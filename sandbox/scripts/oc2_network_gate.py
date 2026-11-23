from __future__ import annotations

import json
import os
import pathlib
import re
import stat
from enum import StrEnum
from typing import Final, Literal

from oc2_network_policy import (
    JsonValue,
    NetworkGateError,
    PolicyRunner,
    ScopedNetworkAllow,
    find_scoped_network_allow as find_scoped_network_allow,
    find_task_broker_allow as find_task_broker_allow,
    revoke_network_allow as revoke_network_allow,
    scoped_network_allow,
    validate_policy_listing,
)


class SandboxState(StrEnum):
    RUNNING = 'running'
    STOPPED = 'stopped'





_APP_NAME: Final[re.Pattern[str]] = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]')
_GUEST_NETWORK_PROBE: Final[str] = '''import socket, ssl, sys
host, port = sys.argv[1], int(sys.argv[2])
ca_data = sys.stdin.buffer.read(65537)
if not 0 < len(ca_data) <= 65536:
    raise SystemExit("BROKER_CA_INPUT_INVALID")
context = ssl.create_default_context(cadata=ca_data.decode("ascii"))
for address in ("1.1.1.1", "8.8.8.8"):
    try:
        connection = socket.create_connection((address, 443), timeout=2)
    except OSError:
        continue
    else:
        connection.close()
        raise SystemExit("SANDBOX_TCP_EGRESS_ALLOWED")
try:
    socket.getaddrinfo("example.com", 443)
except OSError:
    pass
else:
    raise SystemExit("SANDBOX_DNS_EGRESS_ALLOWED")
with socket.create_connection((host, port), timeout=3) as connection:
    with context.wrap_socket(connection, server_hostname=host):
        pass
print("OC2_GUEST_NETWORK_PROBES_PASS")
'''
def validate_app_name(value: str | None) -> str:
    if value is None or _APP_NAME.fullmatch(value) is None:
        raise NetworkGateError('Host Broker requires a valid dedicated daemon name')
    return value


def expected_socket_path(app_name: str, state_home: pathlib.Path) -> pathlib.Path:
    _ = validate_app_name(app_name)
    return state_home / 'sandboxes' / f'sandboxes-{app_name}' / 'sandboxd' / 'sandboxd.sock'


def validate_daemon_identity(status: str, expected_socket: pathlib.Path,
                             socket_mode: int | None) -> None:
    if not re.search(r'^\s*Status:\s*(?:●\s*)?running\s*$', status, re.MULTILINE):
        raise NetworkGateError('dedicated Sandbox daemon is not running')
    match = re.search(r'^\s*Socket:\s*(\S+)\s*$', status, re.MULTILINE)
    if match is None or pathlib.Path(match.group(1)) != expected_socket:
        raise NetworkGateError('dedicated Sandbox daemon socket identity mismatch')
    if socket_mode is None or not stat.S_ISSOCK(socket_mode):
        raise NetworkGateError('dedicated Sandbox daemon socket is unavailable')


def validate_daemon_stopped(status: str, expected_socket: pathlib.Path) -> None:
    """Require the dedicated daemon to report stopped on its exact socket path."""
    state = re.search(r'^\s*Status:\s*(?:●\s*)?stopped\s*$', status, re.MULTILINE)
    socket_match = re.search(r'^\s*Socket:\s*(\S+)\s+\(not connected\)\s*$',
                             status, re.MULTILINE)
    if (state is None or socket_match is None
            or pathlib.Path(socket_match.group(1)) != expected_socket):
        raise NetworkGateError('dedicated Sandbox daemon stop was not verified')


def verify_dedicated_daemon(runner: PolicyRunner, app_name: str) -> None:
    _ = validate_app_name(app_name)
    state_value = os.environ.get('XDG_STATE_HOME')
    state_home = (pathlib.Path(state_value).expanduser() if state_value
                  else pathlib.Path.home() / '.local' / 'state')
    expected = expected_socket_path(app_name, state_home)
    status = runner.sbx('daemon', 'status', capture=True)
    try:
        for parent in (
            state_home,
            state_home / 'sandboxes',
            state_home / 'sandboxes' / f'sandboxes-{app_name}',
            state_home / 'sandboxes' / f'sandboxes-{app_name}' / 'sandboxd',
        ):
            if parent.is_symlink():
                raise NetworkGateError('dedicated Sandbox daemon socket path contains a link')
        socket_mode = expected.lstat().st_mode
    except OSError:
        socket_mode = None
    validate_daemon_identity(status, expected, socket_mode)


def validate_sandbox_identity(inspect: str, sandbox: str) -> None:
    match = re.search(r'^\s*Name:\s*(\S+)\s*$', inspect, re.MULTILINE)
    if match is None or match.group(1) != sandbox:
        raise NetworkGateError('created Sandbox identity could not be verified')


def validate_sandbox_stopped(inspect: str, sandbox: str) -> None:
    """Require the exact Task Sandbox name and a stopped-state inspection row."""
    if sandbox_state(inspect, sandbox) is not SandboxState.STOPPED:
        raise NetworkGateError('Task Sandbox stopped state was not verified')


def sandbox_state(inspect: str, sandbox: str) -> SandboxState:
    """Parse the state only after binding the inspection to the expected Sandbox name."""
    validate_sandbox_identity(inspect, sandbox)
    match = re.search(r'^\s*(?:Status|State):\s*(running|stopped)\s*$', inspect,
                      re.MULTILINE | re.IGNORECASE)
    if match is None:
        raise NetworkGateError('Task Sandbox state is unavailable or unknown')
    try:
        return SandboxState(match.group(1).lower())
    except ValueError:
        raise NetworkGateError('Task Sandbox state is unavailable or unknown') from None


def probe_guest_broker(
    runner: PolicyRunner,
    sandbox: str,
    host: str,
    port: int,
    ca_data: bytes,
    *,
    timeout: int = 30,
) -> None:
    """Measure Guest egress denials and verify the Broker TLS route before M1."""
    if (host not in {'host.docker.internal', '127.0.0.1'}
            or not 1 <= port <= 65535
            or not 0 < len(ca_data) <= 64 * 1024):
        raise NetworkGateError('Guest Broker probe inputs are outside the fixed contract')
    runner.sbx_feed(
        'exec', '-i', sandbox, 'python3', '-c', _GUEST_NETWORK_PROBE,
        host, str(port), data=ca_data, timeout=timeout,
    )


def validate_policy_check(raw: str, exit_code: int, sandbox: str, resource: str,
                          expected_allowed: bool, *, expected_target: str | None = None,
                          protocol: Literal['tcp', 'udp'] = 'tcp') -> None:
    try:
        value: JsonValue = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise NetworkGateError('daemon policy check is not valid JSON') from exc
    target = resource if expected_target is None else expected_target
    expected_exit = 0 if expected_allowed else 1
    if (not isinstance(value, dict) or type(value.get('allowed')) is not bool
            or value.get('allowed') is not expected_allowed
            or exit_code != expected_exit
            or value.get('action') != f'net:connect:{protocol}'
            or value.get('context') != f'sandbox:{sandbox}'
            or value.get('resource_type') != 'net:domain'
            or value.get('resource_value') != resource or value.get('target') != target
            or value.get('type') != 'network'):
        raise NetworkGateError('daemon policy check result does not match the expected decision')
    if not expected_allowed and (value.get('deny_kind') != 'implicit'
                                 or value.get('reason') != 'No matching allow rule (default deny)'):
        raise NetworkGateError('daemon policy check did not report the measured implicit deny')


def _check(runner: PolicyRunner, sandbox: str, target: str,
           resource_value: str, allowed: bool,
           protocol: Literal['tcp', 'udp'] = 'tcp') -> None:
    exit_code, output = runner.sbx_result(
        'policy', 'check', 'network', '--json', '--sandbox', sandbox,
        '--protocol', protocol, target,
    )
    validate_policy_check(
        output, exit_code, sandbox, resource_value, allowed,
        expected_target=resource_value, protocol=protocol,
    )


def run_network_gate(
    runner: PolicyRunner, sandbox: str, broker_port: int,
) -> ScopedNetworkAllow:
    if not 1 <= broker_port <= 65535:
        raise NetworkGateError('Broker port is outside the valid TCP port range')
    resource = f'localhost:{broker_port}'
    _check(runner, sandbox, resource, resource, False)
    _ = runner.sbx('--no-input', 'policy', 'allow', 'network', '--sandbox', sandbox,
                   '--protocol', 'tcp', resource)
    after = runner.sbx('policy', 'ls', '--json', capture=True)
    validate_policy_listing(after, sandbox, 'after', resource)
    _check(runner, sandbox, resource, resource, True)
    _check(
        runner, sandbox, f'host.docker.internal:{broker_port}', resource, True,
    )
    other_port = broker_port % 65535 + 1
    other_target = f'localhost:{other_port}'
    _check(runner, sandbox, other_target, other_target, False)
    _check(runner, sandbox, 'example.com:443', 'example.com:443', False)
    _check(runner, sandbox, '1.1.1.1:53', '1.1.1.1:53', False, 'udp')
    _check(runner, sandbox, 'example.com:53', 'example.com:53', False, 'udp')
    _check(
        runner, sandbox, f'host.docker.internal:{broker_port}',
        f'host.docker.internal:{broker_port}', False, 'udp',
    )
    return scoped_network_allow(after, sandbox, resource)
