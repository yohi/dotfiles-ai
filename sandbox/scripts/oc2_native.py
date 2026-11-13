from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, TypedDict

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from oc2_agent_native import (
    AgentMode,
    AgentName,
    AgentSelection,
    JsonValue,
    McpServerId,
    McpSelection,
    NativePayload as NativePayload,
    PluginId,
    PluginSelection,
    SUPERPOWERS_COMMIT,
    SUPERPOWERS_REF,
    SUPERPOWERS_REPOSITORY,
    build_native_payload as build_native_payload,
    parse_agent_name,
)
from oc2_phase4_selection import Phase4PluginSelection, parse_phase4_selection


ASSET_SOURCE_TO_TARGET: Final[Mapping[str, str]] = MappingProxyType({
    'global-rules/AGENTS.global.md': 'config/opencode/AGENTS.md',
    'global-rules/DOCS_STYLE.md': 'config/opencode/rules/DOCS_STYLE.md',
    'global-rules/GIT_STANDARDS.md': 'config/opencode/rules/GIT_STANDARDS.md',
    'global-rules/MARKDOWN.md': 'config/opencode/rules/MARKDOWN.md',
    'global-rules/META_PROMPT.md': 'config/opencode/rules/META_PROMPT.md',
    'global-rules/SHELL.md': 'config/opencode/rules/SHELL.md',
    'global-rules/STACKED_PR_WORKFLOW.md': 'config/opencode/rules/STACKED_PR_WORKFLOW.md',
    'agent-commands/build-skill.md': 'config/opencode/commands/build-skill.md',
    'agent-skills/custom/agent-skill-architect/SKILL.md': 'config/opencode/skills/agent-skill-architect/SKILL.md',
    'agent-skills/custom/config-modernizer/SKILL.md': 'config/opencode/skills/config-modernizer/SKILL.md',
})
ASSET_SOURCES: Final[frozenset[str]] = frozenset(ASSET_SOURCE_TO_TARGET)
RUNTIME_THEMES: Final[frozenset[str]] = frozenset({
    'aura', 'ayu', 'carbonfox', 'catppuccin', 'catppuccin-frappe',
    'catppuccin-macchiato', 'cobalt2', 'cursor', 'dracula', 'everforest',
    'flexoki', 'github', 'gruvbox', 'kanagawa', 'lucent-orng', 'matrix',
    'material', 'mercury', 'monokai', 'nightowl', 'nord', 'one-dark',
    'opencode', 'orng', 'osaka-jade', 'palenight', 'rosepine', 'solarized',
    'system', 'synthwave84', 'tokyonight', 'vercel', 'vesper', 'zenburn',
})


@dataclass(frozen=True, slots=True)
class WatchdogOptions:
    enabled: bool
    stage1_ms: int
    stage2_ms: int
    max_pings: int
    max_tool_gate_cycles: int
    notifier_type: str
    notify_waiting: bool

    def as_json(self) -> dict[str, JsonValue]:
        return {
            'enabled': self.enabled,
            'stage1Ms': self.stage1_ms,
            'stage2Ms': self.stage2_ms,
            'maxPings': self.max_pings,
            'maxToolGateCycles': self.max_tool_gate_cycles,
            'notifierType': self.notifier_type,
            'notifyWaiting': self.notify_waiting,
        }


@dataclass(frozen=True, slots=True)
class SibylObserverOptions:
    enabled: bool
    max_visible_subagents: int
    show_model: bool
    show_provider: bool
    show_latest_text: bool
    show_reasoning_summary: bool

    def as_json(self) -> dict[str, JsonValue]:
        return {
            'enabled': self.enabled,
            'maxVisibleSubagents': self.max_visible_subagents,
            'showModel': self.show_model,
            'showProvider': self.show_provider,
            'showLatestText': self.show_latest_text,
            'showReasoningSummary': self.show_reasoning_summary,
        }


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    theme: str
    mcp_execution_timeout_ms: int
    watchdog: WatchdogOptions
    sibyl_observer: SibylObserverOptions

    def as_json(self) -> dict[str, JsonValue]:
        return {
            'theme': self.theme,
            'mcpExecutionTimeoutMs': self.mcp_execution_timeout_ms,
            'watchdog': self.watchdog.as_json(),
            'sibylObserver': self.sibyl_observer.as_json(),
        }


