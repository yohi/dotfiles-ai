"""Guest artifact placement and Broker-only Config for the OC2 Host Broker path.

Reuses the Guest launcher, provider and plugin entry from a trusted local
checkout of oc-cf-aig-subscription (never modified, never fetched). Identity is
pinned by source commit, a Manifest whose SHA-256 is fixed in this module, and
per-file SHA-256/size. The Guest re-verifies everything independently.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from oc2_host_broker import (
    MODEL_ID,
    PROVIDER_ID,
    HostBrokerError,
    HostBrokerSelection,
    fixture_guest_path,
)

HERE = pathlib.Path(__file__).resolve().parent
PIN_PATH: Final[pathlib.Path] = HERE.parent / 'config' / 'host-broker-guest-artifacts.json'
MANIFEST_SHA256: Final[str] = '39e17348552c424a4d6e77792e8c60166327e93799362fd807e262f53eff7a21'
MANIFEST_SCHEMA: Final[str] = 'dotfiles-ai/oc2-host-broker-guest-artifacts/v1'
SOURCE_REPO: Final[str] = 'yohi/oc-cf-aig-subscription'
ALLOWED_FILES: Final[frozenset[str]] = frozenset({
    'bin/guest-launch.mjs', 'src/guest/index.js', 'src/guest/provider.mjs',
})
MAX_FILE_BYTES: Final[int] = 64 * 1024
MAX_PROMPT_BYTES: Final[int] = 4096
VERIFIED_MARKER: Final[str] = 'OC2_BROKER_GUEST_VERIFIED'
_IDENTITY_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-host-broker-runtime/v1\0'
_SECRET_LIKE: Final[re.Pattern[str]] = re.compile(r'ocb_[A-Za-z0-9_-]{16,}|\bsk-[A-Za-z0-9_-]{8,}')
_PROVIDER_MARKERS: Final[tuple[bytes, ...]] = (
    b'export const PROVIDER_ID = "oc-cf-aig";',
    b'export const MODEL_ID = "gpt-6-luna";',
)


def broker_dir(runtime: str) -> str:
    return runtime + '/broker'


def launcher_path(runtime: str) -> str:
    return broker_dir(runtime) + '/bin/guest-launch.mjs'


def plugin_dir(runtime: str) -> str:
    return broker_dir(runtime) + '/src/guest'


def config_path(runtime: str) -> str:
    return runtime + '/config/opencode/opencode.jsonc'


@dataclass(frozen=True, slots=True)
class VerifiedArtifacts:
    manifest: dict[str, Any]
    manifest_sha256: str
    files: dict[str, bytes]


def load_manifest(path: pathlib.Path = PIN_PATH,
                  expected_sha256: str = MANIFEST_SHA256) -> tuple[dict[str, Any], str]:
    """Read the pinned Manifest; its SHA-256 is fixed in code, not trusted from disk."""
    try:
        if path.is_symlink() or not path.is_file():
            raise HostBrokerError('artifact manifest is missing or linked')
        raw = path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, ValueError):
        raise HostBrokerError('artifact manifest could not be read') from None
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise HostBrokerError('artifact manifest SHA-256 does not match the pinned value')
    files = manifest.get('files') if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict)
            or set(manifest) != {'schema', 'source_repo', 'source_commit', 'provider',
                                 'model', 'files'}
            or manifest['schema'] != MANIFEST_SCHEMA
            or manifest['source_repo'] != SOURCE_REPO
            or manifest['provider'] != PROVIDER_ID or manifest['model'] != MODEL_ID
            or not isinstance(manifest['source_commit'], str)
            or re.fullmatch(r'[0-9a-f]{40}', manifest['source_commit']) is None
            or not isinstance(files, dict) or set(files) != ALLOWED_FILES):
        raise HostBrokerError('artifact manifest schema or allowlist is invalid')
    for entry in files.values():
        if (not isinstance(entry, dict) or set(entry) != {'sha256', 'size'}
                or not isinstance(entry['sha256'], str)
                or re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) is None
                or type(entry['size']) is not int or not 0 < entry['size'] <= MAX_FILE_BYTES):
            raise HostBrokerError('artifact manifest entry is invalid')
    return manifest, digest


def _git_head(source: pathlib.Path) -> str:
    try:
        result = subprocess.run(
            ['git', '-C', str(source), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise HostBrokerError('artifact source commit could not be determined') from None
    return result.stdout.strip() if result.returncode == 0 else ''


def verify_source(
    source: pathlib.Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    git_head: Callable[[pathlib.Path], str] = _git_head,
) -> VerifiedArtifacts:
    """Read only allowlisted files from a trusted local checkout and verify them.

    Nothing is fetched or installed; a missing or different file stops.
    """
    if source.is_symlink() or not source.is_dir():
        raise HostBrokerError('artifact source must be an existing real directory')
    if git_head(source) != manifest['source_commit']:
        raise HostBrokerError('artifact source commit does not match the pinned commit')
    files: dict[str, bytes] = {}
    flags = os.O_RDONLY | os.O_NOFOLLOW
    for rel, expected in sorted(manifest['files'].items()):
        current = source
        for part in pathlib.PurePosixPath(rel).parts[:-1]:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise HostBrokerError('artifact source path is missing or linked')
        try:
            fd = os.open(current / pathlib.PurePosixPath(rel).name, flags)
        except OSError:
            raise HostBrokerError('artifact source file is missing or linked') from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected['size']:
                raise HostBrokerError('artifact source file is not the expected regular file')
            data = os.read(fd, MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise HostBrokerError('artifact source file SHA-256 mismatch')
        files[rel] = data
    if any(marker not in files['src/guest/provider.mjs'] for marker in _PROVIDER_MARKERS):
        raise HostBrokerError('artifact provider contract markers are missing')
    return VerifiedArtifacts(manifest, manifest_sha256, files)


def build_broker_config(runtime: str) -> dict[str, Any]:
    """The only OpenCode Config used in Broker mode. No credentials, no providers.

    The provider is registered by the Guest plugin at startup, so ``providers``
    stays empty and every other provider is denied by policy.
    """
    plugin = plugin_dir(runtime)
    return {
        '$schema': 'https://opencode.ai/config.json',
        'model': f'{PROVIDER_ID}/{MODEL_ID}',
        'providers': {},
        'plugins': [plugin],
        'mcp': {},
        'policies': [
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': PROVIDER_ID, 'effect': 'allow'},
            {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
            {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'plugin.use', 'resource': plugin, 'effect': 'allow'},
            {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
        ],
    }


def config_bytes(runtime: str) -> bytes:
    return (json.dumps(build_broker_config(runtime), indent=2) + '\n').encode('utf-8')


def assert_broker_config(config_file: pathlib.Path, runtime: str) -> str:
    """Stop unless the file is byte-for-byte the generated Broker-only Config."""
    if config_file.is_symlink() or not config_file.is_file():
        raise HostBrokerError('generated Broker config is missing or unsafe')
    try:
        raw = config_file.read_bytes()
    except OSError:
        raise HostBrokerError('generated Broker config could not be read') from None
    if raw != config_bytes(runtime):
        raise HostBrokerError('Broker config differs from the fixed Broker-only contract')
    return hashlib.sha256(raw).hexdigest()


def broker_runtime_identity(
    selection: HostBrokerSelection,
    manifest_sha256: str,
    generator_fingerprint: str,
) -> str:
    """Runtime Identity covering artifacts, contract, mode and generator sources."""
    parts = (
        bytes.fromhex(manifest_sha256), bytes.fromhex(generator_fingerprint),
        selection.provider.encode(), selection.model.encode(), selection.mode.encode(),
        selection.url.encode(), (selection.fixture_rel or '').encode(),
        selection.sandbox_label.encode(),
    )
    digest = hashlib.sha256(_IDENTITY_NAMESPACE)
    for part in parts:
        digest.update(len(part).to_bytes(4, 'big'))
        digest.update(part)
    return digest.hexdigest()


def validate_prompt(prompt: object) -> str:
    """Non-interactive prompt only; the TUI is never started in Broker mode."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise HostBrokerError(
            'Host Broker mode is non-interactive: --host-broker-prompt is required '
            '(interactive TTY with a stdin capability handoff is not proven)')
    if ('\0' in prompt or len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES
            or _SECRET_LIKE.search(prompt)):
        raise HostBrokerError('Host Broker prompt is too large or contains secret-like text')
    return prompt


