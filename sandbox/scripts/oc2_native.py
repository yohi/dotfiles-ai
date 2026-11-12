from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypedDict

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from oc2_agent_native import (
    AgentMode,
    AgentName,
    AgentSelection,
    McpServerId,
    McpSelection,
    NATIVE_MODEL,
    NativePayload as NativePayload,
    PluginId,
    PluginSelection,
    SUPERPOWERS_COMMIT,
    SUPERPOWERS_REF,
    SUPERPOWERS_REPOSITORY,
    build_native_payload as build_native_payload,
    parse_agent_name,
)


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


@dataclass(frozen=True, slots=True)
class NativeConfig:
    source_sha256: str
    asset_sources: tuple[str, ...]
    agents: tuple[AgentSelection, ...]
    plugins: PluginSelection = PluginSelection(enabled=False, allowlist=())
    mcp: McpSelection = McpSelection(enabled=False, servers=())


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
    """Return the pinned Superpowers commit after validating its APM lock entry."""
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


def _boolean(node: Node, label: str) -> bool:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='true'):
            return True
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='false'):
            return False
        case _:
            raise NativeConfigError(f'{label} must be a boolean')


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


def _parse_asset_sources(node: Node) -> tuple[str, ...]:
    """Parse unique, relative asset paths that are present in the fixed allowlist."""
    assets = tuple(_string(item, 'x-oc2-assets entry') for item in _sequence(
        node, 'x-oc2-assets',
    ))
    if not assets or len(assets) != len(set(assets)):
        raise NativeConfigError('x-oc2-assets must contain unique paths')
    if any(path.startswith('/') or '..' in path.split('/') or '\\' in path for path in assets):
        raise NativeConfigError('unsafe OC2 asset source path')
    if not set(assets) <= ASSET_SOURCES:
        raise NativeConfigError('unapproved asset source path')
    return tuple(source for source in ASSET_SOURCE_TO_TARGET if source in assets)


def _parse_agent_selections(
    top: dict[str, Node], agents_node: Node,
) -> tuple[AgentSelection, ...]:
    """Parse the fixed Agent pair, enforcing its mode and APM model allowlist."""
    agent_nodes = _mapping(agents_node, 'x-oc2-agents')
    try:
        agent_names = {name: parse_agent_name(name) for name in agent_nodes}
    except ValueError as exc:
        raise NativeConfigError(str(exc)) from exc
    selected_agents = set(agent_names.values())
    if selected_agents and selected_agents != {AgentName.HEPHAESTUS, AgentName.ORACLE}:
        raise NativeConfigError('x-oc2-agents must select the fixed Native Agent set')
    if not selected_agents:
        return ()

    root_config = _mapping(top.get('opencode_v2', MappingNode('tag:yaml.org,2002:map', [])), 'opencode_v2')
    providers = _mapping(
        root_config.get('providers', MappingNode('tag:yaml.org,2002:map', [])),
        'opencode_v2.providers',
    )
    openai = _mapping(
        providers.get('openai', MappingNode('tag:yaml.org,2002:map', [])),
        'opencode_v2.providers.openai',
    )
    enabled_node = openai.get('enabled')
    if enabled_node is None or not _boolean(enabled_node, 'openai enabled'):
        raise NativeConfigError('OpenAI must be enabled for Native Agents')
    catalog = _mapping(top.get('provider', MappingNode('tag:yaml.org,2002:map', [])), 'provider')
    openai_catalog = _mapping(
        catalog.get('openai', MappingNode('tag:yaml.org,2002:map', [])),
        'provider.openai',
    )
    model_whitelist = tuple(_string(item, 'provider.openai.whitelist item') for item in _sequence(
        openai_catalog.get('whitelist', SequenceNode('tag:yaml.org,2002:seq', [])),
        'provider.openai.whitelist',
    ))
    if NATIVE_MODEL.partition('/')[2] not in model_whitelist:
        raise NativeConfigError('Native Agent model is not in the APM provider whitelist')

    expected_modes = {AgentName.HEPHAESTUS: AgentMode.PRIMARY, AgentName.ORACLE: AgentMode.SUBAGENT}
    selections: list[AgentSelection] = []
    for name, agent_node in agent_nodes.items():
        agent_name = agent_names[name]
        fields = _mapping(agent_node, 'x-oc2-agents.' + name)
        if set(fields) != {'mode', 'model'}:
            raise NativeConfigError('unsupported agent fields: ' + name)
        mode = _string(fields['mode'], 'agent mode')
        model = _string(fields['model'], 'agent model')
        if mode != expected_modes[agent_name].value:
            raise NativeConfigError('unapproved agent mode: ' + name)
        if model != NATIVE_MODEL:
            raise NativeConfigError('unapproved agent model: ' + name)
        selections.append(AgentSelection(agent_name, expected_modes[agent_name], model))
    return tuple(selections)