@dataclass(frozen=True, slots=True)
class V2ProviderSelection:
    provider_id: str
    enabled: bool
    auth_method: Literal['docker_openai_oauth', 'docker_custom_secret']


@dataclass(frozen=True, slots=True)
class NativeConfig:
    source_sha256: str
    asset_sources: tuple[str, ...]
    agents: tuple[AgentSelection, ...]
    plugins: PluginSelection = PluginSelection(enabled=False, allowlist=())
    mcp: McpSelection = McpSelection(enabled=False, servers=())
    unified_runtime: bool = False
    phase4_plugins: Phase4PluginSelection = Phase4PluginSelection(
        enabled=False, allowlist=(), artifacts=(),
    )
    allowed_models: tuple[str, ...] = ()
    runtime: RuntimeOptions | None = None
    default_model: str | None = None
    provider_selections: tuple[V2ProviderSelection, ...] = ()


class SkillFrontmatter(TypedDict):
    name: str
    description: str


class NativeConfigError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


def _mapping(node: Node, label: str) -> dict[str, Node]:
    match node:
        case MappingNode(value=entries):
            result: dict[str, Node] = {}
            for key_node, value_node in entries:
                if not isinstance(key_node, ScalarNode) or key_node.tag != 'tag:yaml.org,2002:str':
                    raise NativeConfigError(f'{label} keys must be strings')
                key = key_node.value
                if key in result:
                    raise NativeConfigError(f'duplicate mapping key in {label}')
                result[key] = value_node
            return result
        case _:
            raise NativeConfigError(f'{label} must be a mapping')


def _string(node: Node, label: str) -> str:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:str', value=value) if value:
            return str(value)
        case _:
            raise NativeConfigError(f'{label} must be a non-empty string')


def _sequence(node: Node, label: str) -> tuple[Node, ...]:
    match node:
        case SequenceNode(value=items):
            return tuple(items)
        case _:
            raise NativeConfigError(f'{label} must be a sequence')


def parse_superpowers_lock(raw: bytes) -> str:
    """Parse an APM lockfile and return its pinned Superpowers commit.

    Accepts YAML bytes whose root mapping contains a ``dependencies`` sequence
    with exactly one ``superpowers`` entry for the approved repository. The
    entry must match the fixed host, ref, commit, version, and package type.
    Invalid/empty YAML, malformed mappings, missing dependencies, duplicate or
    absent Superpowers entries, and mismatched identity fields raise
    ``NativeConfigError``.
    """
    try:
        root = yaml.compose(raw, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise NativeConfigError('apm.lock.yaml is invalid') from exc
    if root is None:
        raise NativeConfigError('apm.lock.yaml is empty')
    lock = _mapping(root, 'apm.lock.yaml')
    dependencies_node = lock.get('dependencies')
    if dependencies_node is None:
        raise NativeConfigError('apm.lock.yaml dependencies are missing')
    dependencies = _sequence(dependencies_node, 'apm.lock.yaml dependencies')
    matches: list[dict[str, Node]] = []
    for dependency in dependencies:
        fields = _mapping(dependency, 'apm.lock.yaml dependency')
        repository_node = fields.get('repo_url')
        name_node = fields.get('name')
        if repository_node is None or name_node is None:
            continue
        if (_string(repository_node, 'dependency repo_url') == SUPERPOWERS_REPOSITORY
                and _string(name_node, 'dependency name') == 'superpowers'):
            matches.append(fields)
    if len(matches) != 1:
        raise NativeConfigError('APM lock must contain one Superpowers entry')
    entry = matches[0]
    expected = {
        'host': 'github.com',
        'resolved_ref': SUPERPOWERS_REF,
        'resolved_commit': SUPERPOWERS_COMMIT,
        'version': '6.4.2',
        'package_type': 'marketplace_plugin',
    }
    for key, value in expected.items():
        node = entry.get(key)
        if node is None or _string(node, 'Superpowers lock ' + key) != value:
            raise NativeConfigError('APM lock Superpowers identity mismatch')
    return str(SUPERPOWERS_COMMIT)


def _boolean(node: Node | None, label: str) -> bool:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='true'):
            return True
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='false'):
            return False
        case _:
            raise NativeConfigError(f'{label} must be a boolean')


