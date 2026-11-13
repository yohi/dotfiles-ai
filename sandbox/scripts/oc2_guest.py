#!/usr/bin/env python3
"""Validate an oc2 configuration bundle and activate an isolated OpenCode v2 runtime.

Executed by the agent inside a mountless Docker Sandbox. No network operations.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Final, NoReturn, TypeAlias

from oc2_agent_native import (
    SUPERPOWERS_COMMIT,
    SUPERPOWERS_FILE_COUNT,
    SUPERPOWERS_REPOSITORY,
    SUPERPOWERS_TREE_PATH,
    SUPERPOWERS_TOTAL_BYTES,
    SUPERPOWERS_TREE_SHA256,
    SUPERPOWERS_VERSION,
    validate_agent_map,
    validate_native_asset,
)

VERSION = "2.2.5"
BASE = pathlib.Path('/home/agent/workspace/oc2')
FILES = ('opencode.jsonc', 'cli.json', 'export-manifest.json')
ASSET_SCHEMA = 'dotfiles-ai/oc2-assets/v1'
JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
CF_CUSTOM_BASE_URL: Final[str] = (
    'https://gateway.ai.cloudflare.com/v1/'
    '{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat'
)
CF_CUSTOM_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ('Authorization', ''),
    ('cf-aig-authorization', 'Bearer {env:OC_CF_API_TOKEN}'),
    ('cf-aig-collect-log-payload', 'true'),
    ('cf-aig-max-attempts', '1'),
    ('cf-aig-skip-cache', 'true'),
)
ASSET_TARGETS = frozenset({
    'config/opencode/AGENTS.md',
    'config/opencode/rules/DOCS_STYLE.md',
    'config/opencode/rules/GIT_STANDARDS.md',
    'config/opencode/rules/MARKDOWN.md',
    'config/opencode/rules/META_PROMPT.md',
    'config/opencode/rules/SHELL.md',
    'config/opencode/rules/STACKED_PR_WORKFLOW.md',
    'config/opencode/commands/build-skill.md',
    'config/opencode/skills/agent-skill-architect/SKILL.md',
    'config/opencode/skills/config-modernizer/SKILL.md',
    'theme.json',
    'native/oc2-native.json',
})
NATIVE_ASSET_TARGET = 'native/oc2-native.json'
PLUGIN_PREFIX = 'plugins/superpowers/'
PLUGIN_META_TARGET = 'metadata/superpowers-plugin.json'
MCP_SERVER_TARGET = 'mcp/oc2_local_mcp.py'
MAX_ASSETS = 512 * 1024
MAX_PHASE4_PLUGIN_FILE = 4 * 1024 * 1024
IMPORT_SPECIFIER = re.compile(
    r'''(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)['"]([^'"]+)['"]''',
)

CLI_CANDIDATES = (
    '/home/agent/.local/oc2-runtime/node_modules/.bin/opencode',
)


def fail(reason: str) -> NoReturn:
    raise ValueError(reason)


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            fail('duplicate JSON object key')
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class SuperpowersFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedSuperpowersSource:
    files: tuple[SuperpowersFile, ...]
    tree_sha256: str
    total_bytes: int


@dataclass(frozen=True, slots=True)
class Phase4PluginReceipt:
    plugin_id: str
    package: str
    version: str
    repository: str
    commit: str
    acquisition: str
    artifact_sha512: str
    entrypoint: str
    build_tool: str | None
    lock_sha256: str | None


@dataclass(frozen=True, slots=True)
class VerifiedPhase4PluginBundle:
    files: tuple[tuple[str, bytes], ...]
    plugins: tuple[Phase4PluginReceipt, ...]
    selection: tuple[str, ...]
    source_sha256: str
    bundle_sha256: str


def verify_superpowers_source() -> VerifiedSuperpowersSource:
    source = BASE / SUPERPOWERS_TREE_PATH
    validate_location(source, BASE)
    if source.is_symlink() or not source.is_dir():
        fail('verified Superpowers source directory is missing or linked')

    files: list[SuperpowersFile] = []
    total_bytes = 0
    paths = sorted(source.rglob('*'), key=lambda item: item.relative_to(source).as_posix())
    for path in paths:
        if path.is_symlink():
            fail('symlink in verified Superpowers source')
        if path.is_dir():
            continue
        if not path.is_file():
            fail('non-regular entry in verified Superpowers source')
        relative = path.relative_to(source).as_posix()
        if (relative.startswith('/') or '\\' in relative
                or any(part in ('', '.', '..') for part in relative.split('/'))):
            fail('unsafe path in verified Superpowers source')
        size = path.stat().st_size
        if size > SUPERPOWERS_TOTAL_BYTES or total_bytes + size > SUPERPOWERS_TOTAL_BYTES:
            fail('verified Superpowers source exceeds its pinned size')
        content = path.read_bytes()
        total_bytes += len(content)
        files.append(SuperpowersFile(relative, content, hashlib.sha256(content).hexdigest()))

    by_path = {item.path: item for item in files}
    required = {
        'index.js',
        'package.json',
        '.opencode/plugins/superpowers.js',
        'skills/using-superpowers/SKILL.md',
        'skills/brainstorming/SKILL.md',
        'skills/verification-before-completion/SKILL.md',
    }
    if len(files) != SUPERPOWERS_FILE_COUNT or total_bytes != SUPERPOWERS_TOTAL_BYTES:
        fail('verified Superpowers source size or file count mismatch')
    if not required <= set(by_path):
        fail('verified Superpowers entrypoint or required Skills are missing')
    try:
        package = json.loads(
            by_path['package.json'].content, object_pairs_hook=_unique_json_object,
        )
    except (ValueError, UnicodeError) as exc:
        raise ValueError('verified Superpowers package metadata is invalid') from exc
    if (not isinstance(package, dict)
            or package.get('name') != SUPERPOWERS_REPOSITORY.split('/')[-1]
            or package.get('version') != SUPERPOWERS_VERSION
            or package.get('main') != '.opencode/plugins/superpowers.js'):
        fail('verified Superpowers package identity mismatch')

    tree_material = ''.join(
        f'{item.path}\0{item.sha256}\n' for item in files
    ).encode('utf-8')
    tree_sha256 = hashlib.sha256(tree_material).hexdigest()
    if tree_sha256 != SUPERPOWERS_TREE_SHA256:
        fail('verified Superpowers source tree SHA-256 mismatch')
    return VerifiedSuperpowersSource(tuple(files), tree_sha256, total_bytes)


def regular(path: pathlib.Path, max_bytes: int = 1048576) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        fail('non-regular or oversized file: ' + path.name)
    return path.read_bytes()


def _verify_model_settings(value: JsonValue, label: str) -> None:
    if not isinstance(value, dict):
        fail('invalid model reasoning settings: ' + label)
    allowed = {
        'reasoningEffort': {'minimal', 'low', 'medium', 'high', 'xhigh', 'max'},
        'reasoningSummary': {'auto', 'concise', 'detailed'},
    }
    for key, item in value.items():
        if key not in allowed or not isinstance(item, str) or item not in allowed[key]:
            fail('unapproved model reasoning setting: ' + label)


def _verify_model_options(key: str, options: dict[str, JsonValue], label: str) -> None:
    if key == 'headers':
        if options:
            fail('unsupported model headers: ' + label)
        return
    if set(options) - {'thinking'}:
        fail('unsupported model body field: ' + label)
    thinking = options.get('thinking')
    if thinking is None and 'thinking' not in options:
        return
    if (not isinstance(thinking, dict) or set(thinking) != {'type'}
            or not isinstance(thinking['type'], str)
            or thinking['type'] not in {'enabled', 'disabled'}):
        fail('unsupported model thinking option: ' + label)


def _verify_model_catalog(models: JsonValue) -> None:
    if not isinstance(models, dict):
        fail('invalid V2 model catalog')
    for model_id, value in models.items():
        if not isinstance(value, dict) or set(value) - {
            'modelID', 'name', 'settings', 'headers', 'body', 'variants',
        }:
            fail('invalid V2 model configuration')
        if value.get('modelID') != model_id or not isinstance(value.get('name'), str):
            fail('V2 model identity does not match its catalog')
        _verify_model_settings(value.get('settings', {}), model_id)
        for key in ('headers', 'body'):
            options = value.get(key, {})
            if not isinstance(options, dict):
                fail('invalid V2 model ' + key)
            _verify_model_options(key, options, model_id + '.' + key)
        variants = value.get('variants', [])
        if not isinstance(variants, list):
            fail('invalid V2 model variants')
        seen: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                fail('invalid V2 model variant')
            variant_id = variant.get('id')
            if not isinstance(variant_id, str):
                fail('invalid V2 model variant')
            if variant_id in seen or set(variant) - {'id', 'settings', 'headers', 'body'}:
                fail('invalid V2 model variant')
            seen.add(variant_id)
            _verify_model_settings(variant.get('settings', {}), model_id + '.' + variant_id)
            for key in ('headers', 'body'):
                options = variant.get(key, {})
                if not isinstance(options, dict):
                    fail('invalid V2 model variant ' + key)
                _verify_model_options(key, options, model_id + '.' + variant_id)


def verify_v2_config(server: dict[str, JsonValue]) -> None:
    """Reject provider fallback, Guest auth, and literal credentials at activation."""
    allowed_fields = {'$schema', 'shell', 'snapshot', 'model', 'providers', 'policies'}
    if 'agents' in server:
        allowed_fields.add('agents')
        providers_for_agents = server.get('providers')
        if not isinstance(providers_for_agents, dict):
            fail('Native Agent provider models are missing')
        allowed_agent_models: list[str] = []
        for provider_id, provider in providers_for_agents.items():
            if not isinstance(provider, dict):
                continue
            models = provider.get('models')
            if not isinstance(models, dict):
                continue
            allowed_agent_models.extend(
                f'{provider_id}/{model_id}'
                for model_id in models
                if isinstance(model_id, str)
            )
        validate_agent_map(server['agents'], allowed_agent_models)
    if set(server) != allowed_fields:
        fail('unexpected V2 server config fields')
    model = server.get('model')
    providers = server.get('providers')
    policies = server.get('policies')
    allowed_providers = {'openai', 'cloudflare-ai-gateway-custom'}
    if (not isinstance(model, str) or '/' not in model
            or not isinstance(providers, dict) or not providers
            or not set(providers) <= allowed_providers
            or not isinstance(policies, list)):
        fail('invalid V2 provider selection')
    provider_id, model_id = model.split('/', 1)
    if not model_id or provider_id not in providers:
        fail('V2 model does not match the selected provider')
    provider = providers[provider_id]
    if not isinstance(provider, dict):
        fail('invalid V2 provider configuration')
    models = provider.get('models')
    if not isinstance(models, dict) or model_id not in models:
        fail('V2 default model is not in the provider catalog')
    for provider_config in providers.values():
        if not isinstance(provider_config, dict):
            fail('invalid V2 provider configuration')
        _verify_model_catalog(provider_config.get('models'))
    provider_policies: list[JsonValue] = [
        {'action': 'provider.use', 'resource': provider_id, 'effect': 'allow'}
        for provider_id in ('openai', 'cloudflare-ai-gateway-custom')
        if provider_id in providers
    ]
    expected_policies: list[JsonValue] = [
        {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
        *provider_policies,
        {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
        {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
        {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
    ]
    if policies != expected_policies:
        fail('V2 fallback or Guest authentication policy is not fail-closed')
    for provider_name, provider_config in providers.items():
        if not isinstance(provider_name, str) or not isinstance(provider_config, dict):
            fail('invalid V2 provider configuration')
        settings = provider_config.get('settings', {})
        headers = provider_config.get('headers', {})
        if not isinstance(settings, dict) or not isinstance(headers, dict):
            fail('invalid V2 provider request settings')
        _verify_v2_provider_options(provider_name, settings, headers)


def _verify_v2_provider_options(
    provider_id: str,
    settings: dict[str, JsonValue],
    headers: dict[str, JsonValue],
) -> None:
    if provider_id == 'openai':
        if settings or headers:
            fail('OpenAI V2 configuration must not contain Guest credentials')
        return
    if provider_id != 'cloudflare-ai-gateway-custom':
        fail('unsupported V2 provider options')
    if settings != {'baseURL': CF_CUSTOM_BASE_URL}:
        fail('Cloudflare Custom baseURL is not the approved /compat endpoint')

    allowed_headers = {name.casefold(): (name, value) for name, value in CF_CUSTOM_HEADERS}
    seen: set[str] = set()
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            fail('Cloudflare Custom header names and values must be strings')
        folded_name = name.casefold()
        if folded_name in seen:
            fail('duplicate Cloudflare Custom header')
        seen.add(folded_name)
        allowed = allowed_headers.get(folded_name)
        if allowed is None or name != allowed[0] or value != allowed[1]:
            fail('Cloudflare Custom header is not approved')
    if headers.get('cf-aig-authorization') != 'Bearer {env:OC_CF_API_TOKEN}':
        fail('Cloudflare Custom proxy authorization header is required')


def verify(bundle: pathlib.Path) -> str:
    if bundle.is_symlink() or not bundle.is_dir() or set(x.name for x in bundle.iterdir()) != set(FILES):
        fail('invalid bundle directory or members')
    data = {name: regular(bundle / name) for name in FILES}
    manifest = json.loads(
        data['export-manifest.json'], object_pairs_hook=_unique_json_object,
    )
    server = json.loads(data['opencode.jsonc'], object_pairs_hook=_unique_json_object)
    client = json.loads(data['cli.json'], object_pairs_hook=_unique_json_object)
    if (manifest.get('schema') != 'dotfiles-ai/sandbox-export/v0'
            or manifest.get('generator') != 'v0.2'
            or manifest.get('opencode_version') != VERSION
            or manifest.get('plugins_exported') != 0
            or manifest.get('mcp_entries_exported') != 0):
        fail('unrecognized exporter manifest')
    if set(manifest) != {
        'schema', 'generator', 'source', 'config_format', 'source_sha256',
        'opencode_version', 'plugins_exported', 'mcp_entries_exported',
        'artifacts_sha256',
    } or manifest.get('source') != 'apm.yml':
        fail('unexpected exporter manifest fields')
    if re.fullmatch(r'[0-9a-f]{64}', manifest.get('source_sha256', '')) is None:
        fail('invalid source SHA-256')
    hashes = {k: hashlib.sha256(data[k]).hexdigest() for k in FILES[:2]}
    if manifest.get('artifacts_sha256') != hashes:
        fail('bundle SHA-256 mismatch')
    if (not isinstance(server, dict)
            or server.get('$schema') != 'https://opencode.ai/config.json'
            or server.get('shell') not in ('bash', 'sh', 'zsh')
            or type(server.get('snapshot')) is not bool):
        fail('unsafe server config')
    match manifest['config_format']:
        case 'legacy-minimal':
            if (set(server) != {'$schema', 'shell', 'snapshot', 'plugins', 'mcp'}
                    or server.get('plugins') != [] or server.get('mcp') != {}):
                fail('unsafe legacy server config')
        case 'oc2-verification':
            if (set(server) != {'$schema', 'shell', 'snapshot', 'plugins', 'mcp'}
                    or server.get('plugins') != [] or server.get('mcp') != {}):
                fail('unsafe verification server config')
        case 'opencode-v2':
            verify_v2_config(server)
        case 'opencode-v2-unified':
            verify_v2_config(server)
        case _:
            fail('unrecognized config format')
    if client != {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}:
        fail('unsafe TUI config')
    return hashlib.sha256(data['export-manifest.json']).hexdigest()


def runtime_path(
    manifest_sha: str,
    assets_sha: str | None = None,
    generator_fingerprint: str | None = None,
) -> pathlib.Path:
    if generator_fingerprint is not None and assets_sha is None:
        fail('verification Runtime identity requires an asset hash')
    if assets_sha is not None:
        if generator_fingerprint is None:
            combined = hashlib.sha256(
                bytes.fromhex(manifest_sha) + bytes.fromhex(assets_sha),
            ).hexdigest()
        else:
            from oc2_identity import runtime_identity_sha256

            combined = runtime_identity_sha256(
                manifest_sha, assets_sha, generator_fingerprint,
            )
        return BASE / 'runtime' / combined[:16]
    return BASE / 'runtime' / manifest_sha[:16]


def _verify_plugin_source_metadata(raw: bytes) -> dict[str, JsonValue]:
    try:
        metadata: dict[str, JsonValue] = json.loads(
            raw, object_pairs_hook=_unique_json_object,
        )
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid Superpowers source metadata') from exc
    expected: dict[str, JsonValue] = {
        'schema': 'dotfiles-ai/oc2-plugin-source/v1',
        'source': SUPERPOWERS_REPOSITORY,
        'version': SUPERPOWERS_VERSION,
        'commit': SUPERPOWERS_COMMIT,
        'source_path': SUPERPOWERS_TREE_PATH,
        'entrypoint': '.opencode/plugins/superpowers.js',
        'skills_directory': 'skills',
        'file_count': SUPERPOWERS_FILE_COUNT,
        'total_bytes': SUPERPOWERS_TOTAL_BYTES,
        'tree_sha256': SUPERPOWERS_TREE_SHA256,
    }
    if (set(metadata) != set(expected) | {'plugin_files', 'tree_files'}
            or any(metadata.get(key) != value for key, value in expected.items())):
        fail('Superpowers source metadata is not allowlisted')
    tree_files = metadata.get('tree_files')
    if not isinstance(tree_files, list) or len(tree_files) != SUPERPOWERS_FILE_COUNT:
        fail('Superpowers source tree manifest is invalid')
    tree_rows: list[tuple[str, str]] = []
    for row in tree_files:
        if (not isinstance(row, dict) or set(row) != {'path', 'sha256'}
                or not isinstance(row['path'], str)
                or not isinstance(row['sha256'], str)
                or re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is None):
            fail('Superpowers source tree manifest is invalid')
        path = row['path']
        if (path.startswith('/') or '\\' in path
                or any(part in ('', '.', '..') for part in path.split('/'))):
            fail('Superpowers source tree path is unsafe')
        tree_rows.append((path, row['sha256']))
    if tree_rows != sorted(tree_rows) or len({path for path, _ in tree_rows}) != len(tree_rows):
        fail('Superpowers source tree order or paths are invalid')
    tree_material = ''.join(
        f'{path}\0{digest}\n' for path, digest in tree_rows
    ).encode('utf-8')
    if hashlib.sha256(tree_material).hexdigest() != SUPERPOWERS_TREE_SHA256:
        fail('Superpowers source tree SHA-256 mismatch')
    raw_plugin_files = metadata.get('plugin_files')
    if not isinstance(raw_plugin_files, list):
        fail('Superpowers Plugin file manifest is invalid')
    plugin_files: list[str] = []
    for name in raw_plugin_files:
        if not isinstance(name, str):
            fail('Superpowers Plugin file manifest is invalid')
        plugin_files.append(name)
    if plugin_files != sorted(set(plugin_files)):
        fail('Superpowers Plugin file manifest is invalid')
    if any(not isinstance(name, str) for name in plugin_files):
        fail('Superpowers Plugin file manifest is invalid')
    file_names = [name for name in plugin_files if isinstance(name, str)]
    if file_names != sorted(set(file_names)):
        fail('Superpowers Plugin file manifest is invalid')
    names = set(file_names)
    if not {
        'index.js',
        'package.json',
        '.opencode/plugins/superpowers.js',
    } <= names:
        fail('Superpowers Plugin entrypoint files are missing')
    if not any(
        name.startswith('skills/') and name.endswith('/SKILL.md')
        and len(name.split('/')) == 3
        for name in file_names
    ):
        fail('Superpowers Native Skill assets are missing')
    if any(
        name.startswith('/') or '\\' in name
        or any(part in ('', '.', '..') for part in name.split('/'))
        for name in file_names
    ):
        fail('Superpowers Plugin file path is unsafe')
    return metadata


def verify_assets(source: pathlib.Path, expected_sha: str) -> dict[str, bytes]:
    validate_location(source, BASE)
    if re.fullmatch(r'[0-9a-f]{64}', expected_sha) is None:
        fail('invalid asset SHA')
    raw = regular(source, MAX_ASSETS)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        fail('host/guest asset SHA mismatch')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid asset JSON') from exc
    if not isinstance(payload, dict) or set(payload) != {'schema', 'files', 'sha256'}:
        fail('invalid asset manifest')
    if payload.get('schema') != ASSET_SCHEMA:
        fail('unexpected asset schema')
    files = payload['files']
    hashes = payload['sha256']
    if (not isinstance(files, dict) or not isinstance(hashes, dict)
            or any(not isinstance(name, str) for name in files)
            or any(not isinstance(name, str) for name in hashes)
            or set(hashes) != set(files)
            or 'theme.json' not in files or NATIVE_ASSET_TARGET not in files):
        fail('asset path allowlist mismatch')
    native_value = files[NATIVE_ASSET_TARGET]
    if not isinstance(native_value, str):
        fail('invalid native asset type')
    native = validate_native_asset(native_value.encode('utf-8'))
    plugin_targets = {name for name in files if name.startswith(PLUGIN_PREFIX)}
    if any('\\' in name or '..' in name.split('/') for name in plugin_targets):
        fail('unsafe Plugin asset path')
    plugin_enabled = native['plugins']['enabled']
    allowed_targets = set(ASSET_TARGETS)
    if plugin_enabled:
        allowed_targets.update({PLUGIN_META_TARGET, MCP_SERVER_TARGET, *plugin_targets})
        if (not plugin_targets or PLUGIN_META_TARGET not in files
                or MCP_SERVER_TARGET not in files):
            fail('verification Plugin/MCP source metadata is incomplete')
    if set(files) - allowed_targets:
        fail('asset path allowlist mismatch')
    if not plugin_enabled and (plugin_targets or PLUGIN_META_TARGET in files
                               or MCP_SERVER_TARGET in files):
        fail('disabled Plugin/MCP assets are present')
    result: dict[str, bytes] = {}
    for name in sorted(files):
        value = files[name]
        if not isinstance(value, str):
            fail('non-text asset')
        encoded = value.encode('utf-8')
        if len(encoded) > 65536 or hashlib.sha256(encoded).hexdigest() != hashes[name]:
            fail('asset content SHA mismatch')
        result[name] = encoded
    try:
        theme = json.loads(result['theme.json'])
    except ValueError as exc:
        raise ValueError('invalid theme') from exc
    if (not isinstance(theme, dict) or set(theme) != {'name'}
            or not isinstance(theme['name'], str)
            or not re.fullmatch(r'[a-z0-9-]{1,40}', theme['name'])):
        fail('unsafe TUI theme')
    if plugin_enabled:
        metadata = _verify_plugin_source_metadata(result[PLUGIN_META_TARGET])
        plugin_files = metadata['plugin_files']
        if not isinstance(plugin_files, list):
            fail('Superpowers Plugin file manifest is invalid')
        expected_targets = {PLUGIN_PREFIX + name for name in plugin_files if isinstance(name, str)}
        if plugin_targets != expected_targets:
            fail('Superpowers Plugin assets do not match their manifest')
        tree_manifest = metadata['tree_files']
        if not isinstance(tree_manifest, list):
            fail('Superpowers source tree manifest is invalid')
        tree_hashes = {
            row['path']: row['sha256']
            for row in tree_manifest
            if isinstance(row, dict)
            and isinstance(row.get('path'), str)
            and isinstance(row.get('sha256'), str)
        }
        for target in sorted(plugin_targets):
            relative = target.removeprefix(PLUGIN_PREFIX)
            if tree_hashes.get(relative) != hashlib.sha256(result[target]).hexdigest():
                fail('Superpowers Plugin file does not match its pinned source tree')
    return result


def verify_phase4_plugin_assets(
    source: pathlib.Path,
    expected_sha: str,
    expected_source_sha: str,
) -> VerifiedPhase4PluginBundle:
    """Validate Phase 4 plugin identities and entrypoint bytes before import."""
    from oc2_phase4_policy import PHASE4_PLUGIN_POLICIES, PHASE4_POLICY_BY_ID

    validate_location(source, BASE)
    if re.fullmatch(r'[0-9a-f]{64}', expected_sha) is None:
        fail('invalid Phase 4 plugin asset SHA-256')
    if re.fullmatch(r'[0-9a-f]{64}', expected_source_sha) is None:
        fail('invalid Phase 4 source SHA-256')
    raw = regular(source, MAX_ASSETS)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        fail('Phase 4 plugin asset SHA-256 mismatch')
    try:
        payload: JsonValue = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid Phase 4 plugin asset JSON') from exc
    if not isinstance(payload, dict) or set(payload) != {
        'schema', 'source_sha256', 'selection', 'plugins', 'files', 'sha256',
    }:
        fail('invalid Phase 4 plugin asset manifest')
    if (payload['schema'] != 'dotfiles-ai/oc2-phase4-plugin-assets/v1'
            or payload['source_sha256'] != expected_source_sha):
        fail('Phase 4 plugin asset source identity mismatch')
    expected_selection = [policy.plugin_id for policy in PHASE4_PLUGIN_POLICIES]
    if payload['selection'] != expected_selection:
        fail('Phase 4 plugin selection is not allowlisted')
    files = payload['files']
    hashes = payload['sha256']
    rows = payload['plugins']
    if (not isinstance(files, dict) or not isinstance(hashes, dict)
            or not isinstance(rows, list) or len(rows) != len(PHASE4_PLUGIN_POLICIES)
            or any(not isinstance(name, str) for name in files)
            or any(not isinstance(name, str) for name in hashes)):
        fail('invalid Phase 4 plugin asset contents')

    verified_files: dict[str, bytes] = {}
    receipts: list[Phase4PluginReceipt] = []
    expected_targets: set[str] = set()
    for index, policy in enumerate(PHASE4_PLUGIN_POLICIES):
        row = rows[index]
        if not isinstance(row, dict):
            fail('invalid Phase 4 plugin identity row')
        fields = {
            'id', 'package', 'version', 'repository', 'commit', 'acquisition',
            'artifact_sha512', 'entrypoint', 'files',
        }
        if policy.build_tool is not None:
            fields.update({'build_tool', 'lock_sha256'})
        if set(row) != fields:
            fail('invalid Phase 4 plugin identity fields')
        if any(row.get(key) != value for key, value in {
            'id': policy.plugin_id,
            'package': policy.package,
            'version': policy.version,
            'repository': policy.repository,
            'commit': policy.source_commit,
            'acquisition': policy.acquisition,
            'entrypoint': policy.entrypoint,
        }.items()):
            fail('Phase 4 plugin source identity mismatch')
        artifact_sha = row['artifact_sha512']
        if not isinstance(artifact_sha, str) or re.fullmatch(r'[0-9a-f]{128}', artifact_sha) is None:
            fail('invalid Phase 4 artifact SHA-512')
        if policy.build_tool is not None and (
            row.get('build_tool') != policy.build_tool or row.get('lock_sha256') != policy.lock_sha256
        ):
            fail('Phase 4 plugin build provenance mismatch')
        listed_files = row['files']
        required_relative = {'package.json', policy.entrypoint}
        if (not isinstance(listed_files, list)
                or any(not isinstance(name, str) for name in listed_files)
                or set(listed_files) != required_relative or len(listed_files) != len(required_relative)):
            fail('Phase 4 plugin file manifest is invalid')
        for relative in required_relative:
            target = f'plugins/{policy.plugin_id}/{relative}'
            expected_targets.add(target)
        receipts.append(Phase4PluginReceipt(
            policy.plugin_id,
            policy.package,
            policy.version,
            policy.repository,
            policy.source_commit,
            policy.acquisition,
            artifact_sha,
            policy.entrypoint,
            policy.build_tool,
            policy.lock_sha256,
        ))

    if set(files) != expected_targets or set(hashes) != expected_targets:
        fail('Phase 4 plugin asset path allowlist mismatch')
    for target in sorted(expected_targets):
        encoded = files[target]
        if not isinstance(encoded, str):
            fail('Phase 4 plugin asset is not base64 text')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Phase 4 plugin asset base64 is invalid') from exc
        if (len(content) > MAX_PHASE4_PLUGIN_FILE or not isinstance(hashes[target], str)
                or hashlib.sha256(content).hexdigest() != hashes[target]):
            fail('Phase 4 plugin asset content SHA-256 mismatch')
        verified_files[target] = content

    for plugin in receipts:
        policy = PHASE4_POLICY_BY_ID[plugin.plugin_id]
        package_path = f'plugins/{plugin.plugin_id}/package.json'
        entry_path = f'plugins/{plugin.plugin_id}/{plugin.entrypoint}'
        try:
            package = json.loads(verified_files[package_path], object_pairs_hook=_unique_json_object)
            entrypoint = verified_files[entry_path].decode('utf-8')
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Phase 4 package metadata or entrypoint is invalid') from exc
        if (not isinstance(package, dict) or package.get('name') != policy.package
                or package.get('version') != policy.version or package.get('type') != 'module'):
            fail('Phase 4 runtime package identity mismatch')
        if {'dependencies', 'optionalDependencies', 'peerDependencies'} & set(package):
            fail('Phase 4 runtime package contains external dependencies')
        if policy.plugin_id == 'akane':
            exports = package.get('exports')
            if (package.get('main') != './dist/index.js' or not isinstance(exports, dict)
                    or exports.get('./server') != './dist/index.js'):
                fail('Akane server package export mismatch')
        else:
            exports = package.get('exports')
            tui = exports.get('./tui') if isinstance(exports, dict) else None
            root = exports.get('.') if isinstance(exports, dict) else None
            if (package.get('main') != './dist/tui.js' or not isinstance(tui, dict)
                    or tui.get('import') != './dist/tui.js' or not isinstance(root, dict)
                    or root.get('import') != './dist/tui.js'):
                fail('Sibyl TUI package export mismatch')
        imports = set(IMPORT_SPECIFIER.findall(entrypoint))
        if any(name.startswith(('./', '../')) or name not in policy.external_imports for name in imports):
            fail('Phase 4 runtime dependency is not allowlisted')

    return VerifiedPhase4PluginBundle(
        tuple(sorted(verified_files.items())),
        tuple(receipts),
        tuple(expected_selection),
        expected_source_sha,
        expected_sha,
    )


def _asset_count_summary(files: dict[str, bytes]) -> str:
    """Summarize selected asset categories using the verified file keys."""
    rules = sum(name.startswith('config/opencode/rules/') for name in files)
    commands = sum(name.startswith('config/opencode/commands/') for name in files)
    skills = sum(
        name.startswith('config/opencode/skills/') and name.endswith('/SKILL.md')
        for name in files
    )
    theme = int('theme.json' in files)
    custom_agents = sum(name.startswith('config/opencode/agents/') for name in files)
    routing_count = sum(name.startswith('metadata/agent-routes') for name in files)
    routing = str(routing_count) if routing_count else 'none'
    return (
        f'rules={rules} commands={commands} skills={skills} theme={theme} '
        f'custom_agents={custom_agents} routing={routing}'
    )


def install_assets(source: pathlib.Path, expected_sha: str, runtime_id: str) -> pathlib.Path:
    """Verify an asset file and install its selected contents into a new runtime."""
    if re.fullmatch(r'[0-9a-f]{64}', runtime_id) is None:
        fail('invalid asset runtime identity')
    files = verify_assets(source, expected_sha)
    return _install_verified_assets(files, expected_sha, runtime_id)


def _install_verified_assets(
    files: dict[str, bytes], expected_sha: str, runtime_id: str,
) -> pathlib.Path:
    """Materialize already-verified files under a unique asset runtime identity."""
    runtime_root = BASE / 'runtime'
    if not runtime_root.exists():
        runtime_root.mkdir(mode=0o700)
    validate_location(runtime_root, BASE)
    dest = runtime_root / runtime_id[:16]
    validate_location(dest, BASE)
    if dest.exists():
        fail('runtime already exists; refusing overwrite')
    theme = json.loads(files.pop('theme.json'))
    expected = {
        **files,
        'config/opencode/cli.json': (
            json.dumps({'$schema': 'https://opencode.ai/v2/cli.json',
                        'plugins': [], 'theme': theme}, sort_keys=True) + '\n'
        ).encode('utf-8'),
    }
    dest.mkdir(mode=0o700)
    for name in ('home', 'home/.local/share', 'state', 'cache', 'tmp', 'config/opencode'):
        (dest / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, content in expected.items():
        location = dest / name
        validate_location(location, BASE)
        location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(location, content)
    receipt = json.dumps({'runtime_id': runtime_id, 'assets_sha256': expected_sha,
                          'files': sorted(expected)}, sort_keys=True) + '\n'
    write_new(dest / 'assets-receipt.json', receipt.encode('utf-8'))
    return dest

def validate_location(path: pathlib.Path, parent: pathlib.Path) -> None:
    if not path.is_relative_to(parent) or path == parent:
        fail('path outside oc2 sandbox area')
    cur = path
    while cur != parent:
        if cur.is_symlink():
            fail('symlink in destination path')
        cur = cur.parent


def write_new(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)


def prepare(
    bundle: pathlib.Path,
    manifest_sha: str,
    assets: dict[str, bytes] | None = None,
    assets_sha: str | None = None,
    phase4_plugins: VerifiedPhase4PluginBundle | None = None,
) -> pathlib.Path:
    if (assets is None) != (assets_sha is None):
        fail('asset content/identity mismatch')
    if phase4_plugins is not None and (assets is None or assets_sha is None):
        fail('Phase 4 Runtime requires the verified Phase 3 asset bundle')

    server = json.loads(regular(bundle / 'opencode.jsonc'))
    client = json.loads(regular(bundle / 'cli.json'))
    manifest = json.loads(
        regular(bundle / 'export-manifest.json'), object_pairs_hook=_unique_json_object,
    )
    verification_only = manifest.get('config_format') == 'oc2-verification'
    unified_runtime = manifest.get('config_format') == 'opencode-v2-unified'
    plugin_runtime = verification_only or unified_runtime
    if unified_runtime and phase4_plugins is None:
        fail('unified Runtime requires its pinned Phase 4 plugin bundle')
    generator_fingerprint: str | None = None
    if verification_only:
        if assets is None:
            fail('verification Runtime requires selected Plugin/MCP assets')
        from oc2_identity import verification_generator_fingerprint

        generator_fingerprint = verification_generator_fingerprint(
            pathlib.Path(__file__),
            pathlib.Path(__file__).with_name('oc2_agent_native.py'),
            pathlib.Path(__file__).with_name('oc2_identity.py'),
        )
    if phase4_plugins is not None:
        if not plugin_runtime or assets_sha is None:
            fail('Phase 4 plugins require a selected Plugin Runtime')
        from oc2_identity import (
            Phase4RuntimeIdentity,
            phase4_generator_fingerprint,
            phase4_runtime_identity_sha256,
            unified_runtime_identity_sha256,
        )

        generator_fingerprint = phase4_generator_fingerprint((
            pathlib.Path(__file__),
            pathlib.Path(__file__).with_name('oc2_agent_native.py'),
            pathlib.Path(__file__).with_name('oc2_identity.py'),
            pathlib.Path(__file__).with_name('oc2_phase4_policy.py'),
        ))
        identity = Phase4RuntimeIdentity(
            manifest_sha,
            assets_sha,
            phase4_plugins.bundle_sha256,
            generator_fingerprint,
        )
        runtime_id = (
            unified_runtime_identity_sha256(identity)
            if unified_runtime else phase4_runtime_identity_sha256(identity)
        )
        dest = BASE / 'runtime' / runtime_id[:16]
    else:
        dest = runtime_path(manifest_sha, assets_sha, generator_fingerprint)
    validate_location(dest, BASE)
    asset_files: dict[str, bytes] = {}
    bundled_plugins: dict[str, bytes] = {}
    if assets is not None:
        native_payload = validate_native_asset(assets[NATIVE_ASSET_TARGET])
        if native_payload['source_sha256'] != manifest.get('source_sha256'):
            fail('APM config and Native Agent asset source SHA mismatch')
        if (phase4_plugins is not None
                and phase4_plugins.source_sha256 != native_payload['source_sha256']):
            fail('Phase 4 plugin and base asset source SHA mismatch')
        plugin_enabled = native_payload['plugins']['enabled']
        if plugin_runtime != plugin_enabled:
            fail('Runtime mode does not match Plugin/MCP asset selection')
        if verification_only and 'agents' in server:
            fail('verification config must not select a model or Native Agent')
        if not verification_only and server.get('agents', {}) != native_payload['agents']:
            fail('V2 config and Native Agent asset mismatch')
        runtime_options = native_payload['runtime']
        if unified_runtime:
            if not isinstance(runtime_options, dict):
                fail('unified Runtime options are missing from the APM asset')
            if json.loads(assets['theme.json']) != {'name': runtime_options['theme']}:
                fail('TUI theme does not match the APM Runtime options')
        # Instructions are resolved inside the guest, not on the Host.
        rule_names = sorted(p for p in assets if p.startswith('config/opencode/rules/'))
        server['instructions'] = [str(dest / name) for name in rule_names]
        client['theme'] = json.loads(assets['theme.json'])
        asset_files = {name: value for name, value in assets.items()
                       if name != 'theme.json'}
        if plugin_runtime:
            plugin_metadata = _verify_plugin_source_metadata(assets[PLUGIN_META_TARGET])
            plugin_source = verify_superpowers_source()
            if plugin_metadata['tree_sha256'] != plugin_source.tree_sha256:
                fail('Superpowers source tree SHA-256 mismatch')
            bundled_plugins = {
                name[len(PLUGIN_PREFIX):]: content
                for name, content in assets.items()
                if name.startswith(PLUGIN_PREFIX)
            }
            raw_plugin_files = plugin_metadata.get('plugin_files')
            if not isinstance(raw_plugin_files, list):
                fail('Superpowers Plugin bundle differs from its file manifest')
            plugin_files: list[str] = []
            for name in raw_plugin_files:
                if not isinstance(name, str):
                    fail('Superpowers Plugin bundle differs from its file manifest')
                plugin_files.append(name)
            if set(bundled_plugins) != set(plugin_files):
                fail('Superpowers Plugin bundle differs from its file manifest')
            plugin_file_names = [name for name in plugin_files if isinstance(name, str)]
            required_skills = {
                name for name in plugin_file_names
                if name.startswith('skills/') and name.endswith('/SKILL.md')
                and len(name.split('/')) == 3
            }
            entrypoint = plugin_metadata.get('entrypoint')
            if not isinstance(entrypoint, str):
                fail('Superpowers Plugin entrypoint is invalid')
            required_plugin_files = {
                'index.js', 'package.json', entrypoint,
                *required_skills,
            }
            if not required_skills or not required_plugin_files <= set(bundled_plugins):
                fail('Verification Asset Bundle is missing Native Skill files')
            source_files = {item.path: item.content for item in plugin_source.files}
            if any(source_files.get(name) != content for name, content in bundled_plugins.items()):
                fail('Plugin Asset Bundle differs from the pinned source tree')
            plugin_path = dest / 'plugins/superpowers'
            server['plugins'] = [str(plugin_path)]
            mcp_config: dict[str, JsonValue] = {
                'servers': {
                    'oc2-status': {
                        'type': 'local',
                        'enabled': True,
                        'command': [
                            'python3', '-I', str(dest / MCP_SERVER_TARGET),
                        ],
                    },
                },
            }
            if unified_runtime:
                if not isinstance(runtime_options, dict):
                    fail('unified Runtime options are missing from the APM asset')
                timeout_ms = runtime_options.get('mcpExecutionTimeoutMs')
                if type(timeout_ms) is not int or not 1000 <= timeout_ms <= 600000:
                    fail('MCP execution timeout violates safety bounds')
                mcp_config['timeout'] = {'execution': timeout_ms}
                policies = server.get('policies')
                if not isinstance(policies, list) or not isinstance(server.get('providers'), dict):
                    fail('unified Runtime Provider policy is missing')
                policies.extend([
                    {'action': 'plugin.use', 'resource': str(plugin_path), 'effect': 'allow'},
                    {'action': 'mcp.use', 'resource': 'oc2-status', 'effect': 'allow'},
                ])
            else:
                server['policies'] = [
                    {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
                    {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
                    {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
                    {'action': 'plugin.use', 'resource': str(plugin_path), 'effect': 'allow'},
                    {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
                    {'action': 'mcp.use', 'resource': 'oc2-status', 'effect': 'allow'},
                ]
            server['mcp'] = mcp_config
            if phase4_plugins is not None:
                if unified_runtime:
                    if not isinstance(runtime_options, dict):
                        fail('Phase 5 Runtime options are missing')
                    watchdog = runtime_options['watchdog']
                    observer = runtime_options['sibylObserver']
                    if not isinstance(watchdog, dict) or not isinstance(observer, dict):
                        fail('Akane/Sibyl Runtime options are invalid')
                else:
                    watchdog = {
                        'enabled': True,
                        'stage1Ms': 2_147_483_647,
                        'stage2Ms': 2_147_483_647,
                        'maxPings': 1,
                        'maxToolGateCycles': 1,
                        'notifierType': 'tmux',
                        'notifyWaiting': False,
                    }
                    observer = {
                        'enabled': True,
                        'maxVisibleSubagents': 8,
                        'showModel': False,
                        'showProvider': False,
                        'showLatestText': False,
                        'showReasoningSummary': False,
                    }
                akane_path = dest / 'plugins/akane'
                sibyl_path = dest / 'plugins/sibyl'
                server['plugins'].append({
                    'package': str(akane_path),
                    'options': {
                        **watchdog,
                        'agents': {
                            'include': (
                                ['__oc2_phase4_fixture__'] if not unified_runtime
                                else ['hephaestus', 'oracle']
                            ),
                        },
                    },
                })
                server['policies'].append({
                    'action': 'plugin.use',
                    'resource': str(akane_path),
                    'effect': 'allow',
                })
                client['plugins'] = [{
                    'package': str(sibyl_path),
                    'options': {'observer': observer},
                }]
                for target, content in phase4_plugins.files:
                    if target in asset_files:
                        fail('Phase 4 plugin asset conflicts with base Runtime assets')
                    asset_files[target] = content
    elif plugin_runtime:
        fail('selected Plugin Runtime requires Plugin/MCP assets')

    def encoded(value: object) -> bytes:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')) + '\n').encode('utf-8')

    expected = {
        'config/opencode/opencode.jsonc': encoded(server),
        'config/opencode/cli.json': encoded(client),
        **asset_files,
    }
    if plugin_runtime:
        if plugin_source is not None:
            expected.update({
                PLUGIN_PREFIX + item.path: item.content
                for item in plugin_source.files
            })
        elif verification_only and phase4_plugins is None:
            fail('verification Runtime is missing its pinned Plugin source')
    if phase4_plugins is not None:
        expected.update(dict(phase4_plugins.files))
    receipt: dict[str, JsonValue] = {
        'manifest_sha256': manifest_sha,
        'opencode_version': VERSION,
    }
    if assets_sha is not None:
        receipt['assets_sha256'] = assets_sha
    if verification_only:
        receipt['verification_only'] = True
        if generator_fingerprint is None:
            fail('verification Runtime is missing its generator fingerprint')
        receipt['generator_sha256'] = generator_fingerprint
        if plugin_source is not None:
            receipt['plugin_source'] = {
                'repository': SUPERPOWERS_REPOSITORY,
                'commit': SUPERPOWERS_COMMIT,
                'path': SUPERPOWERS_TREE_PATH,
                'file_count': len(plugin_source.files),
                'total_bytes': plugin_source.total_bytes,
                'tree_sha256': plugin_source.tree_sha256,
                'file_sha256': {item.path: item.sha256 for item in plugin_source.files},
            }
        else:
            receipt['plugin_source'] = {
                'repository': SUPERPOWERS_REPOSITORY,
                'commit': SUPERPOWERS_COMMIT,
                'path': SUPERPOWERS_TREE_PATH,
                'file_count': plugin_metadata['file_count'],
                'total_bytes': plugin_metadata['total_bytes'],
                'tree_sha256': plugin_metadata['tree_sha256'],
                'file_sha256': {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in bundled_plugins.items()
                },
            }
    elif unified_runtime:
        if generator_fingerprint is None or plugin_metadata is None:
            fail('unified Runtime is missing its generator fingerprint')
        receipt['unified_runtime'] = True
        receipt['generator_sha256'] = generator_fingerprint
        receipt['plugin_source'] = {
            'repository': SUPERPOWERS_REPOSITORY,
            'commit': SUPERPOWERS_COMMIT,
            'path': SUPERPOWERS_TREE_PATH,
            'file_count': plugin_metadata['file_count'],
            'total_bytes': plugin_metadata['total_bytes'],
            'tree_sha256': plugin_metadata['tree_sha256'],
            'file_sha256': {
                name: hashlib.sha256(content).hexdigest()
                for name, content in bundled_plugins.items()
            },
        }
    if phase4_plugins is not None:
        receipt['phase4_plugins_sha256'] = phase4_plugins.bundle_sha256
        receipt['phase4_plugins'] = [
            {
                'id': plugin.plugin_id,
                'package': plugin.package,
                'version': plugin.version,
                'repository': plugin.repository,
                'commit': plugin.commit,
                'acquisition': plugin.acquisition,
                'artifact_sha512': plugin.artifact_sha512,
                'entrypoint': plugin.entrypoint,
                'build_tool': plugin.build_tool,
                'lock_sha256': plugin.lock_sha256,
            }
            for plugin in phase4_plugins.plugins
        ]
    marker = dest / 'receipt.json'
    if dest.exists():
        if verification_only:
            fail('verification Runtime identity already exists; refusing reuse')
        if not dest.is_dir() or dest.is_symlink() or not marker.is_file() or marker.is_symlink():
            fail('incomplete or untrusted runtime directory; refusing overwrite')
        if json.loads(regular(marker)) != receipt:
            fail('runtime receipt mismatch')
        for name, value in expected.items():
            location = dest / name
            validate_location(location, BASE)
            if regular(location) != value:
                fail('existing runtime asset mismatch')
        return pathlib.Path(dest)

    (dest / 'config/opencode').mkdir(parents=True, mode=0o700)
    for name in ('home', 'data', 'state', 'cache', 'tmp', 'project'):
        (dest / name).mkdir(mode=0o700)
    for name, data in expected.items():
        location = dest / name
        location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(location, data)
    write_new(marker, encoded(receipt))
    return pathlib.Path(dest)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=pathlib.Path)
    p.add_argument('--expected-sha')
    p.add_argument('--assets', type=pathlib.Path)
    p.add_argument('--expected-assets-sha')
    p.add_argument('--phase4-plugin-assets', type=pathlib.Path)
    p.add_argument('--expected-phase4-plugin-sha')
    p.add_argument('--install-assets-runtime')
    args = p.parse_args(argv)
    try:
        if args.install_assets_runtime is not None:
            if args.phase4_plugin_assets is not None or args.expected_phase4_plugin_sha is not None:
                fail('Phase 4 plugin assets cannot be used with the generic asset installer')
            if args.assets is None or args.expected_assets_sha is None:
                fail('asset runtime requires verified assets')
            if re.fullmatch(r'[0-9a-f]{64}', args.install_assets_runtime) is None:
                fail('invalid asset runtime identity')
            runtime_assets = verify_assets(args.assets, args.expected_assets_sha)
            count_summary = _asset_count_summary(runtime_assets)
            asset_runtime = _install_verified_assets(
                runtime_assets, args.expected_assets_sha, args.install_assets_runtime,
            )
            print('OC2_ASSETS_VERIFIED: ' + count_summary)
            print('OC2_RUNTIME_PREPARED: ' + str(asset_runtime))
            print('OC2_RUNTIME_VERSION: ' + VERSION)
            return 0
        if args.bundle is None or args.expected_sha is None:
            fail('configuration bundle and expected SHA are required')
        if re.fullmatch('[0-9a-f]{64}', args.expected_sha) is None:
            fail('invalid expected SHA')
        bundle = args.bundle
        validate_location(bundle, BASE)
        digest = verify(bundle)
        if digest != args.expected_sha:
            fail('host/guest manifest SHA mismatch')
        if (args.assets is None) != (args.expected_assets_sha is None):
            fail('asset arguments must be provided together')
        assets = verify_assets(args.assets, args.expected_assets_sha) if args.assets else None
        if (args.phase4_plugin_assets is None) != (args.expected_phase4_plugin_sha is None):
            fail('Phase 4 plugin asset file and hash must be provided together')
        phase4_plugins: VerifiedPhase4PluginBundle | None = None
        if args.phase4_plugin_assets is not None:
            if assets is None:
                fail('Phase 4 plugin assets require the verified base asset bundle')
            native = validate_native_asset(assets[NATIVE_ASSET_TARGET])
            phase4_plugins = verify_phase4_plugin_assets(
                args.phase4_plugin_assets,
                args.expected_phase4_plugin_sha,
                native['source_sha256'],
            )
        runtime = prepare(
            bundle, digest, assets, args.expected_assets_sha, phase4_plugins=phase4_plugins,
        )
        print('OC2_GUEST_CONFIG_VERIFIED')
        if phase4_plugins is not None:
            print('OC2_PHASE4_PLUGINS_VERIFIED: server=akane tui=sibyl recovery_ping=not-executed')
        print('OC2_RUNTIME_PREPARED: ' + str(runtime))
        if assets is not None:
            print('OC2_ASSETS_VERIFIED: ' + _asset_count_summary(assets))
        print('OC2_RUNTIME_VERSION: ' + VERSION)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print('OC2_GUEST_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