def build_guest_exec_args(
    selection: HostBrokerSelection,
    opencode_path: str,
    runtime: str,
    prompt: str,
    *,
    tty: bool = False,
) -> tuple[str, ...]:
    """Guest launcher argv (no capability). A TTY request is refused outright.

    The Guest launcher consumes stdin for the capability and gives OpenCode no
    stdin (``stdio[0] = ignore``), so an interactive TUI cannot coexist with the
    only handoff path verified for ``sbx exec -i``.
    """
    if tty:
        raise HostBrokerError(
            'interactive TTY is refused: stdin carries the capability and OpenCode gets no stdin')
    if not opencode_path.startswith('/') or opencode_path != str(pathlib.PurePosixPath(opencode_path)):
        raise HostBrokerError('OpenCode path must be a normalized absolute path')
    argv = [
        'node', launcher_path(runtime),
        '--mode=' + selection.mode,
        '--broker-url=' + selection.url,
        '--opencode=' + opencode_path,
    ]
    fixture = fixture_guest_path(selection, runtime)
    if fixture is not None:
        argv.append('--fixture-root=' + fixture)
    return (*argv, '--', 'run', '--standalone', validate_prompt(prompt))


GUEST_VERIFY_SCRIPT: Final[str] = r'''import hashlib
import json
import os
import re
import stat
import sys

ROOT = '/home/agent/workspace/oc2'
# Path as written into the Config. Identical to ROOT in the Guest; kept separate
# only so offline tests can relocate the filesystem root without editing it.
CONFIG_ROOT = '/home/agent/workspace/oc2'
MAX = 65536


def fail(message):
    print('OC2_BROKER_GUEST_STOP: ' + message, file=sys.stderr)
    raise SystemExit(1)


def open_chain(path, want_dir=True):
    parts = path.split('/')[1:]
    if not path.startswith('/') or any(p in ('', '.', '..') for p in parts):
        fail('unsafe path')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags | os.O_DIRECTORY)
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            nxt = os.open(part, flags | (os.O_DIRECTORY if (want_dir or not last) else 0),
                          dir_fd=fd)
            os.close(fd)
            fd = nxt
    except OSError:
        os.close(fd)
        fail('path is missing, linked, or not the expected type')
    return fd


def read_regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX or info.st_mode & 0o002:
        fail('not a bounded, non-writable regular file')
    data = os.read(fd, MAX + 1)
    if len(data) != info.st_size:
        fail('short read')
    return data


runtime, manifest_raw, config_sha = sys.argv[1:4]
if re.fullmatch(re.escape(ROOT) + r'/runtime/[0-9a-f]{16}', runtime) is None:
    fail('runtime path is outside the Runtime area')
manifest = json.loads(manifest_raw)
files = manifest['files']
expected_dirs = {''}
for rel in files:
    parts = rel.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        expected_dirs.add('/'.join(parts[:i]))


def walk(dir_fd, prefix, seen):
    for name in os.listdir(dir_fd):
        rel = prefix + name
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            if rel not in expected_dirs:
                fail('unexpected directory in Broker artifacts')
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=dir_fd)
            try:
                walk(child, rel + '/', seen)
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode):
            if rel not in files:
                fail('unexpected file in Broker artifacts')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
            try:
                data = read_regular(fd)
            finally:
                os.close(fd)
            entry = files[rel]
            if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                fail('Broker artifact hash mismatch')
            if rel == 'src/guest/provider.mjs' and (
                    b'export const PROVIDER_ID = "oc-cf-aig";' not in data
                    or b'export const MODEL_ID = "gpt-6-luna";' not in data):
                fail('Broker provider contract markers are missing')
            seen.add(rel)
        else:
            fail('unsupported entry type in Broker artifacts')


root_fd = open_chain(runtime + '/broker')
seen = set()
try:
    walk(root_fd, '', seen)
finally:
    os.close(root_fd)
if seen != set(files):
    fail('Broker artifact set is incomplete')

cfd = open_chain(runtime + '/config/opencode/opencode.jsonc', want_dir=False)
try:
    raw = read_regular(cfd)
finally:
    os.close(cfd)
if hashlib.sha256(raw).hexdigest() != config_sha:
    fail('Broker config hash mismatch')
config = json.loads(raw)
plugin = CONFIG_ROOT + runtime[len(ROOT):] + '/broker/src/guest'
if (config.get('providers') != {} or config.get('model') != 'oc-cf-aig/gpt-6-luna'
        or config.get('plugins') != [plugin] or config.get('mcp') != {}
        or set(config) != {'$schema', 'model', 'providers', 'plugins', 'mcp', 'policies'}):
    fail('Broker config is not the Broker-only contract')
for policy in config['policies']:
    if policy.get('effect') == 'allow' and policy.get('resource') not in ('oc-cf-aig', plugin):
        fail('Broker config allows an unexpected resource')
print('OC2_BROKER_GUEST_VERIFIED')
'''