def _integer(node: Node, label: str, minimum: int, maximum: int) -> int:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:int', value=value):
            parsed = yaml.safe_load(value)
            if type(parsed) is int and minimum <= parsed <= maximum:
                result = parsed
                return result
        case _:
            pass
    raise NativeConfigError(f'{label} is outside the supported range')


def _runtime_options(node: Node, mcp_execution_timeout_ms: int) -> RuntimeOptions:
    fields = _mapping(node, 'x-oc2-runtime')
    if set(fields) != {'enabled', 'theme', 'watchdog', 'sibylObserver'}:
        raise NativeConfigError('x-oc2-runtime fields are invalid')
    if not _boolean(fields['enabled'], 'x-oc2-runtime.enabled'):
        raise NativeConfigError('Unified Runtime cannot be disabled in its selected configuration')
    theme = _string(fields['theme'], 'x-oc2-runtime.theme')
    if theme not in RUNTIME_THEMES:
        raise NativeConfigError('x-oc2-runtime.theme is invalid')

    watchdog_fields = _mapping(fields['watchdog'], 'x-oc2-runtime.watchdog')
    if set(watchdog_fields) != {
        'enabled', 'stage1Ms', 'stage2Ms', 'maxPings', 'maxToolGateCycles',
        'notifierType', 'notifyWaiting',
    }:
        raise NativeConfigError('x-oc2-runtime.watchdog fields are invalid')
    if not _boolean(watchdog_fields['enabled'], 'watchdog.enabled'):
        raise NativeConfigError('Akane Watchdog must remain enabled for Sibyl state production')
    stage1 = _integer(watchdog_fields['stage1Ms'], 'watchdog.stage1Ms', 1000, 3600000)
    stage2 = _integer(watchdog_fields['stage2Ms'], 'watchdog.stage2Ms', 86400000, 2147483647)
    max_pings = _integer(watchdog_fields['maxPings'], 'watchdog.maxPings', 1, 1)
    max_cycles = _integer(watchdog_fields['maxToolGateCycles'], 'watchdog.maxToolGateCycles', 1, 8)
    notifier = _string(watchdog_fields['notifierType'], 'watchdog.notifierType')
    if notifier != 'tmux':
        raise NativeConfigError('watchdog.notifierType is not supported')
    notify_waiting = _boolean(watchdog_fields['notifyWaiting'], 'watchdog.notifyWaiting')
    watchdog = WatchdogOptions(
        True, stage1, stage2, max_pings, max_cycles, notifier, notify_waiting,
    )

    observer_fields = _mapping(fields['sibylObserver'], 'x-oc2-runtime.sibylObserver')
    if set(observer_fields) != {
        'enabled', 'maxVisibleSubagents', 'showModel', 'showProvider',
        'showLatestText', 'showReasoningSummary',
    }:
        raise NativeConfigError('x-oc2-runtime.sibylObserver fields are invalid')
    if not _boolean(observer_fields['enabled'], 'sibylObserver.enabled'):
        raise NativeConfigError('Sibyl Observer must remain enabled for sidebar visibility')
    observer = SibylObserverOptions(
        True,
        _integer(observer_fields['maxVisibleSubagents'], 'sibylObserver.maxVisibleSubagents', 1, 16),
        _boolean(observer_fields['showModel'], 'sibylObserver.showModel'),
        _boolean(observer_fields['showProvider'], 'sibylObserver.showProvider'),
        _boolean(observer_fields['showLatestText'], 'sibylObserver.showLatestText'),
        _boolean(observer_fields['showReasoningSummary'], 'sibylObserver.showReasoningSummary'),
    )
    return RuntimeOptions(theme, mcp_execution_timeout_ms, watchdog, observer)