def _parse_plugin_ids(node: Node) -> tuple[PluginId, ...]:
    """Parse disabled Plugin configuration and its unique fixed candidate list."""
    plugins = _mapping(node, 'x-oc2-plugins')
    if set(plugins) != {'enabled', 'allowlist'}:
        raise NativeConfigError('x-oc2-plugins fields are invalid')
    if _boolean(plugins['enabled'], 'x-oc2-plugins.enabled'):
        raise NativeConfigError('x-oc2-plugins must remain disabled in APM')
    plugin_ids = tuple(_plugin_id(_string(item, 'x-oc2-plugins.allowlist entry')) for item in
                       _sequence(plugins['allowlist'], 'x-oc2-plugins.allowlist'))
    if len(plugin_ids) != len(set(plugin_ids)):
        raise NativeConfigError('x-oc2-plugins.allowlist must be unique')
    return plugin_ids


def _parse_mcp_server_ids(node: Node) -> tuple[McpServerId, ...]:
    """Parse disabled MCP configuration and its unique fixed server list."""
    mcp = _mapping(node, 'x-oc2-mcp')
    if set(mcp) != {'enabled', 'servers'}:
        raise NativeConfigError('x-oc2-mcp fields are invalid')
    if _boolean(mcp['enabled'], 'x-oc2-mcp.enabled'):
        raise NativeConfigError('x-oc2-mcp must remain disabled in APM')
    server_ids = tuple(_mcp_server_id(_string(item, 'x-oc2-mcp.servers entry')) for item in
                       _sequence(mcp['servers'], 'x-oc2-mcp.servers'))
    if len(server_ids) != len(set(server_ids)):
        raise NativeConfigError('x-oc2-mcp.servers must be unique')
    return server_ids


def parse_apm_native(
    raw: bytes,
    *,
    require_oc2_assets: bool = False,
    verification_only: bool = False,
) -> NativeConfig:
    """Parse a YAML APM mapping into a digest-bound Native config.

    Asset paths must be unique safe members of ``ASSET_SOURCES``; Agents are
    either absent or the fixed pair with approved modes/models; APM Plugin and
    MCP activation is rejected. OC2 extensions must be complete. An
    extension-free mapping is accepted only when neither verification-only nor
    required-assets mode is enabled. Returns ordered selections and the source
    digest; malformed YAML or disallowed values raise ``NativeConfigError``.
    """
    try:
        root = yaml.compose(raw, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise NativeConfigError('apm.yml is invalid') from exc
    if root is None:
        raise NativeConfigError('apm.yml is empty')
    top = _mapping(root, 'apm.yml')
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
    if not any(extension_presence):
        if require_oc2_assets or verification_only:
            raise NativeConfigError('OC2 APM extensions are required')
        return NativeConfig(
            hashlib.sha256(raw).hexdigest(),
            (),
            (),
            PluginSelection(enabled=False, allowlist=()),
            McpSelection(enabled=False, servers=()),
        )
    if not all(extension_presence):
        raise NativeConfigError('OC2 extensions must be declared together')
    if (assets_node is None or agents_node is None or plugins_node is None
            or mcp_node is None):
        raise NativeConfigError('OC2 APM extension state is inconsistent')

    asset_sources = _parse_asset_sources(assets_node)
    selections = _parse_agent_selections(top, agents_node)
    plugin_ids = _parse_plugin_ids(plugins_node)
    server_ids = _parse_mcp_server_ids(mcp_node)

    plugin_selection = PluginSelection(
        enabled=verification_only,
        allowlist=plugin_ids if verification_only else (),
    )
    mcp_selection = McpSelection(
        enabled=verification_only,
        servers=server_ids if verification_only else (),
    )
    if verification_only and plugin_ids != (PluginId.SUPERPOWERS,):
        raise NativeConfigError('verification requires the Superpowers plugin candidate')
    if verification_only and server_ids != (McpServerId.OC2_STATUS,):
        raise NativeConfigError('verification requires the oc2-status MCP candidate')
    return NativeConfig(
        hashlib.sha256(raw).hexdigest(),
        asset_sources,
        tuple(selections),
        plugin_selection,
        mcp_selection,
    )


def validate_skill_frontmatter(expected_name: str, content: str) -> SkillFrontmatter:
    """Parse a Skill document and return its required name/description fields.

    Accept only a non-empty body following YAML frontmatter with exactly
    ``name`` and ``description``. Reject malformed/missing fields, name
    mismatch or non-native name, and descriptions longer than 1024 characters.
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
