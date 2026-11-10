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
from typing import NoReturn

VERSION = "2.1.4"
BASE = pathlib.Path('/home/agent/workspace/oc2')
SERVER_CONFIG = 'opencode.jsonc'
CLIENT_CONFIG = 'cli.json'
EXPORT_MANIFEST = 'export-manifest.json'
THEME_FILE = 'theme.json'
FILES = (SERVER_CONFIG, CLIENT_CONFIG, EXPORT_MANIFEST)
ASSET_SCHEMA = 'dotfiles-ai/oc2-assets/v1'
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
    THEME_FILE,
})
MAX_ASSETS = 512 * 1024

def fail(reason: str) -> NoReturn:
    """Stop processing the bundle with a validation error."""
    raise ValueError(reason)


def regular(path: pathlib.Path, max_bytes: int = 1048576) -> bytes:
    """Read a bounded regular file, rejecting links and oversized inputs."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        fail('non-regular or oversized file: ' + path.name)
    return path.read_bytes()


def verify(bundle: pathlib.Path) -> str:
    """Verify bundle structure, artifact hashes, and allowed configuration."""
    if bundle.is_symlink() or not bundle.is_dir() or {x.name for x in bundle.iterdir()} != set(FILES):
        fail('invalid bundle directory or members')
    data = {name: regular(bundle / name) for name in FILES}
    manifest = json.loads(data[EXPORT_MANIFEST])
    server = json.loads(data[SERVER_CONFIG])
    client = json.loads(data[CLIENT_CONFIG])
    if (manifest.get('schema') != 'dotfiles-ai/sandbox-export/v0'
            or manifest.get('generator') != 'v0.1'
            or manifest.get('opencode_version') != VERSION
            or manifest.get('plugins_exported') != 0
            or manifest.get('mcp_entries_exported') != 0):
        fail('unrecognized exporter manifest')
    hashes = {k: hashlib.sha256(data[k]).hexdigest() for k in FILES[:2]}
    if manifest.get('artifacts_sha256') != hashes:
        fail('bundle SHA-256 mismatch')
    if (not isinstance(server, dict) or server.get('plugins') != [] or server.get('mcp') != {}
            or server.get('shell') not in ('bash', 'sh', 'zsh') or type(server.get('snapshot')) is not bool):
        fail('unsafe server config')
    if client != {'$schema': 'https://opencode.ai/v2/' + CLIENT_CONFIG, 'plugins': []}:
        fail('unsafe TUI config')
    return hashlib.sha256(data[EXPORT_MANIFEST]).hexdigest()


def runtime_path(manifest_sha: str, assets_sha: str | None = None) -> pathlib.Path:
    """Derive the immutable runtime directory from verified content hashes."""
    if assets_sha:
        combined = hashlib.sha256(
            bytes.fromhex(manifest_sha) + bytes.fromhex(assets_sha)
        ).hexdigest()
        return BASE / 'runtime' / combined[:16]
    return BASE / 'runtime' / manifest_sha[:16]


def verify_assets(source: pathlib.Path, expected_sha: str) -> dict[str, bytes]:
    """Verify selected assets and return their validated byte content."""
    validate_location(source, BASE)
    if re.fullmatch(r'[0-9a-f]{64}', expected_sha) is None:
        fail('invalid asset SHA')
    raw = regular(source, MAX_ASSETS)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        fail('host/guest asset SHA mismatch')
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ValueError('invalid asset JSON') from exc
    files, hashes = _asset_payload(payload)
    result: dict[str, bytes] = {}
    for name in sorted(ASSET_TARGETS):
        value = files[name]
        if not isinstance(value, str):
            fail('non-text asset')
        encoded = value.encode('utf-8')
        if len(encoded) > 65536 or hashlib.sha256(encoded).hexdigest() != hashes[name]:
            fail('asset content SHA mismatch')
        result[name] = encoded
    _validate_theme(result[THEME_FILE])
    # No third-party agent metadata or model routing is imported.
    return result


def _asset_payload(payload: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    """Validate the asset manifest shape and its strict path allowlist."""
    if not isinstance(payload, dict) or set(payload) != {'schema', 'files', 'sha256'}:
        fail('invalid asset manifest')
    if payload.get('schema') != ASSET_SCHEMA:
        fail('unexpected asset schema')
    files = payload['files']
    hashes = payload['sha256']
    if (not isinstance(files, dict) or not isinstance(hashes, dict)
            or set(files) != ASSET_TARGETS or set(hashes) != ASSET_TARGETS):
        fail('asset path allowlist mismatch')
    return files, hashes


def _validate_theme(data: bytes) -> None:
    """Reject malformed or unapproved theme metadata."""
    try:
        theme = json.loads(data)
    except ValueError as exc:
        raise ValueError('invalid theme') from exc
    if (not isinstance(theme, dict) or set(theme) != {'name'}
            or not isinstance(theme['name'], str)
            or not re.fullmatch(r'[a-z0-9-]{1,40}', theme['name'])):
        fail('unsafe TUI theme')

def validate_location(path: pathlib.Path, parent: pathlib.Path) -> None:
    """Require a destination below the runtime root with no symlink parents."""
    if not path.is_relative_to(parent) or path == parent:
        fail('path outside oc2 sandbox area')
    cur = path
    while cur != parent:
        if cur.is_symlink():
            fail('symlink in destination path')
        cur = cur.parent


def write_new(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    """Create a new file exclusively with the requested restrictive mode."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)


