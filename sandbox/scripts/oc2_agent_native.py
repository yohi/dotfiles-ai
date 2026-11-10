from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NotRequired, Protocol, TypedDict, TypeAlias, assert_never


JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']


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
    allowed_models: list[str]
    runtime: dict[str, JsonValue] | None


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


NATIVE_SCHEMA: Final[str] = 'dotfiles-ai/oc2-native/v3'
RUNTIME_THEMES: Final[frozenset[str]] = frozenset({
    'aura', 'ayu', 'carbonfox', 'catppuccin', 'catppuccin-frappe',
    'catppuccin-macchiato', 'cobalt2', 'cursor', 'dracula', 'everforest',
    'flexoki', 'github', 'gruvbox', 'kanagawa', 'lucent-orng', 'matrix',
    'material', 'mercury', 'monokai', 'nightowl', 'nord', 'one-dark',
    'opencode', 'orng', 'osaka-jade', 'palenight', 'rosepine', 'solarized',
    'system', 'synthwave84', 'tokyonight', 'vercel', 'vesper', 'zenburn',
})
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


def _agent_config(name: AgentName, model: str) -> AgentJSON:
    definition = _agent_definitions()[name]
    mode = AgentMode.PRIMARY if name is AgentName.HEPHAESTUS else AgentMode.SUBAGENT
    return {
        'mode': mode.value,
        'model': model,
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
        value = _agent_config(selection.name, selection.model)
        match selection.name:
            case AgentName.HEPHAESTUS:
                agents['hephaestus'] = value
            case AgentName.ORACLE:
                agents['oracle'] = value
            case unreachable:
                assert_never(unreachable)
    allowed_models = sorted(config.allowed_models or {selection.model for selection in config.agents})
    if any(selection.model not in allowed_models for selection in config.agents):
        raise ValueError('Native Agent model is not allowlisted')
    runtime = config.runtime
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
        'allowed_models': allowed_models,
        'runtime': runtime.as_json() if runtime is not None else None,
    }
    payload['agents'] = validate_agent_map(payload['agents'], allowed_models)
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

    @property
    def allowed_models(self) -> tuple[str, ...]: ...

    @property
    def runtime(self) -> NativeRuntimeProtocol | None: ...


class NativeRuntimeProtocol(Protocol):
    def as_json(self) -> dict[str, JsonValue]: ...


def validate_agent_map(value: JsonValue | AgentMap, allowed_models: list[str]) -> AgentMap:
    if not isinstance(value, dict) or set(value) - {name.value for name in AgentName}:
        raise ValueError('unapproved Native Agent map')
    result: AgentMap = {}
    for raw_name in value:
        name = parse_agent_name(raw_name)
        raw_agent = value[raw_name]
        if not isinstance(raw_agent, dict):
            raise ValueError('Native Agent configuration is not allowlisted')
        model = raw_agent.get('model')
        expected = _agent_config(name, model if isinstance(model, str) else '')
        if raw_agent != expected or model not in allowed_models:
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
            'schema', 'source_sha256', 'agents', 'plugins', 'mcp', 'allowed_models', 'runtime'}:
        raise ValueError('invalid native Agent manifest fields')
    if decoded['schema'] != NATIVE_SCHEMA:
        raise ValueError('unexpected native Agent manifest schema')
    source_sha = decoded['source_sha256']
    if not isinstance(source_sha, str) or re.fullmatch(r'[0-9a-f]{64}', source_sha) is None:
        raise ValueError('invalid native Agent source SHA-256')
    raw_allowed_models = decoded['allowed_models']
    if not isinstance(raw_allowed_models, list):
        raise ValueError('invalid Native Agent model allowlist')
    allowed_models: list[str] = []
    for model in raw_allowed_models:
        if (not isinstance(model, str) or re.fullmatch(
            r'(openai|cloudflare-ai-gateway-custom)/[A-Za-z0-9._/-]+', model,
        ) is None):
            raise ValueError('invalid Native Agent model allowlist')
        allowed_models.append(model)
    if len(allowed_models) != len(set(allowed_models)):
        raise ValueError('invalid Native Agent model allowlist')
    agents = validate_agent_map(decoded['agents'], allowed_models)
    plugins, mcp = validate_component_selection(decoded['plugins'], decoded['mcp'])
    runtime = validate_runtime_options(decoded['runtime'])
    return NativePayload(
        schema=NATIVE_SCHEMA,
        source_sha256=source_sha,
        agents=agents,
        plugins=plugins,
        mcp=mcp,
        allowed_models=allowed_models,
        runtime=runtime,
    )


def validate_runtime_options(value: JsonValue) -> dict[str, JsonValue] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        'theme', 'mcpExecutionTimeoutMs', 'watchdog', 'sibylObserver',
    }:
        raise ValueError('invalid Runtime option fields')
    theme = value['theme']
    if not isinstance(theme, str) or theme not in RUNTIME_THEMES:
        raise ValueError('invalid Runtime theme')
    mcp_timeout = value['mcpExecutionTimeoutMs']
    if type(mcp_timeout) is not int or not 1000 <= mcp_timeout <= 600000:
        raise ValueError('MCP execution timeout violates safety bounds')
    watchdog = value['watchdog']
    if (not isinstance(watchdog, dict) or set(watchdog) != {
        'enabled', 'stage1Ms', 'stage2Ms', 'maxPings', 'maxToolGateCycles',
        'notifierType', 'notifyWaiting',
    }):
        raise ValueError('invalid Akane Runtime options')
    if (watchdog['enabled'] is not True or type(watchdog['stage1Ms']) is not int
            or not 1000 <= watchdog['stage1Ms'] <= 3600000
            or type(watchdog['stage2Ms']) is not int or watchdog['stage2Ms'] < 86400000
            or type(watchdog['maxPings']) is not int or watchdog['maxPings'] != 1
            or type(watchdog['maxToolGateCycles']) is not int
            or not 1 <= watchdog['maxToolGateCycles'] <= 8
            or watchdog['notifierType'] != 'tmux'
            or type(watchdog['notifyWaiting']) is not bool):
        raise ValueError('Akane Runtime options violate safety bounds')
    observer = value['sibylObserver']
    if (not isinstance(observer, dict) or set(observer) != {
        'enabled', 'maxVisibleSubagents', 'showModel', 'showProvider',
        'showLatestText', 'showReasoningSummary',
    }):
        raise ValueError('invalid Sibyl Runtime options')
    if (observer['enabled'] is not True
            or type(observer['maxVisibleSubagents']) is not int
            or not 1 <= observer['maxVisibleSubagents'] <= 16
            or any(type(observer[key]) is not bool for key in (
                'showModel', 'showProvider', 'showLatestText', 'showReasoningSummary',
            ))):
        raise ValueError('Sibyl Runtime options violate safety bounds')
    return value


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
