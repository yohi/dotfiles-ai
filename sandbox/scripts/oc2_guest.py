#!/usr/bin/env python3
"""Validate an oc2 configuration bundle and activate an isolated OpenCode v2 runtime.

Executed by the agent inside a mountless Docker Sandbox. No network operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Final, NoReturn, TypeAlias

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
})
MAX_ASSETS = 512 * 1024

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


def regular(path: pathlib.Path, max_bytes: int = 1048576) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        fail('non-regular or oversized file: ' + path.name)
    return path.read_bytes()


def verify_v2_config(server: dict[str, JsonValue]) -> None:
    """Reject provider fallback, Guest auth, and literal credentials at activation."""
    if set(server) != {'$schema', 'shell', 'snapshot', 'model', 'providers', 'policies'}:
        fail('unexpected V2 server config fields')
    model = server.get('model')
    providers = server.get('providers')
    policies = server.get('policies')
    allowed_providers = {'openai', 'cloudflare-ai-gateway-custom'}
    if (not isinstance(model, str) or '/' not in model
            or not isinstance(providers, dict) or set(providers) != allowed_providers
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
    expected_policies: list[JsonValue] = [
        {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
        {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
        {'action': 'provider.use', 'resource': 'cloudflare-ai-gateway-custom', 'effect': 'allow'},
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
        case 'opencode-v2':
            verify_v2_config(server)
        case _:
            fail('unrecognized config format')
    if client != {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}:
        fail('unsafe TUI config')
    return hashlib.sha256(data['export-manifest.json']).hexdigest()


def runtime_path(manifest_sha: str, assets_sha: str | None = None) -> pathlib.Path:
    if assets_sha:
        combined = hashlib.sha256(
            bytes.fromhex(manifest_sha) + bytes.fromhex(assets_sha)
        ).hexdigest()
        return BASE / 'runtime' / combined[:16]
    return BASE / 'runtime' / manifest_sha[:16]


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
            or not set(files) <= ASSET_TARGETS or set(hashes) != set(files)
            or 'theme.json' not in files):
        fail('asset path allowlist mismatch')
    result: dict[str, bytes] = {}
    for name in sorted(ASSET_TARGETS):
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
    # No third-party agent metadata or model routing is imported.
    return result


def install_assets(source: pathlib.Path, expected_sha: str, runtime_id: str) -> pathlib.Path:
    if re.fullmatch(r'[0-9a-f]{64}', runtime_id) is None:
        fail('invalid asset runtime identity')
    files = verify_assets(source, expected_sha)
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
) -> pathlib.Path:
    if (assets is None) != (assets_sha is None):
        fail('asset content/identity mismatch')
    dest = runtime_path(manifest_sha, assets_sha)
    validate_location(dest, BASE)

    server = json.loads(regular(bundle / 'opencode.jsonc'))
    client = json.loads(regular(bundle / 'cli.json'))
    asset_files: dict[str, bytes] = {}
    if assets is not None:
        # Instructions are resolved inside the guest, not on the Host.
        rule_names = sorted(p for p in assets if p.startswith('config/opencode/rules/'))
        server['instructions'] = [str(dest / name) for name in rule_names]
        client['theme'] = json.loads(assets['theme.json'])
        asset_files = {name: value for name, value in assets.items()
                       if name != 'theme.json'}

    def encoded(value: object) -> bytes:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')) + '\n').encode('utf-8')

    expected = {
        'config/opencode/opencode.jsonc': encoded(server),
        'config/opencode/cli.json': encoded(client),
        **asset_files,
    }
    receipt = {'manifest_sha256': manifest_sha, 'opencode_version': VERSION}
    if assets_sha is not None:
        receipt['assets_sha256'] = assets_sha
    marker = dest / 'receipt.json'
    if dest.exists():
        if not dest.is_dir() or dest.is_symlink() or not marker.is_file() or marker.is_symlink():
            fail('incomplete or untrusted runtime directory; refusing overwrite')
        if json.loads(regular(marker)) != receipt:
            fail('runtime receipt mismatch')
        for name, value in expected.items():
            location = dest / name
            validate_location(location, BASE)
            if regular(location) != value:
                fail('existing runtime asset mismatch')
        return dest

    (dest / 'config/opencode').mkdir(parents=True, mode=0o700)
    for name in ('home', 'data', 'state', 'cache', 'tmp', 'project'):
        (dest / name).mkdir(mode=0o700)
    for name, data in expected.items():
        location = dest / name
        location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(location, data)
    write_new(marker, encoded(receipt))
    return dest

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=pathlib.Path)
    p.add_argument('--expected-sha')
    p.add_argument('--assets', type=pathlib.Path)
    p.add_argument('--expected-assets-sha')
    p.add_argument('--install-assets-runtime')
    args = p.parse_args(argv)
    try:
        if args.install_assets_runtime is not None:
            if args.assets is None or args.expected_assets_sha is None:
                fail('asset runtime requires verified assets')
            runtime = install_assets(args.assets, args.expected_assets_sha,
                                     args.install_assets_runtime)
            print('OC2_ASSETS_VERIFIED: rules=7 commands=1 skills=2 theme=1 custom_agents=0 routing=none')
            print('OC2_RUNTIME_PREPARED: ' + str(runtime))
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
        runtime = prepare(bundle, digest, assets, args.expected_assets_sha)
        print('OC2_GUEST_CONFIG_VERIFIED')
        if assets is not None:
            print('OC2_ASSETS_VERIFIED: rules=7 commands=1 skills=2 theme=1 custom_agents=0 routing=none')
        print('OC2_RUNTIME_PREPARED: ' + str(runtime))
        print('OC2_RUNTIME_VERSION: ' + VERSION)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print('OC2_GUEST_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