def prepare(
    bundle: pathlib.Path,
    manifest_sha: str,
    assets: dict[str, bytes] | None = None,
    assets_sha: str | None = None,
) -> pathlib.Path:
    """Materialize verified configuration and assets into a new isolated runtime."""
    if (assets is None) != (assets_sha is None):
        fail('asset content/identity mismatch')
    dest = runtime_path(manifest_sha, assets_sha)
    validate_location(dest, BASE)

    server = json.loads(regular(bundle / SERVER_CONFIG))
    client = json.loads(regular(bundle / CLIENT_CONFIG))
    asset_files: dict[str, bytes] = {}
    if assets is not None:
        # Instructions are resolved inside the guest, not on the Host.
        rule_names = sorted(p for p in assets if p.startswith('config/opencode/rules/'))
        server['instructions'] = [str(dest / name) for name in rule_names]
        client['theme'] = json.loads(assets[THEME_FILE])
        asset_files = {name: value for name, value in assets.items()
                       if name != THEME_FILE}

    def encoded(value: object) -> bytes:
        """Serialize runtime configuration as canonical UTF-8 JSON."""
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')) + '\n').encode('utf-8')

    expected = {
        f'config/opencode/{SERVER_CONFIG}': encoded(server),
        f'config/opencode/{CLIENT_CONFIG}': encoded(client),
        **asset_files,
    }
    receipt = {'manifest_sha256': manifest_sha, 'opencode_version': VERSION}
    if assets_sha is not None:
        receipt['assets_sha256'] = assets_sha
    marker = dest / 'receipt.json'
    if not _verify_existing_runtime(dest, marker, receipt, expected):
        (dest / 'config/opencode').mkdir(parents=True, mode=0o700)
        for name in ('home', 'data', 'state', 'cache', 'tmp', 'project'):
            (dest / name).mkdir(mode=0o700)
        for name, data in expected.items():
            location = dest / name
            location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_new(location, data)
        write_new(marker, encoded(receipt))
    return dest


def _verify_existing_runtime(
    dest: pathlib.Path,
    marker: pathlib.Path,
    receipt: dict[str, str],
    expected: dict[str, bytes],
) -> bool:
    """Check whether an existing runtime exactly matches its receipt and assets."""
    if not dest.exists():
        return False
    if not dest.is_dir() or dest.is_symlink() or not marker.is_file() or marker.is_symlink():
        fail('incomplete or untrusted runtime directory; refusing overwrite')
    if json.loads(regular(marker)) != receipt:
        fail('runtime receipt mismatch')
    for name, value in expected.items():
        location = dest / name
        validate_location(location, BASE)
        if regular(location) != value:
            fail('existing runtime asset mismatch')
    return True

def main(argv: list[str] | None = None) -> int:
    """Validate staged bundle inputs and prepare the guest runtime."""
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=pathlib.Path, required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--assets', type=pathlib.Path)
    p.add_argument('--expected-assets-sha')
    args = p.parse_args(argv)
    try:
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
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('OC2_GUEST_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