def place_artifacts(
    runner: Any,
    sandbox: str,
    runtime: str,
    artifacts: VerifiedArtifacts,
    config_sha256: str,
    staging: pathlib.Path,
) -> None:
    """Copy only the allowlisted files into the Runtime area, then verify in the Guest.

    Existing files are reused only when their SHA-256 matches; nothing is overwritten.
    ``staging`` receives the already-verified bytes so the source is read once.
    """
    base = broker_dir(runtime)
    dirs = [base, base + '/bin', base + '/src', base + '/src/guest']
    for directory in dirs:
        if runner.directory_status(sandbox, directory) not in (0, 10):
            raise HostBrokerError('Broker artifact directory is unsafe or its state is unknown')
    runner.sbx('exec', sandbox, 'mkdir', '-p', '-m', '700', *dirs)
    for rel, data in sorted(artifacts.files.items()):
        local = staging / rel.replace('/', '__')
        local.write_bytes(data)
        local.chmod(0o600)
        destination = f'{base}/{rel}'
        status = runner.destination_status(sandbox, destination)
        if status == 0:
            runner.sbx('cp', str(local), f'{sandbox}:{destination}')
        elif status != 10:
            raise HostBrokerError('Broker artifact destination is unsafe or its state is unknown')
        output = runner.sbx('exec', sandbox, 'sha256sum', destination, capture=True).split()
        if not output or output[0] != artifacts.manifest['files'][rel]['sha256']:
            raise HostBrokerError('Broker artifact SHA-256 mismatch in the Sandbox')
    manifest_json = json.dumps(artifacts.manifest, sort_keys=True, separators=(',', ':'))
    verdict = runner.sbx(
        'exec', sandbox, 'python3', '-I', '-c', GUEST_VERIFY_SCRIPT,
        runtime, manifest_json, config_sha256, capture=True,
    )
    if VERIFIED_MARKER not in str(verdict):
        raise HostBrokerError('independent Guest verification of Broker artifacts failed')
