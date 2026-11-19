from __future__ import annotations

import json
import os
import pathlib
import re
import stat
from typing import Final, Protocol, TypeAlias


class NetworkGateError(Exception):
    pass


class PolicyRunner(Protocol):
    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str: ...

    def sbx_result(self, *args: str, timeout: int | None = 180) -> tuple[int, str]: ...


JsonValue: TypeAlias = (
    str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
)

_APP_NAME: Final[re.Pattern[str]] = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]')
_RULE_ID: Final[re.Pattern[str]] = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
)
_NETWORK_ACTIONS: Final[frozenset[str]] = frozenset({
    'net:connect:tcp', 'net:connect:udp',
})


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


def _decode_rules(raw: str) -> list[dict[str, JsonValue]]:
    try:
        value: JsonValue = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise NetworkGateError('daemon policy readback is not valid JSON') from exc
    if not isinstance(value, dict):
        raise NetworkGateError('daemon policy readback has no rules array')
    rules = value.get('rules')
    if not isinstance(rules, list):
        raise NetworkGateError('daemon policy readback has no rules array')
    parsed_rules: list[dict[str, JsonValue]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise NetworkGateError('daemon policy readback contains an invalid rule')
        parsed_rules.append(rule)
    return parsed_rules


def validate_policy_listing(raw: str, sandbox: str, stage: str,
                            allow_resource: str | None = None) -> None:
    if stage not in {'global', 'before', 'after'}:
        raise NetworkGateError('unknown policy validation stage')
    rules = _decode_rules(raw)
    fallback: list[dict[str, JsonValue]] = []
    scoped: list[dict[str, JsonValue]] = []
    for rule in rules:
        resource_type = rule.get('resource_type')
        if resource_type not in {'network', 'filesystem:read', 'filesystem:write'}:
            if rule.get('status') == 'active':
                raise NetworkGateError('daemon policy contains an unknown active rule')
            continue
        if resource_type != 'network' or rule.get('status') != 'active':
            continue
        if rule.get('scope') == 'global':
            actions = rule.get('actions')
            action_names = (
                [action for action in actions if isinstance(action, str)]
                if isinstance(actions, list) else []
            )
            if (rule.get('id') == 'default-deny-all'
                    and rule.get('name') == 'default-deny-all'
                    and rule.get('decision') == 'deny'
                    and rule.get('applies_to') == 'all'
                    and rule.get('resources') == ['**']
                    and isinstance(actions, list)
                    and len(action_names) == len(actions)
                    and sorted(action_names) == sorted(_NETWORK_ACTIONS)
                    and len(action_names) == len(_NETWORK_ACTIONS)):
                fallback.append(rule)
            else:
                raise NetworkGateError('daemon has an unrecognized active global network rule')
        elif rule.get('scope') == f'sandbox:{sandbox}':
            scoped.append(rule)
        else:
            raise NetworkGateError('daemon has an active network rule for an unexpected scope')
    if len(fallback) != 1:
        raise NetworkGateError('active global default-deny-all policy is missing or ambiguous')
    if stage in {'global', 'before'}:
        if scoped:
            raise NetworkGateError('Sandbox has unexpected active network policy before allow')
        return
    if allow_resource is None or len(scoped) != 1:
        raise NetworkGateError('Sandbox-scoped Broker allow policy is missing or ambiguous')
    allow = scoped[0]
    rule_id = allow.get('id')
    policy_id = allow.get('policy_id')
    if (not isinstance(rule_id, str) or _RULE_ID.fullmatch(rule_id) is None
            or not isinstance(policy_id, str) or _RULE_ID.fullmatch(policy_id) is None
            or allow.get('decision') != 'allow' or allow.get('resources') != [allow_resource]
            or allow.get('actions') != ['net:connect:tcp']
            or allow.get('sandbox_id') != sandbox
            or allow.get('applies_to') != f'sandbox:{sandbox}'):
        raise NetworkGateError('Sandbox-scoped Broker allow policy does not match expected identity')


def validate_policy_check(raw: str, exit_code: int, sandbox: str, resource: str,
                          expected_allowed: bool, *, expected_target: str | None = None) -> None:
    try:
        value: JsonValue = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise NetworkGateError('daemon policy check is not valid JSON') from exc
    target = resource if expected_target is None else expected_target
    expected_exit = 0 if expected_allowed else 1
    if (not isinstance(value, dict) or type(value.get('allowed')) is not bool
            or value.get('allowed') is not expected_allowed
            or exit_code != expected_exit
            or value.get('action') != 'net:connect:tcp'
            or value.get('context') != f'sandbox:{sandbox}'
            or value.get('resource_type') != 'net:domain'
            or value.get('resource_value') != resource or value.get('target') != target
            or value.get('type') != 'network'):
        raise NetworkGateError('daemon policy check result does not match the expected decision')
    if not expected_allowed and (value.get('deny_kind') != 'implicit'
                                 or value.get('reason') != 'No matching allow rule (default deny)'):
        raise NetworkGateError('daemon policy check did not report the measured implicit deny')


def _check(runner: PolicyRunner, sandbox: str, target: str,
           resource_value: str, allowed: bool) -> None:
    exit_code, output = runner.sbx_result(
        'policy', 'check', 'network', '--json', '--sandbox', sandbox,
        '--protocol', 'tcp', target,
    )
    validate_policy_check(
        output, exit_code, sandbox, resource_value, allowed,
        expected_target=resource_value,
    )


def run_network_gate(runner: PolicyRunner, sandbox: str, broker_port: int) -> None:
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
