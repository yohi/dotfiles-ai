from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final, Protocol, TypeAlias


class NetworkGateError(Exception):
    """An invalid Sandbox network-policy or Task identity observation."""


class PolicyRunner(Protocol):
    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str: ...

    def sbx_result(self, *args: str, timeout: int | None = 180) -> tuple[int, str]: ...

    def sbx_feed(self, *args: str, data: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class ScopedNetworkAllow:
    """Identity of the exact Task-owned sandbox-scoped Broker allow rule."""

    sandbox: str
    sandbox_id: str
    policy_id: str
    rule_id: str
    resource: str


JsonValue: TypeAlias = (
    str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
)

_RULE_ID: Final[re.Pattern[str]] = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
)
_NETWORK_ACTIONS: Final[frozenset[str]] = frozenset({
    'net:connect:tcp', 'net:connect:udp',
})
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


def validate_policy_listing(
    raw: str,
    sandbox: str,
    stage: str,
    allow_resource: str | None = None,
) -> None:
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


def scoped_network_allow(
    raw: str,
    sandbox: str,
    resource: str,
) -> ScopedNetworkAllow:
    """Parse the sole active Broker allow after validating the full listing."""
    validate_policy_listing(raw, sandbox, 'after', resource)
    scoped = [
        rule for rule in _decode_rules(raw)
        if rule.get('scope') == f'sandbox:{sandbox}'
        and rule.get('resource_type') == 'network'
        and rule.get('status') == 'active'
    ]
    if len(scoped) != 1:
        raise NetworkGateError('Sandbox-scoped Broker allow identity is missing or ambiguous')
    rule = scoped[0]
    sandbox_id = rule.get('sandbox_id')
    policy_id = rule.get('policy_id')
    rule_id = rule.get('id')
    if (not isinstance(sandbox_id, str) or not isinstance(policy_id, str)
            or not isinstance(rule_id, str)):
        raise NetworkGateError('Sandbox-scoped Broker allow identity is invalid')
    return ScopedNetworkAllow(sandbox, sandbox_id, policy_id, rule_id, resource)


def find_scoped_network_allow(
    raw: str,
    sandbox: str,
    resource: str,
) -> ScopedNetworkAllow | None:
    """Return this Sandbox's Broker rule, or validate default-deny if absent."""
    scoped = [
        rule for rule in _decode_rules(raw)
        if rule.get('scope') == f'sandbox:{sandbox}'
        and rule.get('resource_type') == 'network'
        and rule.get('status') == 'active'
    ]
    if not scoped:
        validate_policy_listing(raw, sandbox, 'before')
        return None
    return scoped_network_allow(raw, sandbox, resource)


def find_task_broker_allow(raw: str, sandbox: str) -> ScopedNetworkAllow | None:
    """Discover only this Task's loopback-TCP rule from a policy readback."""
    scoped = [
        rule for rule in _decode_rules(raw)
        if rule.get('scope') == f'sandbox:{sandbox}'
        and rule.get('resource_type') == 'network'
        and rule.get('status') == 'active'
    ]
    if not scoped:
        validate_policy_listing(raw, sandbox, 'before')
        return None
    if len(scoped) != 1:
        raise NetworkGateError('Task Sandbox has multiple active network rules')
    resources = scoped[0].get('resources')
    if not isinstance(resources, list) or len(resources) != 1:
        raise NetworkGateError('Task Broker allow resource is ambiguous')
    resource = resources[0]
    match = re.fullmatch(r'localhost:([1-9][0-9]{0,4})', resource) \
        if isinstance(resource, str) else None
    if match is None or not 1 <= int(match.group(1)) <= 65535:
        raise NetworkGateError('Task Broker allow is not a loopback TCP resource')
    return scoped_network_allow(raw, sandbox, resource)


def revoke_network_allow(runner: PolicyRunner, expected: ScopedNetworkAllow) -> None:
    """Remove only the exact still-matching rule and verify policy readback."""
    current = runner.sbx('policy', 'ls', '--json', capture=True)
    if scoped_network_allow(current, expected.sandbox, expected.resource) != expected:
        raise NetworkGateError('Task-owned Broker allow identity changed before cleanup')
    runner.sbx(
        '--no-input', 'policy', 'rm', 'network', '--id', expected.rule_id,
        '--sandbox', expected.sandbox,
    )
    updated = runner.sbx('policy', 'ls', '--json', capture=True)
    validate_policy_listing(updated, expected.sandbox, 'before')
    if any(rule.get('id') == expected.rule_id for rule in _decode_rules(updated)):
        raise NetworkGateError('Task-owned Broker allow remains after removal readback')
