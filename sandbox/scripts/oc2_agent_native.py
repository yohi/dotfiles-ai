from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NotRequired, Protocol, TypedDict, TypeAlias, assert_never


class AgentName(StrEnum):
    HEPHAESTUS = 'hephaestus'
    ORACLE = 'oracle'


class AgentMode(StrEnum):
    PRIMARY = 'primary'
    SUBAGENT = 'subagent'


class Effect(StrEnum):
    ALLOW = 'allow'
    DENY = 'deny'
    ASK = 'ask'


class PluginId(StrEnum):
    SUPERPOWERS = 'superpowers'


class McpServerId(StrEnum):
    OC2_STATUS = 'oc2-status'


@dataclass(frozen=True, slots=True)
class Permission:
    action: str
    resource: str
    effect: Effect

    def as_json(self) -> PermissionJSON:
        return {'action': self.action, 'resource': self.resource, 'effect': self.effect.value}


class PermissionJSON(TypedDict):
    action: str
    resource: str
    effect: str


class AgentJSON(TypedDict):
    mode: str
    model: str
    description: str
    system: str
    permissions: list[PermissionJSON]


class AgentMap(TypedDict):
    hephaestus: NotRequired[AgentJSON]
    oracle: NotRequired[AgentJSON]


class PluginSelectionJSON(TypedDict):
    enabled: bool
    allowlist: list[str]


class McpSelectionJSON(TypedDict):
    enabled: bool
    servers: list[str]


class NativePayload(TypedDict):
    schema: str
    source_sha256: str
    agents: AgentMap
    plugins: PluginSelectionJSON
    mcp: McpSelectionJSON


@dataclass(frozen=True, slots=True)
class AgentSelection:
    name: AgentName
    mode: AgentMode
    model: str


@dataclass(frozen=True, slots=True)
class PluginSelection:
    enabled: bool
    allowlist: tuple[PluginId, ...]


@dataclass(frozen=True, slots=True)
class McpSelection:
    enabled: bool
    servers: tuple[McpServerId, ...]


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    description: str
    system: str
    permissions: tuple[Permission, ...]


NATIVE_SCHEMA: Final[str] = 'dotfiles-ai/oc2-native/v2'
NATIVE_MODEL: Final[str] = 'openai/gpt-6-luna'
SUPERPOWERS_REPOSITORY: Final[str] = 'obra/superpowers'
SUPERPOWERS_REF: Final[str] = 'v6.4.2'
SUPERPOWERS_COMMIT: Final[str] = '8ca22dba9a94f28898bbce59f2537ff4d87c747d'
SUPERPOWERS_VERSION: Final[str] = '6.4.2'
SUPERPOWERS_SOURCE_PATH: Final[str] = 'verification-superpowers'
SUPERPOWERS_FILE_COUNT: Final[int] = 229
SUPERPOWERS_TOTAL_BYTES: Final[int] = 1_974_678
SUPERPOWERS_TREE_SHA256: Final[str] = (
    '19ba95fe50e96fb94d8260972cb50595ed31ada3f993e370b381a1e7718c5036'
)


def parse_agent_name(value: str) -> AgentName:
    match value:
        case AgentName.HEPHAESTUS:
            return AgentName.HEPHAESTUS
        case AgentName.ORACLE:
            return AgentName.ORACLE
        case _:
            raise ValueError('unapproved agent: ' + value)


def _agent_definitions() -> dict[AgentName, AgentDefinition]:
    return {
        AgentName.HEPHAESTUS: AgentDefinition(
            description='Implements user-requested code changes with focused tests.',
            system=(
                'Implement only the user-approved change. Preserve existing security boundaries. '
                'Ask before shell execution or delegating to another agent.'
            ),
            permissions=(
                Permission('*', '*', Effect.DENY),
                Permission('read', '*', Effect.ALLOW),
                Permission('glob', '*', Effect.ALLOW),
                Permission('grep', '*', Effect.ALLOW),
                Permission('lsp', '*', Effect.ALLOW),
                Permission('edit', '*', Effect.ASK),
                Permission('bash', '*', Effect.ASK),
                Permission('task', '*', Effect.ASK),
                Permission('webfetch', '*', Effect.DENY),
                Permission('websearch', '*', Effect.DENY),
                Permission('mcp.use', '*', Effect.DENY),
                Permission('read', '*.env', Effect.DENY),
                Permission('read', '*.env.*', Effect.DENY),
                Permission('read', '*.env.example', Effect.ALLOW),
            ),
        ),
        AgentName.ORACLE: AgentDefinition(
            description='Provides read-only technical analysis and options.',
            system=(
                'Analyze the supplied code and evidence without changing files, executing commands, '
                'delegating, using external tools, or connecting to MCP servers.'
            ),
            permissions=(
                Permission('*', '*', Effect.DENY),
                Permission('read', '*', Effect.ALLOW),
                Permission('glob', '*', Effect.ALLOW),
                Permission('grep', '*', Effect.ALLOW),
                Permission('lsp', '*', Effect.ALLOW),
                Permission('edit', '*', Effect.DENY),
                Permission('bash', '*', Effect.DENY),
                Permission('task', '*', Effect.DENY),
                Permission('webfetch', '*', Effect.DENY),
                Permission('websearch', '*', Effect.DENY),
                Permission('mcp.use', '*', Effect.DENY),
                Permission('read', '*.env', Effect.DENY),
                Permission('read', '*.env.*', Effect.DENY),
                Permission('read', '*.env.example', Effect.ALLOW),
            ),
        ),
    }


