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

VERSION = "2.1.4"
BASE = pathlib.Path('/home/agent/workspace/oc2')
FILES = ('opencode.jsonc', 'cli.json', 'export-manifest.json')
CLI_CANDIDATES = (
    '/home/agent/.local/opencode-v2/node_modules/.bin/opencode',
    '/home/agent/.local/oc2-runtime/node_modules/.bin/opencode',
)


def fail(reason: str) -> None:
    raise ValueError(reason)


def regular(path: pathlib.Path, max_bytes: int = 1048576) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        fail('non-regular or oversized file: ' + path.name)
    return path.read_bytes()


def verify(bundle: pathlib.Path) -> str:
    if bundle.is_symlink() or not bundle.is_dir() or set(x.name for x in bundle.iterdir()) != set(FILES):
        fail('invalid bundle directory or members')
    data = {name: regular(bundle / name) for name in FILES}
    manifest = json.loads(data['export-manifest.json'])
    server = json.loads(data['opencode.jsonc'])
    client = json.loads(data['cli.json'])
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
    if client != {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}:
        fail('unsafe TUI config')
    return hashlib.sha256(data['export-manifest.json']).hexdigest()


def runtime_path(manifest_sha: str) -> pathlib.Path:
    return BASE / 'runtime' / manifest_sha[:16]


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


def prepare(bundle: pathlib.Path, manifest_sha: str) -> pathlib.Path:
    dest = runtime_path(manifest_sha)
    validate_location(dest, BASE)
    marker = dest / 'receipt.json'
    if dest.exists():
        if not dest.is_dir() or dest.is_symlink() or not marker.is_file() or marker.is_symlink():
            fail('incomplete or untrusted runtime directory; refusing overwrite')
        receipt = json.loads(regular(marker))
        if receipt != {'manifest_sha256': manifest_sha, 'opencode_version': VERSION}:
            fail('runtime receipt mismatch')
        if regular(dest / 'config/opencode/opencode.jsonc') != regular(bundle / 'opencode.jsonc'):
            fail('existing server config mismatch')
        if regular(dest / 'config/opencode/cli.json') != regular(bundle / 'cli.json'):
            fail('existing TUI config mismatch')
        return dest
    (dest / 'config/opencode').mkdir(parents=True, mode=0o700)
    for name in ('home', 'data', 'state', 'cache', 'tmp', 'project'):
        (dest / name).mkdir(mode=0o700)
    write_new(dest / 'config/opencode/opencode.jsonc', regular(bundle / 'opencode.jsonc'))
    write_new(dest / 'config/opencode/cli.json', regular(bundle / 'cli.json'))
    write_new(marker, (json.dumps({'manifest_sha256': manifest_sha, 'opencode_version': VERSION}, sort_keys=True) + '\n').encode())
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=pathlib.Path, required=True)
    p.add_argument('--expected-sha', required=True)
    args = p.parse_args(argv)
    try:
        if re.fullmatch('[0-9a-f]{64}', args.expected_sha) is None:
            fail('invalid expected SHA')
        bundle = args.bundle
        validate_location(bundle, BASE)
        digest = verify(bundle)
        if digest != args.expected_sha:
            fail('host/guest manifest SHA mismatch')
        runtime = prepare(bundle, digest)
        print('OC2_GUEST_CONFIG_VERIFIED')
        print('OC2_RUNTIME_PREPARED: ' + str(runtime))
        print('OC2_RUNTIME_VERSION: ' + VERSION)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print('OC2_GUEST_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