def _mcp_execution_timeout_ms(top: dict[str, Node]) -> int:
    experimental_node = top.get('experimental')
    if experimental_node is None:
        raise NativeConfigError('experimental.mcp_timeout is required by the OC2 Runtime')
    experimental = _mapping(experimental_node, 'experimental')
    timeout_node = experimental.get('mcp_timeout')
    if timeout_node is None:
        raise NativeConfigError('experimental.mcp_timeout is required by the OC2 Runtime')
    return _integer(timeout_node, 'experimental.mcp_timeout', 1000, 600000)


def _model_configuration(
    top: dict[str, Node],
) -> tuple[str, tuple[V2ProviderSelection, ...], tuple[str, ...]]:
    settings_node = top.get('opencode_v2')
    if settings_node is None:
        raise NativeConfigError('opencode_v2 model configuration is required')
    settings = _mapping(settings_node, 'opencode_v2')
    required = {'default_model', 'deny_provider_fallback', 'deny_guest_auth', 'providers'}
    if not required <= set(settings) or set(settings) - required - {'allowed_models'}:
        raise NativeConfigError('opencode_v2 fields are invalid')
    default_model_node = settings.get('default_model')
    providers_node = settings.get('providers')
    catalog_node = top.get('provider')
    if default_model_node is None or providers_node is None or catalog_node is None:
        raise NativeConfigError('opencode_v2 model/provider fields are required')
    default_model = _string(default_model_node, 'opencode_v2.default_model')
    if _boolean(settings.get('deny_provider_fallback'), 'deny_provider_fallback') is not True:
        raise NativeConfigError('provider fallback must remain denied')
    if _boolean(settings.get('deny_guest_auth'), 'deny_guest_auth') is not True:
        raise NativeConfigError('Guest authentication must remain denied')
    providers = _mapping(providers_node, 'opencode_v2.providers')
    if set(providers) - {'openai', 'cloudflare-ai-gateway-custom'}:
        raise NativeConfigError('unapproved OpenCode v2 provider')
    catalog = _mapping(catalog_node, 'provider')
    allowed: set[str] = set()
    selections: list[V2ProviderSelection] = []
    for provider_id, provider_node in providers.items():
        selection = _mapping(provider_node, 'opencode_v2.providers.' + provider_id)
        if set(selection) != {'enabled', 'auth_method'}:
            raise NativeConfigError('provider selection fields are invalid')
        enabled = _boolean(selection['enabled'], 'provider.enabled')
        method = _string(selection['auth_method'], 'provider.auth_method')
        expected_method: Literal['docker_openai_oauth', 'docker_custom_secret'] = (
            'docker_openai_oauth' if provider_id == 'openai' else 'docker_custom_secret'
        )
        if method != expected_method:
            raise NativeConfigError('provider authentication method is not approved')
        selections.append(V2ProviderSelection(provider_id, enabled, expected_method))
        if not enabled:
            continue
        source_node = catalog.get(provider_id)
        if source_node is None:
            raise NativeConfigError('enabled provider catalog is missing')
        source = _mapping(source_node, 'provider.' + provider_id)
        if provider_id == 'openai':
            models_node = source.get('whitelist')
            if models_node is None:
                raise NativeConfigError('provider.openai.whitelist is required')
            for model_node in _sequence(models_node, 'provider.openai.whitelist'):
                allowed.add('openai/' + _string(model_node, 'OpenAI model'))
        else:
            models_node = source.get('models')
            if models_node is None:
                raise NativeConfigError('Cloudflare Custom model catalog is missing')
            models = _mapping(models_node, 'provider.' + provider_id + '.models')
            allowed.update(provider_id + '/' + model for model in models)
    if not allowed or default_model not in allowed:
        raise NativeConfigError('default model is not in an enabled APM provider catalog')
    models_node = settings.get('allowed_models')
    if models_node is not None:
        configured = tuple(
            _string(item, 'opencode_v2.allowed_models entry')
            for item in _sequence(models_node, 'opencode_v2.allowed_models')
        )
        if (not configured or len(configured) != len(set(configured))
                or not set(configured) <= allowed or default_model not in configured):
            raise NativeConfigError('opencode_v2.allowed_models is not a valid provider subset')
        allowed = set(configured)
    return default_model, tuple(selections), tuple(sorted(allowed))


