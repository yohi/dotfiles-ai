from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypedDict, assert_never

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from oc2_agent_native import AgentMode, AgentName, AgentSelection, NATIVE_MODEL, NativePayload, build_native_payload, parse_agent_name


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
class Permission:
    action: str
    resource: str
    effect: Effect

    def as_json(self) -> PermissionJSON:
        return {'action': self.action, 'resource': self.resource, 'effect': self.effect.value}


@dataclass(frozen=True, slots=True)
class NativeConfig:
    source_sha256: str
    asset_sources: tuple[str, ...]
    agents: tuple[AgentSelection, ...]


class SkillFrontmatter(TypedDict):
    name: str
    description: str


class NativeConfigError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    description: str
    system: str
    permissions: tuple[Permission, ...]


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
        case unreachable:
            assert_never(unreachable)


def _string(node: Node, label: str) -> str:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:str', value=value) if value:
            return value
        case _:
            raise NativeConfigError(f'{label} must be a non-empty string')


def _sequence(node: Node, label: str) -> tuple[Node, ...]:
    match node:
        case SequenceNode(value=items):
            return tuple(items)
        case _:
            raise NativeConfigError(f'{label} must be a sequence')


def _boolean(node: Node, label: str) -> bool:
    match node:
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='true'):
            return True
        case ScalarNode(tag='tag:yaml.org,2002:bool', value='false'):
            return False
        case _:
            raise NativeConfigError(f'{label} must be a boolean')


def parse_apm_native(raw: bytes, *, require_oc2_assets: bool = False) -> NativeConfig:
    try:
        root = yaml.compose(raw, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise NativeConfigError('apm.yml is invalid') from exc
    if root is None:
        raise NativeConfigError('apm.yml is empty')
    top = _mapping(root, 'apm.yml')
    agents_node = top.get('x-oc2-agents')
    assets_node = top.get('x-oc2-assets')
    mcp_node = top.get('x-oc2-mcp')
    extension_presence = (assets_node is not None, agents_node is not None, mcp_node is not None)
    if not any(extension_presence):
        if require_oc2_assets:
            raise NativeConfigError('OC2 APM extensions are required')
        return NativeConfig(hashlib.sha256(raw).hexdigest(), (), ())
    if not all(extension_presence):
        raise NativeConfigError('OC2 extensions must be declared together')
    if assets_node is None or agents_node is None or mcp_node is None:
        raise NativeConfigError('OC2 APM extension state is inconsistent')

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
    expected_modes = {AgentName.HEPHAESTUS: AgentMode.PRIMARY, AgentName.ORACLE: AgentMode.SUBAGENT}
    if selected_agents:
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

    mcp = _mapping(mcp_node, 'x-oc2-mcp')
    if set(mcp) != {'enabled', 'servers'}:
        raise NativeConfigError('x-oc2-mcp fields are invalid')
    if _boolean(mcp['enabled'], 'x-oc2-mcp.enabled'):
        raise NativeConfigError('MCP must remain disabled')
    if _sequence(mcp['servers'], 'x-oc2-mcp.servers'):
        raise NativeConfigError('MCP server allowlist must remain empty')
    asset_sources = tuple(source for source in ASSET_SOURCE_TO_TARGET if source in assets)
    return NativeConfig(hashlib.sha256(raw).hexdigest(), asset_sources, tuple(selections))


def validate_skill_frontmatter(expected_name: str, content: str) -> SkillFrontmatter:
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