def _agent_config(name: AgentName) -> AgentJSON:
    definition = _agent_definitions()[name]
    mode = AgentMode.PRIMARY if name is AgentName.HEPHAESTUS else AgentMode.SUBAGENT
    return {
        'mode': mode.value,
        'model': NATIVE_MODEL,
        'description': definition.description,
        'system': definition.system,
        'permissions': [permission.as_json() for permission in definition.permissions],
    }


def build_native_payload(config: NativeConfigProtocol) -> NativePayload:
    plugin_allowlist = [plugin.value for plugin in config.plugins.allowlist]
    mcp_servers = [server.value for server in config.mcp.servers]
    if config.plugins.enabled != config.mcp.enabled:
        raise ValueError('Plugin and MCP verification selections must match')
    if config.plugins.enabled and (
            plugin_allowlist != [PluginId.SUPERPOWERS.value]
            or mcp_servers != [McpServerId.OC2_STATUS.value]):
        raise ValueError('Plugin/MCP selection is not allowlisted')
    if not config.plugins.enabled and (plugin_allowlist or mcp_servers):
        raise ValueError('disabled Plugin/MCP selections must be empty')
    agents: AgentMap = {}
    for selection in config.agents:
        value = _agent_config(selection.name)
        match selection.name:
            case AgentName.HEPHAESTUS:
                agents['hephaestus'] = value
            case AgentName.ORACLE:
                agents['oracle'] = value
            case unreachable:
                assert_never(unreachable)
    payload: NativePayload = {
        'schema': NATIVE_SCHEMA,
        'source_sha256': config.source_sha256,
        'agents': agents,
        'plugins': {
            'enabled': config.plugins.enabled,
            'allowlist': plugin_allowlist,
        },
        'mcp': {
            'enabled': config.mcp.enabled,
            'servers': mcp_servers,
        },
    }
    payload['agents'] = validate_agent_map(payload['agents'])
    return payload


class NativeConfigProtocol(Protocol):
    @property
    def source_sha256(self) -> str: ...

    @property
    def agents(self) -> tuple[AgentSelection, ...]: ...

    @property
    def plugins(self) -> PluginSelection: ...

    @property
    def mcp(self) -> McpSelection: ...


JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']


def validate_agent_map(value: JsonValue | AgentMap) -> AgentMap:
    if not isinstance(value, dict) or set(value) - {name.value for name in AgentName}:
        raise ValueError('unapproved Native Agent map')
    result: AgentMap = {}
    for raw_name in value:
        name = parse_agent_name(raw_name)
        raw_agent = value.get(raw_name)
        expected = _agent_config(name)
        if raw_agent != expected:
            raise ValueError('Native Agent configuration is not allowlisted')
        match name:
            case AgentName.HEPHAESTUS:
                result['hephaestus'] = expected
            case AgentName.ORACLE:
                result['oracle'] = expected
            case unreachable:
                assert_never(unreachable)
    return result


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate native config key')
        result[key] = value
    return result


def validate_native_asset(raw: bytes) -> NativePayload:
    try:
        decoded: JsonValue = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid native Agent manifest') from exc
    if not isinstance(decoded, dict) or set(decoded) != {
            'schema', 'source_sha256', 'agents', 'plugins', 'mcp'}:
        raise ValueError('invalid native Agent manifest fields')
    if decoded['schema'] != NATIVE_SCHEMA:
        raise ValueError('unexpected native Agent manifest schema')
    source_sha = decoded['source_sha256']
    if not isinstance(source_sha, str) or re.fullmatch(r'[0-9a-f]{64}', source_sha) is None:
        raise ValueError('invalid native Agent source SHA-256')
    agents = validate_agent_map(decoded['agents'])
    plugins, mcp = validate_component_selection(decoded['plugins'], decoded['mcp'])
    return NativePayload(
        schema=NATIVE_SCHEMA,
        source_sha256=source_sha,
        agents=agents,
        plugins=plugins,
        mcp=mcp,
    )


def validate_component_selection(
    plugins: JsonValue,
    mcp: JsonValue,
) -> tuple[PluginSelectionJSON, McpSelectionJSON]:
    """Validate the fixed Plugin and MCP selection projection."""
    if (not isinstance(plugins, dict) or set(plugins) != {'enabled', 'allowlist'}
            or not isinstance(mcp, dict) or set(mcp) != {'enabled', 'servers'}):
        raise ValueError('invalid Plugin/MCP selection fields')
    plugin_enabled = plugins['enabled']
    allowlist = plugins['allowlist']
    mcp_enabled = mcp['enabled']
    servers = mcp['servers']
    if (type(plugin_enabled) is not bool or type(mcp_enabled) is not bool
            or not isinstance(allowlist, list) or not isinstance(servers, list)):
        raise ValueError('invalid Plugin/MCP selection types')
    normalized_allowlist: list[str] = []
    for item in allowlist:
        if not isinstance(item, str):
            raise ValueError('invalid Plugin/MCP selection types')
        normalized_allowlist.append(item)
    normalized_servers: list[str] = []
    for item in servers:
        if not isinstance(item, str):
            raise ValueError('invalid Plugin/MCP selection types')
        normalized_servers.append(item)
    expected_plugins = [] if not plugin_enabled else [PluginId.SUPERPOWERS.value]
    expected_servers = [] if not mcp_enabled else [McpServerId.OC2_STATUS.value]
    if normalized_allowlist != expected_plugins or normalized_servers != expected_servers:
        raise ValueError('Plugin/MCP selection is not allowlisted')
    if plugin_enabled != mcp_enabled:
        raise ValueError('Plugin and MCP verification selections must match')
    return (
        {'enabled': plugin_enabled, 'allowlist': normalized_allowlist},
        {'enabled': mcp_enabled, 'servers': normalized_servers},
    )