def _plugin_id(value: str) -> PluginId:
    match value:
        case 'superpowers':
            return PluginId.SUPERPOWERS
        case _:
            raise NativeConfigError('unapproved plugin candidate')


def _mcp_server_id(value: str) -> McpServerId:
    match value:
        case 'oc2-status':
            return McpServerId.OC2_STATUS
        case _:
            raise NativeConfigError('unapproved MCP server')


def parse_apm_native(
    raw: bytes,
    *,
    require_oc2_assets: bool = False,
    verification_only: bool = False,
    phase4_plugins: bool = False,
) -> NativeConfig:
    """Parse YAML APM bytes into a digest-bound Native configuration.

    Accepts a YAML root mapping with either no OC2 extensions or the complete
    ``x-oc2-assets``, ``x-oc2-agents``, ``x-oc2-plugins``, and ``x-oc2-mcp``
    extension set. Assets are returned in declared order after validating
    unique safe allowlisted paths. The approved Agent selections are returned
    as an ordered tuple (Agents may be absent or the fixed approved pair).
    Plugin and MCP selections default to disabled and
    empty; when ``verification_only`` is true, their fixed candidate lists are
    selected and must include exactly ``superpowers`` and ``oc2-status``.
    ``require_oc2_assets`` requires the OC2 extension set even when no other
    extension is present. The result includes the SHA-256 of the exact input
    bytes. Invalid/empty YAML, incomplete extensions, malformed or duplicate
    fields, unsupported selections, and rejected activation raise
    ``NativeConfigError``.
    """
    try:
        root = yaml.compose(raw, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise NativeConfigError('apm.yml is invalid') from exc
    if root is None:
        raise NativeConfigError('apm.yml is empty')
    top = _mapping(root, 'apm.yml')
    model_configuration = (
        _model_configuration(top) if 'opencode_v2' in top else None
    )
    if model_configuration is None:
        default_model = None
        provider_selections: tuple[V2ProviderSelection, ...] = ()
        allowed_models: tuple[str, ...] = ()
    else:
        default_model, provider_selections, allowed_models = model_configuration
    phase4_node = top.get('x-oc2-phase4')
    runtime_node = top.get('x-oc2-runtime')
    agents_node = top.get('x-oc2-agents')
    plugins_node = top.get('x-oc2-plugins')
    assets_node = top.get('x-oc2-assets')
    mcp_node = top.get('x-oc2-mcp')
    extension_presence = (
        assets_node is not None,
        agents_node is not None,
        plugins_node is not None,
        mcp_node is not None,
    )
    if phase4_node is not None and not all(extension_presence):
        raise NativeConfigError('Phase 4 requires the complete OC2 APM extension set')
    if not any(extension_presence):
        if runtime_node is not None:
            raise NativeConfigError('Unified Runtime requires the complete OC2 APM extension set')
        if require_oc2_assets or verification_only:
            raise NativeConfigError('OC2 APM extensions are required')
        return NativeConfig(
            source_sha256=hashlib.sha256(raw).hexdigest(),
            asset_sources=(),
            agents=(),
            plugins=PluginSelection(enabled=False, allowlist=()),
            mcp=McpSelection(enabled=False, servers=()),
            default_model=default_model,
            provider_selections=provider_selections,
            allowed_models=allowed_models,
        )
    if not all(extension_presence):
        raise NativeConfigError('OC2 extensions must be declared together')
    if (assets_node is None or agents_node is None or plugins_node is None
            or mcp_node is None):
        raise NativeConfigError('OC2 APM extension state is inconsistent')

    configured_unified_runtime = False
    runtime_options: RuntimeOptions | None = None
    if runtime_node is not None:
        runtime = _mapping(runtime_node, 'x-oc2-runtime')
        configured_unified_runtime = _boolean(runtime['enabled'], 'x-oc2-runtime.enabled')
        runtime_options = _runtime_options(
            runtime_node, _mcp_execution_timeout_ms(top),
        )
    unified_runtime = (
        configured_unified_runtime and not verification_only and not phase4_plugins
    )
    phase4_selection = parse_phase4_selection(
        phase4_node,
        explicit_opt_in=phase4_plugins or unified_runtime,
    )

    assets = tuple(_string(item, 'x-oc2-assets entry') for item in _sequence(
        assets_node, 'x-oc2-assets',
    ))
    if not assets or len(assets) != len(set(assets)):
        raise NativeConfigError('x-oc2-assets must contain unique paths')
    if any(path.startswith('/') or '..' in path.split('/') or '\\' in path for path in assets):
        raise NativeConfigError('unsafe OC2 asset source path')
    if not set(assets) <= ASSET_SOURCES:
        raise NativeConfigError('unapproved asset source path')

    agent_nodes = _mapping(agents_node, 'x-oc2-agents')
    try:
        agent_names = {name: parse_agent_name(name) for name in agent_nodes}
    except ValueError as exc:
        raise NativeConfigError(str(exc)) from exc
    selected_agents = set(agent_names.values())
    if selected_agents and selected_agents != {AgentName.HEPHAESTUS, AgentName.ORACLE}:
        raise NativeConfigError('x-oc2-agents must select the fixed Native Agent set')
    selections: list[AgentSelection] = []
    if selected_agents and default_model is None:
        raise NativeConfigError('Native Agents require opencode_v2 model configuration')
    expected_modes = {AgentName.HEPHAESTUS: AgentMode.PRIMARY, AgentName.ORACLE: AgentMode.SUBAGENT}
    if selected_agents:
        for name, agent_node in agent_nodes.items():
            agent_name = agent_names[name]
            fields = _mapping(agent_node, 'x-oc2-agents.' + name)
            if set(fields) != {'mode', 'model'}:
                raise NativeConfigError('unsupported agent fields: ' + name)
            mode = _string(fields['mode'], 'agent mode')
            model = _string(fields['model'], 'agent model')
            if mode != expected_modes[agent_name].value:
                raise NativeConfigError('unapproved agent mode: ' + name)
            if model not in allowed_models:
                raise NativeConfigError('unapproved agent model: ' + name)
            selections.append(AgentSelection(agent_name, expected_modes[agent_name], model))

    plugins = _mapping(plugins_node, 'x-oc2-plugins')
    if set(plugins) != {'enabled', 'allowlist'}:
        raise NativeConfigError('x-oc2-plugins fields are invalid')
    plugins_enabled = _boolean(plugins['enabled'], 'x-oc2-plugins.enabled')
    plugin_ids = tuple(_plugin_id(_string(item, 'x-oc2-plugins.allowlist entry')) for item in
                       _sequence(plugins['allowlist'], 'x-oc2-plugins.allowlist'))
    if len(plugin_ids) != len(set(plugin_ids)):
        raise NativeConfigError('x-oc2-plugins.allowlist must be unique')

    mcp = _mapping(mcp_node, 'x-oc2-mcp')
    if set(mcp) != {'enabled', 'servers'}:
        raise NativeConfigError('x-oc2-mcp fields are invalid')
    mcp_enabled = _boolean(mcp['enabled'], 'x-oc2-mcp.enabled')
    server_ids = tuple(_mcp_server_id(_string(item, 'x-oc2-mcp.servers entry')) for item in
                       _sequence(mcp['servers'], 'x-oc2-mcp.servers'))
    if len(server_ids) != len(set(server_ids)):
        raise NativeConfigError('x-oc2-mcp.servers must be unique')

    runtime_selection = unified_runtime or verification_only
    if (not verification_only and not phase4_plugins
            and plugins_enabled != configured_unified_runtime):
        raise NativeConfigError('x-oc2-plugins.enabled must match unified Runtime selection')
    if (not verification_only and not phase4_plugins
            and mcp_enabled != configured_unified_runtime):
        raise NativeConfigError('x-oc2-mcp.enabled must match unified Runtime selection')
    selected_plugins = runtime_selection
    selected_mcp = runtime_selection
    if selected_plugins and plugin_ids != (PluginId.SUPERPOWERS,):
        raise NativeConfigError('Runtime requires the Superpowers plugin candidate')
    if selected_mcp and server_ids != (McpServerId.OC2_STATUS,):
        raise NativeConfigError('Runtime requires the oc2-status MCP candidate')
    plugin_selection = PluginSelection(
        enabled=selected_plugins,
        allowlist=plugin_ids if selected_plugins else (),
    )
    mcp_selection = McpSelection(
        enabled=selected_mcp,
        servers=server_ids if selected_mcp else (),
    )
    asset_sources = tuple(source for source in ASSET_SOURCE_TO_TARGET if source in assets)
    if verification_only and plugin_ids != (PluginId.SUPERPOWERS,):
        raise NativeConfigError('verification requires the Superpowers plugin candidate')
    if verification_only and server_ids != (McpServerId.OC2_STATUS,):
        raise NativeConfigError('verification requires the oc2-status MCP candidate')
    return NativeConfig(
        source_sha256=hashlib.sha256(raw).hexdigest(),
        asset_sources=asset_sources,
        agents=tuple(selections),
        plugins=plugin_selection,
        mcp=mcp_selection,
        unified_runtime=unified_runtime,
        allowed_models=allowed_models,
        runtime=runtime_options,
        default_model=default_model,
        provider_selections=provider_selections,
        phase4_plugins=phase4_selection,
    )


def validate_skill_frontmatter(expected_name: str, content: str) -> SkillFrontmatter:
    """Parse and validate the frontmatter of a native Skill document.

    Accepts text beginning with a YAML frontmatter block followed by a
    non-empty Markdown body. Returns the validated ``name`` and trimmed
    ``description``. Frontmatter may contain only ``name`` and ``description``;
    the name must equal ``expected_name`` and match the native-compatible
    lowercase name syntax, and description length is limited to 1024
    characters. Missing delimiters
    or body, invalid/empty YAML, duplicate or unknown fields, missing/invalid
    values, name mismatch, and overlong descriptions raise
    ``NativeConfigError``.
    """
    if not content.startswith('---\n'):
        raise NativeConfigError('Skill frontmatter is missing')
    parts = content.split('\n---\n', 1)
    if len(parts) != 2 or not parts[1].strip():
        raise NativeConfigError('Skill frontmatter or body is incomplete')
    try:
        frontmatter = yaml.compose(parts[0][4:], Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise NativeConfigError('Skill frontmatter is invalid YAML') from exc
    if frontmatter is None:
        raise NativeConfigError('Skill frontmatter is empty')
    fields = _mapping(frontmatter, 'Skill frontmatter')
    if set(fields) - {'name', 'description'}:
        raise NativeConfigError('Skill frontmatter fields are not allowlisted')
    if set(fields) != {'name', 'description'}:
        raise NativeConfigError('Skill description is required')
    name = _string(fields['name'], 'Skill name')
    description = _string(fields['description'], 'Skill description')
    if name != expected_name:
        raise NativeConfigError('Skill name mismatch')
    if re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) is None:
        raise NativeConfigError('Skill name is not native-compatible')
    if len(description) > 1024:
        raise NativeConfigError('Skill description exceeds the native limit')
    return {'name': name, 'description': description}
