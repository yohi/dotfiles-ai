#!/usr/bin/env python3
"""Host-side one-command OpenCode v2 launcher using Docker Sandboxes.

Source configuration is exported from dotfiles-ai/apm.yml. No credential, MCP,
provider, or OpenCode v1 runtime files are copied. Host/workspace mounts are
not requested. Existing unrelated sandboxes are never modified.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import getpass
import hashlib
import importlib
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
from typing import TYPE_CHECKING, Final, Literal

import yaml
from oc2_oauth_bundle import oauth_helper_source

if TYPE_CHECKING:
    from sandbox.scripts.oc2_workspace import Manifest as WorkspaceManifest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERSION = '2.2.5'
ROOT = '/home/agent/workspace/oc2'
V2_CONFIG_NAME = 'opencode.jsonc'
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]$')
CF_GATEWAY_PROVIDER_ID: Final[str] = 'cloudflare-ai-gateway-custom'
CLOUDFLARE_SECRET_NAME: Final[str] = 'cloudflare-ai-gateway'
CLOUDFLARE_TOKEN_PLACEHOLDER: Final[str] = 'proxy-managed'
OPENAI_ACCESS_TOKEN_SENTINEL: Final[str] = 'oai-oat01-proxy-managed'
OPENAI_REFRESH_TOKEN_SENTINEL: Final[str] = 'oai-ort01-proxy-managed'
CLONE_SOURCE_ROOT = pathlib.Path(
    os.environ.get('XDG_STATE_HOME', str(pathlib.Path.home() / '.local' / 'state')),
) / 'oc2' / 'clone-sources'
PINNED = (
    '/home/agent/.local/oc2-runtime/node_modules/.bin/opencode',
)
RUNTIME_DIRECTORY_SETUP_SCRIPT = '''
import os, stat, sys

base = os.path.normpath(sys.argv[1])
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
paths = sys.argv[2:]
if not base.startswith('/') or '..' in base.split('/'):
    raise SystemExit('unsafe runtime root')
uid = os.geteuid()

for path in paths:
    if not path.startswith('/') or '..' in path.split('/'):
        raise SystemExit('runtime directory escaped its root')
    target = os.path.normpath(path)
    if target != base and not target.startswith(base + '/'):
        raise SystemExit('runtime directory escaped its root')
    descriptor = os.open('/', flags)
    current = ''
    try:
        for component in target.split('/')[1:]:
            current += '/' + component
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            if current == base or current.startswith(base + '/'):
                info = os.fstat(child)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
                    os.close(child)
                    raise SystemExit('runtime directory has an unsafe owner or type')
                os.fchmod(child, 0o700)
                if stat.S_IMODE(os.fstat(child).st_mode) != 0o700:
                    os.close(child)
                    raise SystemExit('runtime directory is not private')
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)
'''

GUEST_EXEC_WRAPPER = r'''import os
import re
import sys
import urllib.parse

PROXY_NAMES = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')


def stop(message):
    print('OC2_PROXY_STOP: ' + message, file=sys.stderr)
    raise SystemExit(125)


arguments = sys.argv[2:]
try:
    separator = arguments.index('--')
except ValueError:
    stop('invalid runtime wrapper arguments')
runtime_entries = arguments[:separator]
target = arguments[separator + 1:]
if not target:
    stop('missing target process')

child_environment = {}
for entry in runtime_entries:
    key, delimiter, value = entry.partition('=')
    if (not delimiter or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) is None
            or key in child_environment or key.upper() in PROXY_NAMES):
        stop('invalid fixed runtime environment')
    child_environment[key] = value

proxy_environment = {}
for name in PROXY_NAMES:
    variants = [os.environ[key] for key in (name, name.lower()) if key in os.environ]
    if len(variants) == 2 and variants[0] != variants[1]:
        stop('conflicting proxy environment variables')
    if variants:
        proxy_environment[name] = variants[0]

if 'HTTPS_PROXY' not in proxy_environment:
    stop('required HTTPS proxy configuration is missing or unsafe')
for proxy in (proxy_environment[name] for name in ('HTTP_PROXY', 'HTTPS_PROXY')
              if name in proxy_environment):
    if any(ord(character) < 32 or ord(character) == 127 for character in proxy):
        stop('unsafe proxy URL')
    try:
        parsed = urllib.parse.urlsplit(proxy)
        valid_proxy = (
            parsed.scheme in ('http', 'https')
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ('', '/')
            and not parsed.query
            and not parsed.fragment
        )
        parsed.port
    except ValueError:
        stop('unsafe proxy URL')
    if not valid_proxy:
        stop('unsafe proxy URL')

bypasses = proxy_environment.get('NO_PROXY', '')
if bypasses:
    entries = [entry.strip().lower() for entry in bypasses.split(',')]
    allowed_no_proxy = (
        'localhost', '127.0.0.1', '::1', 'gateway.docker.internal',
    )
    if any(entry not in allowed_no_proxy for entry in entries):
        stop('unsafe NO_PROXY entries')

child_environment.update(proxy_environment)
os.execvpe(target[0], target, child_environment)
'''

GUEST_EXEC_WRAPPER = r'''import os
import re
import sys
import urllib.parse

PROXY_NAMES = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')


def stop(message):
    print('OC2_PROXY_STOP: ' + message, file=sys.stderr)
    raise SystemExit(125)


arguments = sys.argv[2:]
try:
    separator = arguments.index('--')
except ValueError:
    stop('invalid runtime wrapper arguments')
runtime_entries = arguments[:separator]
target = arguments[separator + 1:]
if not target:
    stop('missing target process')

child_environment = {}
for entry in runtime_entries:
    key, delimiter, value = entry.partition('=')
    if (not delimiter or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) is None
            or key in child_environment or key.upper() in PROXY_NAMES):
        stop('invalid fixed runtime environment')
    child_environment[key] = value

proxy_environment = {}
for name in PROXY_NAMES:
    variants = [os.environ[key] for key in (name, name.lower()) if key in os.environ]
    if len(variants) == 2 and variants[0] != variants[1]:
        stop('conflicting proxy environment variables')
    if variants:
        proxy_environment[name] = variants[0]

if 'HTTPS_PROXY' not in proxy_environment:
    stop('required HTTPS proxy configuration is missing or unsafe')
for proxy in (proxy_environment[name] for name in ('HTTP_PROXY', 'HTTPS_PROXY')
              if name in proxy_environment):
    if any(ord(character) < 32 or ord(character) == 127 for character in proxy):
        stop('unsafe proxy URL')
    try:
        parsed = urllib.parse.urlsplit(proxy)
        valid_proxy = (
            parsed.scheme in ('http', 'https')
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ('', '/')
            and not parsed.query
            and not parsed.fragment
        )
        parsed.port
    except ValueError:
        stop('unsafe proxy URL')
    if not valid_proxy:
        stop('unsafe proxy URL')

bypasses = proxy_environment.get('NO_PROXY', '')
if bypasses:
    entries = [entry.strip().lower() for entry in bypasses.split(',')]
    allowed_no_proxy = (
        'localhost', '127.0.0.1', '::1', 'gateway.docker.internal',
    )
    if any(entry not in allowed_no_proxy for entry in entries):
        stop('unsafe NO_PROXY entries')

child_environment.update(proxy_environment)
os.execvpe(target[0], target, child_environment)
'''


@dataclass(frozen=True, slots=True)
class CloudflareGatewayRuntime:
    """Validated non-secret identifiers for the configured Cloudflare Gateway."""

    account_id: str
    gateway_id: str


@dataclass(frozen=True, slots=True)
class SandboxLaunch:
    name: str
    digest: str
    cli: str
    workspace: str
    config_file: pathlib.Path
    cloudflare: CloudflareGatewayRuntime | None = None


class Stop(Exception):
    pass


GENERATED_CONFIG_UNSAFE = 'generated OpenCode config is missing or unsafe'
GENERATED_CONFIG_READ_FAILED = 'generated OpenCode config could not be read'
GENERATED_CONFIG_NOT_OBJECT = 'generated OpenCode config is not an object'
GENERATED_PROVIDER_INVALID = 'generated OpenCode provider selection is invalid'


def _read_generated_config(config_file: pathlib.Path) -> dict[str, object]:
    if config_file.is_symlink() or not config_file.is_file():
        raise Stop(GENERATED_CONFIG_UNSAFE)
    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop(GENERATED_CONFIG_READ_FAILED) from exc
    if not isinstance(config, dict):
        raise Stop(GENERATED_CONFIG_NOT_OBJECT)
    return config


def credential_mixin_spec(name: str) -> bytes:
    """Serialize the proxy credential bindings without embedding credentials."""
    if re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) is None:
        raise Stop('invalid credential Mixin name')
    spec = {
        'schemaVersion': '3',
        'kind': 'mixin',
        'displayName': name,
        'capabilities': [
            {
                'type': 'com.docker.sandbox/credential@1',
                'config': {
                  'service': 'openai',
                  'phase': 'runtime',
                  'oauth': {
                    'tokenEndpoint': {
                        'host': 'auth.openai.com',
                        'path': '/oauth/token',
                    },
                    'resourceHosts': ['chatgpt.com'],
                    'sentinels': {
                        'accessToken': OPENAI_ACCESS_TOKEN_SENTINEL,
                        'refreshToken': OPENAI_REFRESH_TOKEN_SENTINEL,
                    },
                    'credentialFile': {
                        'path': '~/.local/share/opencode/auth.json',
                        'structure': {
                            'openai': {
                                'type': 'oauth',
                                'access': '{{.AccessToken}}',
                                'refresh': '{{.RefreshToken}}',
                                'expires': '{{.ExpiresAt}}',
                            },
                        },
                    },
                  },
                },
            },
            {
                'type': 'com.docker.sandbox/credential@1',
                'optional': True,
                'config': {
                  'service': 'cloudflare-ai-gateway',
                  'phase': 'runtime',
                  'apiKey': {
                    'name': 'OC_CF_API_TOKEN',
                    'proxyManaged': True,
                    'inject': [{
                        'domain': 'gateway.ai.cloudflare.com',
                        'header': 'cf-aig-authorization',
                        'format': 'Bearer %s',
                    }],
                  },
                },
            },
            {
              'type': 'com.docker.sandbox/network-policy@1',
              'config': {
                'runtime': {
                'allow': [
                    'auth.openai.com',
                    'chatgpt.com',
                    'gateway.ai.cloudflare.com',
                ],
                },
              },
            },
        ],
    }
    return b'# syntax=docker/sandbox-kit:3\n' + yaml.safe_dump(spec, sort_keys=False).encode('utf-8')


def cloudflare_gateway_runtime(
    config_file: pathlib.Path,
    account_id: str | None,
    gateway_id: str | None,
) -> CloudflareGatewayRuntime | None:
    """Return validated Cloudflare IDs when the Custom Gateway provider is selected."""
    config = _read_generated_config(config_file)
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop(GENERATED_PROVIDER_INVALID)
    if CF_GATEWAY_PROVIDER_ID not in providers:
        return None
    if not isinstance(providers[CF_GATEWAY_PROVIDER_ID], dict):
        raise Stop('generated Cloudflare provider selection is invalid')
    if (not isinstance(account_id, str)
            or re.fullmatch(r'[0-9a-fA-F]{32}', account_id) is None
            or not isinstance(gateway_id, str)
            or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', gateway_id) is None):
        raise Stop('Cloudflare runtime identifiers are missing or invalid')
    return CloudflareGatewayRuntime(account_id=account_id, gateway_id=gateway_id)


def requires_external_inference(config_file: pathlib.Path) -> bool:
    """Return whether the exported OpenCode config selects an external provider."""
    config = _read_generated_config(config_file)
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop(GENERATED_PROVIDER_INVALID)
    return bool(providers)


def _trusted_v2_config(repo: pathlib.Path) -> dict[str, object]:
    import prepare_opencode_v2 as exporter

    source = exporter._read_apm_source(repo)
    generated = exporter._build_files(
        source.shell, source.snapshot, source.source_sha256, source.v2_config,
    )
    config = json.loads(generated[V2_CONFIG_NAME])
    if not isinstance(config, dict):
        raise Stop('APM V2 config generator returned an invalid document')
    return config


def configure_cloudflare_provider(
    config_file: pathlib.Path,
    *,
    include_cloudflare: bool,
    generated_config: dict[str, object],
) -> bool:
    if _read_generated_config(config_file) != generated_config:
        raise Stop('generated OpenCode config differs from the validated APM source')
    config = copy.deepcopy(generated_config)
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop('generated OpenCode provider selection is invalid')
    cloudflare_provider = providers.get(CF_GATEWAY_PROVIDER_ID)
    if cloudflare_provider is not None and not isinstance(cloudflare_provider, dict):
        raise Stop('generated Cloudflare provider selection is invalid')
    default_model = config.get('model')
    selected_by_default = (
        isinstance(default_model, str)
        and default_model.partition('/')[0] == CF_GATEWAY_PROVIDER_ID
    )
    if include_cloudflare or selected_by_default:
        if cloudflare_provider is None:
            raise Stop('Cloudflare Gateway mode has no configured provider')
        return True
    if cloudflare_provider is None:
        return False
    policies = config.get('policies', [])
    if not isinstance(policies, list) or any(not isinstance(policy, dict) for policy in policies):
        raise Stop('generated OpenCode provider policies are invalid')
    config['providers'] = {
        provider_id: provider
        for provider_id, provider in providers.items()
        if provider_id != CF_GATEWAY_PROVIDER_ID
    }
    config['policies'] = [
        policy for policy in policies
        if policy.get('resource') != CF_GATEWAY_PROVIDER_ID
    ]
    try:
        _write_generated_config(config_file, config)
    except OSError as exc:
        raise Stop('generated OpenCode config could not be prepared') from exc
    return False


def _write_generated_config(config_file: pathlib.Path, config: dict[str, object]) -> None:
    if config_file.name != V2_CONFIG_NAME:
        raise OSError('unsafe generated config destination')
    parent_fd = os.open(
        config_file.parent,
        os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0),
    )
    try:
        parent_info = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.geteuid()
                or stat.S_IMODE(parent_info.st_mode) & 0o077):
            raise OSError('unsafe generated config directory')
        descriptor = os.open(
            config_file.name,
            os.O_WRONLY | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0),
            dir_fd=parent_fd,
        )
        try:
            file_info = os.fstat(descriptor)
            if (not stat.S_ISREG(file_info.st_mode) or file_info.st_uid != os.geteuid()
                    or file_info.st_nlink != 1):
                raise OSError('unsafe generated config file')
            with os.fdopen(descriptor, 'w', encoding='utf-8', closefd=False) as output:
                output.write(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
                output.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _cloudflare_secret_entry_scope(
    entry: object,
    sandbox_name: str,
) -> Literal['sandbox', 'global'] | None:
    expected_fields = {'name', 'scope', 'secret', 'type'}
    if not isinstance(entry, dict) or set(entry) != expected_fields:
        raise Stop('Cloudflare credential entry schema is unsupported')
    name, scope, secret_type = entry['name'], entry['scope'], entry['type']
    if (not isinstance(name, str) or not isinstance(scope, str)
            or not isinstance(entry['secret'], str) or not isinstance(secret_type, str)):
        raise Stop('Cloudflare credential entry schema is invalid')
    if name != CLOUDFLARE_SECRET_NAME:
        return None
    if secret_type != 'service':
        raise Stop('Cloudflare credential type is unexpected')
    if scope == sandbox_name:
        return 'sandbox'
    if scope in ('(global)', 'global'):
        return 'global'
    raise Stop('Cloudflare credential scope is unexpected')


def _cloudflare_secret_scope(
    listing: str,
    sandbox_name: str,
) -> Literal['sandbox', 'global'] | None:
    try:
        document = json.loads(listing)
    except json.JSONDecodeError:
        raise Stop('Cloudflare credential listing JSON is invalid') from None
    if not isinstance(document, dict) or set(document) != {'secrets'}:
        raise Stop('Cloudflare credential listing JSON schema is unsupported')
    entries = document['secrets']
    if not isinstance(entries, list):
        raise Stop('Cloudflare credential listing JSON schema is invalid')
    scopes = {
        scope for entry in entries
        if (scope := _cloudflare_secret_entry_scope(entry, sandbox_name)) is not None
    }
    if 'sandbox' in scopes:
        return 'sandbox'
    if 'global' in scopes:
        return 'global'
    return None


def _read_cloudflare_secret_scope(
    runner: Runner,
    sandbox_name: str,
    *,
    global_scope: bool,
) -> Literal['sandbox', 'global'] | None:
    command = (
        ('secret', 'ls', '--global', '--service', CLOUDFLARE_SECRET_NAME, '--json')
        if global_scope
        else ('secret', 'ls', '--sandbox', sandbox_name,
              '--service', CLOUDFLARE_SECRET_NAME, '--json')
    )
    try:
        listing = runner.sbx(*command, capture=True)
    except Stop:
        raise Stop('Cloudflare credential availability could not be checked') from None
    scope = _cloudflare_secret_scope(listing, sandbox_name)
    expected_scope = 'global' if global_scope else 'sandbox'
    if scope is not None and scope != expected_scope:
        raise Stop('Cloudflare credential listing returned an unexpected scope')
    return scope


def ensure_cloudflare_credential(
    runner: Runner,
    sandbox_name: str,
    *,
    interactive: bool,
) -> Literal['sandbox', 'global']:
    scope = _read_cloudflare_secret_scope(runner, sandbox_name, global_scope=False)
    if scope is not None:
        return scope
    scope = _read_cloudflare_secret_scope(runner, sandbox_name, global_scope=True)
    if scope == 'global':
        return scope
    if not interactive:
        raise Stop('Cloudflare credential is missing; an interactive terminal is required')
    runner.sbx('secret', 'set', CLOUDFLARE_SECRET_NAME, '--sandbox', sandbox_name, tty=True)
    scope = _read_cloudflare_secret_scope(runner, sandbox_name, global_scope=False)
    if scope != 'sandbox':
        raise Stop('Cloudflare sandbox-scoped credential was not verified')
    return scope


@dataclass(frozen=True, slots=True)
class CloneRemote:
    name: str
    fetch_urls: tuple[str, ...]
    push_urls: tuple[str, ...]


def operator_command(user: str, *args: str) -> list[str]:
    if user == getpass.getuser():
        return list(args)
    if re.fullmatch(r'[a-z_][a-z0-9_-]*', user) is None:
        raise Stop('invalid Sandbox operator user')
    sudo = shutil.which('sudo')
    if sudo is None:
        raise Stop('sudo is required to use the separate Sandbox operator account')
    return [sudo, '-i', '-u', user, '--', *args]


def run_operator(user: str, *args: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            operator_command(user, *args), check=False, text=True,
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop('Sandbox operator command could not complete') from exc
    if result.returncode != 0:
        raise Stop('Sandbox operator command failed')
    return result.stdout


class Runner:
    def __init__(self, user: str, *, dry_run: bool = False):
        self.user = user
        self.dry_run = dry_run

    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str:
        """Run an sbx command with an optional subprocess timeout."""
        command = operator_command(self.user, 'sbx', *args)
        if self.dry_run:
            print('PLAN: ' + ' '.join(command[:5]) + ' [...]')
            return ''
        try:
            result = subprocess.run(command, check=False, text=True,
                                    capture_output=capture, timeout=None if tty else timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Stop('sbx command could not complete') from exc
        if result.returncode != 0:
            raise Stop(f'sbx command failed (exit {result.returncode})')
        return result.stdout if capture else ''


def clone_create_args(
    name: str, workspace: pathlib.Path, mixin_path: pathlib.Path,
) -> list[str]:
    return [
        'create', '--clone', '--name', name, '--kit', str(mixin_path),
        'shell', str(workspace),
    ]


def _safe_clone_remotes(workspace: pathlib.Path) -> tuple[CloneRemote, ...]:
    """Return network remotes without credential-bearing URLs."""
    listed = subprocess.run(
        ['git', '-C', str(workspace), 'remote'],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if listed.returncode != 0:
        raise Stop('could not inspect Git remotes')

    remotes: list[CloneRemote] = []
    for name in listed.stdout.splitlines():
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name) is None:
            raise Stop('Git remote name is not safe to copy')
        urls: list[list[str]] = []
        for push in (False, True):
            command = ['git', '-C', str(workspace), 'remote', 'get-url', '--all']
            if push:
                command.append('--push')
            command.append(name)
            result = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=10,
            )
            if result.returncode != 0:
                raise Stop('could not inspect Git remote URLs')
            safe_urls: list[str] = []
            for url in result.stdout.splitlines():
                if _remote_url_has_credentials(url):
                    raise Stop('Git remote contains credential material')
                parsed = urllib.parse.urlsplit(url)
                network_url = parsed.scheme.lower() in {'https', 'http', 'ssh', 'git'}
                scp_url = re.fullmatch(
                    r'(?:[^@\s/:]+@)?(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9][A-Za-z0-9.-]*):[^:\s].+',
                    url,
                ) is not None
                if network_url or scp_url:
                    safe_urls.append(url)
            urls.append(safe_urls)
        if urls[0]:
            remotes.append(CloneRemote(name, tuple(urls[0]), tuple(urls[1])))
    return tuple(remotes)


def _remote_url_has_credentials(url: str) -> bool:
    """Reject credentials and query strings embedded in a remote URL."""
    if any(character.isspace() or ord(character) < 0x20 for character in url):
        return True
    parsed = urllib.parse.urlsplit(url)
    if (parsed.password is not None
            or re.search(r'[^/@\s:]+:[^/@\s]+@', url) is not None):
        return True
    if parsed.scheme.lower() in {'http', 'https'} and parsed.username is not None:
        return True
    return bool(parsed.query)


def _new_clone_source_directory(name: str) -> pathlib.Path:
    """Create a private persistent source directory for Docker's read-only mount."""
    root = CLONE_SOURCE_ROOT
    if not root.is_absolute():
        raise Stop('clone source state directory must be absolute')
    if root.is_symlink():
        raise Stop('clone source state directory must not be a symlink')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    destination = root / name
    if destination.exists() or destination.is_symlink():
        raise Stop('a retained clone source already exists for this Sandbox name')
    destination.mkdir(mode=0o700)
    return destination


def _copy_regular_workspace_file(source: str, destination: str) -> str:
    """Copy a stable regular file without following links or blocking on special files."""
    import oc2_workspace

    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(source, flags), 'rb') as source_stream:
        before = os.fstat(source_stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > oc2_workspace.MAX_FILE_BYTES:
            raise Stop('workspace changed to an unsafe file during snapshot')
        destination_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(os.open(destination, destination_flags, 0o600), 'wb') as output:
            total = 0
            while chunk := source_stream.read(1024 * 1024):
                total += len(chunk)
                if total > oc2_workspace.MAX_FILE_BYTES:
                    raise Stop('workspace file exceeds the snapshot size limit')
                _ = output.write(chunk)
        after = os.fstat(source_stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Stop('workspace file changed during snapshot')
    return destination


def _run_git(workspace: pathlib.Path, *args: str) -> None:
    """Run a Git operation without exposing its output or credential values."""
    try:
        result = subprocess.run(
            ['git', '-C', str(workspace), *args],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop('could not prepare sanitized clone workspace') from exc
    if result.returncode != 0:
        raise Stop('could not prepare sanitized clone workspace')


def install_cli_args(name: str) -> list[str]:
    return [
        'exec', name, 'npm', 'install', '--prefix', '/home/agent/.local/oc2-runtime',
        '--no-audit', '--no-fund', '--no-save', f'@opencode/cli@{VERSION}',
    ]


def export_v2_config(repo: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    script = HERE / 'prepare_opencode_v2.py'
    try:
        result = subprocess.run(
            [sys.executable, str(script), '--repo-root', str(repo), '--out', str(output)],
            check=False, capture_output=True, text=True, timeout=40,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop('APM V2 config generation could not complete') from exc
    if result.returncode != 0:
        raise Stop('APM V2 config generation failed')
    from sandbox.scripts.stage_opencode_v2 import StageError, verify_bundle

    try:
        verify_bundle(output)
    except StageError as exc:
        raise Stop('APM V2 config bundle failed verification') from exc
    config = output / 'opencode.jsonc'
    if config.is_symlink() or not config.is_file():
        raise Stop('generated V2 config is missing or unsafe')
    return config


def validate_clone_workspace(workspace: pathlib.Path) -> None:
    """Refuse Clone mode if it would expose files omitted by the safety scan."""
    oc2_workspace = importlib.import_module('oc2_workspace')

    if any((workspace / name).exists() for name in ('opencode.json', 'opencode.jsonc', 'cli.json')):
        raise Stop('workspace contains OpenCode project configuration')
    manifest = oc2_workspace.snapshot(workspace)
    checked = {entry.path for entry in manifest.files}
    exposed: set[str] = set()
    def fail_workspace_walk(error: OSError) -> None:
        """Fail closed when any workspace directory cannot be traversed."""
        raise Stop('workspace cannot be safely inspected') from error

    for current, directories, filenames in os.walk(
            workspace, followlinks=False, onerror=fail_workspace_walk):
        current_path = pathlib.Path(current)
        retained: list[str] = []
        for name in directories:
            candidate = current_path / name
            relative = candidate.relative_to(workspace).as_posix()
            if candidate.is_symlink():
                raise Stop('workspace contains a symlink')
            if name == '.git':
                if relative != '.git':
                    raise Stop('workspace contains nested Git metadata')
                continue
            retained.append(name)
        directories[:] = retained
        for name in filenames:
            if name == '.git' and (current_path / name).relative_to(workspace).as_posix() != '.git':
                raise Stop('workspace contains nested Git metadata')
        exposed.update(
            (current_path / name).relative_to(workspace).as_posix()
            for name in filenames
        )
    if exposed != checked:
        raise Stop('clone mode would expose files excluded from the safe workspace scan')
    git_metadata = workspace / '.git'
    if git_metadata.is_symlink() or not git_metadata.is_dir():
        raise Stop('Clone mode requires a real .git directory')

    def fail_walk(error: OSError) -> None:
        """Fail closed when the Git metadata traversal is incomplete."""
        raise Stop('Git metadata cannot be safely inspected') from error

    object_store = git_metadata / 'objects'
    for current, directories, filenames in os.walk(
            git_metadata, followlinks=False, onerror=fail_walk):
        current_path = pathlib.Path(current)
        for name in directories:
            if (current_path / name).is_symlink():
                raise Stop('Git metadata contains an unsafe symlink')
        for name in filenames:
            candidate = current_path / name
            if candidate.is_symlink():
                raise Stop('Git metadata contains an unsafe symlink')
            if candidate.is_relative_to(object_store):
                continue
            try:
                content = oc2_workspace._read_regular(candidate)
            except oc2_workspace.WorkspaceError as exc:
                raise Stop('Git metadata cannot be safely inspected') from exc
            if (oc2_workspace.contains_credential_material(content)
                    or re.search(rb'\b[^/@\s:]+:[^/@\s]+@', content)):
                raise Stop('Git metadata contains credential material')

    if object_store.is_dir():
        _inspect_git_objects(workspace)


def _inspect_git_objects(workspace: pathlib.Path) -> None:
    """Inspect decompressed Git object contents without scanning compressed bytes."""
    import oc2_workspace

    try:
        process = subprocess.Popen(
            ['git', '-C', str(workspace), 'cat-file', '--batch-all-objects', '--batch'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise Stop('Git objects cannot be safely inspected') from exc
    if process.stdout is None:
        process.kill()
        process.wait()
        raise Stop('Git objects cannot be safely inspected')

    with process.stdout:
        for header in iter(process.stdout.readline, b''):
            fields = header.rstrip(b'\n').split(b' ')
            if len(fields) != 3 or fields[1] not in (b'blob', b'commit', b'tag', b'tree'):
                process.kill()
                process.wait()
                raise Stop('Git object metadata is invalid')
            try:
                size = int(fields[2])
            except ValueError as exc:
                process.kill()
                process.wait()
                raise Stop('Git object metadata is invalid') from exc
            if not 0 <= size <= oc2_workspace.MAX_FILE_BYTES:
                process.kill()
                process.wait()
                raise Stop('Git object exceeds the inspection size limit')
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = process.stdout.read(min(remaining, 1024 * 1024))
                if not chunk:
                    process.kill()
                    process.wait()
                    raise Stop('Git object data is incomplete')
                chunks.append(chunk)
                remaining -= len(chunk)
            if process.stdout.read(1) != b'\n':
                process.kill()
                process.wait()
                raise Stop('Git object data is malformed')
            content = b''.join(chunks)
            if fields[1] != b'tree' and (
                    oc2_workspace.contains_credential_material(content)
                    or re.search(rb'\b[^/@\s:]+:[^/@\s]+@', content)):
                process.kill()
                process.wait()
                raise Stop('Git metadata contains credential material')
    if process.wait() != 0:
        raise Stop('Git objects cannot be safely inspected')


def is_compatible_sandbox(runner: Runner, name: str) -> bool:
    # sbx ls --format json on v0.49.2 gives identity but does not report
    # workspace/mounts. Inspect the exact named sandbox before trusting it.
    import json

    raw = runner.sbx('ls', '-q', capture=True)
    names = {line.strip() for line in raw.splitlines() if line.strip()}
    if name not in names:
        return False

    try:
        listing = json.loads(runner.sbx('ls', '--format', 'json', capture=True))
    except (TypeError, ValueError) as exc:
        raise Stop('could not parse existing Sandbox identity') from exc
    records: list[object] | None
    if isinstance(listing, list):
        records = listing
    elif isinstance(listing, dict):
        records = listing.get('sandboxes')
    else:
        records = None
    if not isinstance(records, list):
        raise Stop('could not establish existing Sandbox identity')
    matches = [row for row in records if isinstance(row, dict)
               and row.get('name') == name]
    if len(matches) != 1:
        raise Stop('could not establish existing Sandbox identity')
    row = matches[0]
    if row.get('agent') != 'shell':
        raise Stop('existing Sandbox agent is not shell')

    # Earlier CLI versions included optional workspace fields in the list.
    # If present and populated, they independently prohibit reuse.
    for field in ('workspace', 'workspaces'):
        if field in row and row[field] not in (None, '', '-', [], {}):
            raise Stop('existing Sandbox has a workspace mount; refusing reuse')

    try:
        detail = json.loads(runner.sbx('inspect', name, '--json', capture=True))
    except (TypeError, ValueError) as exc:
        raise Stop('could not parse Sandbox mount inspection') from exc
    if not isinstance(detail, dict) or detail.get('name') != name:
        raise Stop('Sandbox inspection identity mismatch; refusing reuse')
    mounts = detail.get('runtime_mounts')
    if not isinstance(mounts, list):
        raise Stop('Sandbox mount information missing or invalid; refusing reuse')
    if mounts:
        raise Stop('existing Sandbox has runtime mounts; refusing reuse')
    return True

def export_config(repo: pathlib.Path, out: pathlib.Path) -> tuple[pathlib.Path, str]:
    """Reuse existing SSOT exporter and verifier rather than copying v1 config."""
    from sandbox.scripts.stage_opencode_v2 import verify_bundle

    cmd = [sys.executable, str(HERE / 'prepare_opencode_v2.py'),
           '--repo-root', str(repo), '--out', str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise Stop('apm.yml configuration export failed; existing settings untouched')
    digest = verify_bundle(out)
    # Source export is scalar-only; files are explicitly safe for a different
    # UID to read. A dedicated temp directory is used, not the repo itself.
    out.chmod(0o755)
    for item in out.iterdir():
        if item.is_symlink() or not item.is_file():
            raise Stop('export contains non-regular files')
        item.chmod(0o644)
    return out, digest


def execute(runner: Runner, name: str, *args: str) -> None:
    runner.sbx('exec', name, *args)


def _set_acl(paths: tuple[pathlib.Path, ...], *options: str) -> None:
    setfacl = shutil.which('setfacl')
    if setfacl is None:
        raise Stop('setfacl is required for private Workspace staging')
    for offset in range(0, len(paths), 64):
        batch = paths[offset:offset + 64]
        try:
            result = subprocess.run(
                [setfacl, *options, '--', *(str(path) for path in batch)],
                check=False, capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Stop('could not set private Workspace ACL') from exc
        if result.returncode != 0:
            raise Stop('could not set private Workspace ACL')


def grant_snapshot_access(snapshot: pathlib.Path, operator: str) -> None:
    if operator == getpass.getuser():
        return
    if re.fullmatch(r'[a-z_][a-z0-9_-]*', operator) is None:
        raise Stop('invalid Sandbox operator user')
    _set_acl((snapshot,), '-R', '-m', f'u:{operator}:r--')
    directories = [snapshot]

    def fail_walk(error: OSError) -> None:
        raise Stop('could not inspect private Workspace staging') from error

    for current, children, _ in os.walk(snapshot, followlinks=False, onerror=fail_walk):
        for name in children:
            child = pathlib.Path(current) / name
            if child.is_symlink():
                raise Stop('Workspace staging unexpectedly contains a symlink')
            directories.append(child)
    for offset in range(0, len(directories), 64):
        _set_acl(tuple(directories[offset:offset + 64]), '-m', f'u:{operator}:r-x')


def grant_collection_directory_access(directory: pathlib.Path, operator: str) -> None:
    """Grant an operator traversal through private parents and access to staging."""
    if operator == getpass.getuser():
        return
    if re.fullmatch(r'[a-z_][a-z0-9_-]*', operator) is None:
        raise Stop('invalid Sandbox operator user')
    _set_acl((directory.parent, directory.parent.parent),
             '-m', f'u:{operator}:--x')
    _set_acl((directory,), '-m', f'u:{operator}:rwx')


def grant_collected_workspace_access(incoming: pathlib.Path, operator: str,
                                    host_user: str) -> None:
    if operator == host_user:
        return
    if re.fullmatch(r'[a-z_][a-z0-9_-]*', host_user) is None:
        raise Stop('invalid Host user for collection ACL')
    setfacl = shutil.which('setfacl')
    find = shutil.which('find')
    if setfacl is None or find is None:
        raise Stop('setfacl and find are required for private change collection')
    run_operator(operator, setfacl, '-m', f'u:{host_user}:r-x', '--', str(incoming))
    run_operator(
        operator, find, str(incoming), '-type', 'd', '-exec', setfacl, '-m',
        f'u:{host_user}:r-x', '--', '{}', '+',
    )
    run_operator(
        operator, find, str(incoming), '-type', 'f', '-exec', setfacl, '-m',
        f'u:{host_user}:r--', '--', '{}', '+',
    )


def transfer_workspace(runner: Runner, name: str, snapshot: pathlib.Path,
                       manifest: WorkspaceManifest, operator: str) -> str:
    oc2_workspace = importlib.import_module('oc2_workspace')

    if not isinstance(manifest, oc2_workspace.Manifest):
        raise Stop('invalid workspace manifest')
    parent = f'{ROOT}/projects'
    destination = parent + '/' + secrets.token_hex(16)
    execute(runner, name, 'mkdir', '-p', parent)
    state = runner.sbx(
        'exec', name, 'bash', '-c',
        f'if test -e {shlex.quote(destination)} || test -L {shlex.quote(destination)}; '
        'then echo exists; else echo missing; fi', capture=True,
    ).strip()
    if state != 'missing':
        raise Stop('workspace destination already exists or could not be checked')
    checked = snapshot.parent / (snapshot.name + '-verified')
    oc2_workspace.materialize(pathlib.Path(manifest.root), checked, manifest, for_guest=True)
    if snapshot.exists():
        shutil.rmtree(snapshot)
    checked.rename(snapshot)
    grant_snapshot_access(snapshot, operator)
    runner.sbx('cp', str(snapshot), f'{name}:{destination}')
    execute(runner, name, 'chmod', '-R', 'u+rwX', destination)
    for entry in manifest.files:
        remote_file = destination + '/' + entry.path
        result = runner.sbx('exec', name, 'sha256sum', remote_file, capture=True).split()
        if not result or result[0] != entry.sha256:
            raise Stop('workspace transfer checksum mismatch')
    return destination


def stage(runner: Runner, name: str, bundle: pathlib.Path, manifest_sha: str,
          guest_script: pathlib.Path, assets_file: pathlib.Path | None = None,
          assets_sha: str | None = None) -> None:
    destination = f'{ROOT}/bundles/{manifest_sha[:16]}'
    script_sha = hashlib.sha256(guest_script.read_bytes()).hexdigest()
    script_dest = f'{ROOT}/scripts/oc2_guest_{script_sha[:16]}.py'
    # sbx exec v0.49.2 was observed invoking bash -c without the expected
    # trailing positional parameters. Use direct argv for filesystem operations.
    execute(runner, name, 'mkdir', '-p', ROOT, f'{ROOT}/bundles', f'{ROOT}/scripts')
    execute(runner, name, 'chmod', '700', ROOT, f'{ROOT}/bundles', f'{ROOT}/scripts')
    # Never overwrite an existing bundle or bootstrap script. Reuse is allowed
    # only after the guest validates their content and hash.
    exists = runner.sbx('exec', name, 'bash', '-c',
                        f'if test -e {shlex.quote(destination)}; then echo exists; else echo missing; fi',
                        capture=True).strip()
    if exists == 'missing':
        runner.sbx('cp', str(bundle), f'{name}:{destination}')
    elif exists != 'exists':
        raise Stop('cannot determine remote bundle state')
    script_exists = runner.sbx('exec', name, 'bash', '-c',
                               f'if test -e {shlex.quote(script_dest)}; then echo exists; else echo missing; fi',
                               capture=True).strip()
    if script_exists == 'missing':
        runner.sbx('cp', str(guest_script), f'{name}:{script_dest}')
    elif script_exists != 'exists':
        raise Stop('cannot determine remote bootstrap script state')
    remote_sha = runner.sbx('exec', name, 'sha256sum', script_dest, capture=True).split()[0]
    if remote_sha != script_sha:
        raise Stop('guest bootstrap code SHA mismatch')
    args = ['--bundle', destination, '--expected-sha', manifest_sha]
    if (assets_file is None) != (assets_sha is None):
        raise Stop('asset file and hash must be supplied together')
    if assets_file is not None and assets_sha is not None:
        if re.fullmatch(r'[0-9a-f]{64}', assets_sha) is None:
            raise Stop('invalid asset hash')
        remote_assets = f'{ROOT}/assets/{assets_sha[:16]}.json'
        execute(runner, name, 'mkdir', '-p', f'{ROOT}/assets')
        check = runner.sbx('exec', name, 'bash', '-c',
                           f'if test -e {shlex.quote(remote_assets)}; then echo exists; else echo missing; fi',
                           capture=True).strip()
        if check == 'missing':
            runner.sbx('cp', str(assets_file), f'{name}:{remote_assets}')
        elif check != 'exists':
            raise Stop('cannot establish guest asset state')
        actual = runner.sbx('exec', name, 'sha256sum',
                            remote_assets, capture=True).split()[0]
        if actual != assets_sha:
            raise Stop('guest asset bundle SHA mismatch')
        args.extend(['--assets', remote_assets, '--expected-assets-sha', assets_sha])
    execute(runner, name, 'python3', script_dest, *args)


def cli_path(runner: Runner, name: str) -> str | None:
    for candidate in PINNED:
        result = runner.sbx(
            'exec', name, 'sh', '-c',
            'if test -x "$1"; then "$1" --version; fi',
            'oc2-version-probe', candidate, capture=True,
        ).strip()
        if result in (VERSION, 'v' + VERSION, 'opencode v' + VERSION):
            return candidate
    return None


def seed_cli(runner: Runner, name: str, source: str) -> str | None:
    """Copy only a verified CLI package tree from a separate mountless PoC.

    This avoids changing network policy. Neither credentials nor XDG data are
    read from the source Sandbox. No existing target installation is overwritten.
    """
    if not source or source == name:
        return None
    if not is_compatible_sandbox(runner, source):
        return None
    binary = PINNED[0]
    source_modules = '/home/agent/.local/opencode-v2/node_modules'
    source_binary = source_modules + '/.bin/opencode'
    target_modules = str(pathlib.PurePosixPath(binary).parent.parent)
    quoted = shlex.quote(source_binary)
    version = runner.sbx('exec', source, 'bash', '-c',
                         f'if test -x {quoted}; then {quoted} --version; fi',
                         capture=True).strip()
    if version not in (VERSION, 'v' + VERSION, 'opencode v' + VERSION):
        return None
    # sbx cp runs as sbx-poc, not the Host repo owner. Give it a private
    # temporary directory owned by the operator instead of chmod 0777 on the
    # Host-owned export directory.
    operator = ([] if runner.user == getpass.getuser()
                else ['sudo', '-i', '-u', runner.user, '--'])
    try:
        created = subprocess.run(
            [*operator, 'sh', '-c', 'umask 077; mktemp -d "$HOME/.oc2-seed-XXXXXXXX"'],
            capture_output=True, text=True, timeout=15, check=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise Stop('could not create private Sandbox operator staging directory') from exc
    staging = created.stdout.strip()
    if re.fullmatch(r'/(?:[^/]+/)+\.oc2-seed-[A-Za-z0-9]{8}', staging) is None:
        raise Stop('unsafe seed staging path')
    local = pathlib.Path(staging) / 'node_modules'
    try:
        print('OC2: seeding pinned CLI from read-only PoC sandbox ' + source)
        runner.sbx('cp', f'{source}:{source_modules}', str(local))
        runner.sbx('exec', name, 'bash', '-c',
                   f'set -eu; mkdir -p {shlex.quote(str(pathlib.PurePosixPath(target_modules).parent))}; '
                   f'test ! -e {shlex.quote(target_modules)}')
        runner.sbx('cp', str(local), f'{name}:{target_modules}')
        if cli_path(runner, name) != binary:
            raise Stop(f'seeded OpenCode CLI did not verify as v{VERSION}')
        return binary
    finally:
        subprocess.run([*operator, 'rm', '-rf', '--', staging],
                       capture_output=True, timeout=30, check=False)


def provision_cli(runner: Runner, name: str) -> str:
    found = cli_path(runner, name)
    if found:
        return found
    print(f'OC2: installing @opencode/cli@{VERSION} inside the new Sandbox.')
    runner.sbx(*install_cli_args(name), timeout=900)
    found = cli_path(runner, name)
    if not found:
        raise Stop(f'installed CLI is not the pinned v{VERSION}')
    return found


def _runtime_directory_setup_command(root: str, runtime: str) -> list[str]:
    root_path = pathlib.PurePosixPath(root)
    runtime_path = pathlib.PurePosixPath(runtime)
    if (not root_path.is_absolute() or '..' in root_path.parts
            or runtime_path.parent != root_path / 'runtime'
            or re.fullmatch(r'[0-9a-f]{16}', runtime_path.name) is None):
        raise Stop('invalid private runtime directory')

    directories = (
        root, root + '/runtime', runtime, runtime + '/home',
        runtime + '/home/.local/share', runtime + '/home/.local/share/opencode',
        runtime + '/config', runtime + '/config/opencode', runtime + '/state',
        runtime + '/cache', runtime + '/tmp',
    )
    return ['python3', '-c', RUNTIME_DIRECTORY_SETUP_SCRIPT, root, *directories]


def launch(runner: Runner, request: SandboxLaunch) -> None:
    # Use sbx exec's native --workdir and direct argv instead of bash -c
    # positional parameters. The configured runtime is fully sandbox-local.
    if re.fullmatch(r'[0-9a-f]{64}', request.digest) is None:
        raise Stop('invalid runtime digest')
    if request.cli not in PINNED:
        raise Stop('unapproved OpenCode executable path')
    runtime = f'{ROOT}/runtime/{request.digest[:16]}'
    workdir = request.workspace
    workspace_path = pathlib.PurePosixPath(workdir)
    if not workspace_path.is_absolute() or '..' in workspace_path.parts:
        raise Stop('workspace path is not a safe absolute path')
    config_dir = f'{runtime}/config/opencode'
    cloudflare_environment = (
        () if request.cloudflare is None else (
            f'OC_CF_ACCOUNT_ID={request.cloudflare.account_id}',
            f'OC_CF_GATEWAY_ID={request.cloudflare.gateway_id}',
            f'OC_CF_API_TOKEN={CLOUDFLARE_TOKEN_PLACEHOLDER}',
        )
    )
    runner.sbx(
        'exec', request.name,
        *_runtime_directory_setup_command(ROOT, runtime),
    )
    runner.sbx(
        'cp', str(request.config_file),
        f'{request.name}:{config_dir}/opencode.jsonc',
    )
    runtime_environment = (
        f'HOME={runtime}/home',
        'USER=agent',
        'SHELL=/bin/bash',
        'PATH=/usr/local/bin:/usr/bin:/bin',
        'TERM=xterm-256color',
        'LANG=C.UTF-8',
        f'XDG_CONFIG_HOME={runtime}/config',
        f'XDG_DATA_HOME={runtime}/home/.local/share',
        f'OPENCODE_DB={runtime}/home/.local/share/opencode/oc2.db',
        f'XDG_STATE_HOME={runtime}/state',
        f'XDG_CACHE_HOME={runtime}/cache',
        f'TMPDIR={runtime}/tmp',
        'OPENCODE_WATCHDOG_ENABLED=false',
        'OPENCODE_CONFIG_PROJECT_DISABLE=1',
        'OPENCODE_DISABLE_AUTOUPDATE=1',
        'OPENCODE_DISABLE_MODELS_FETCH=1',
        *cloudflare_environment,
    )
    helper = oauth_helper_source(HERE)
    runner.sbx(
        'exec', '-w', workdir, request.name, 'python3', '-c', GUEST_EXEC_WRAPPER,
        '--', *runtime_environment, '--', 'python3', '-c', helper,
        request.cli, 'oc2_oauth.py',
    )
    runner.sbx(
        'exec', '-it', '-w', workdir, request.name,
        'python3', '-c', GUEST_EXEC_WRAPPER, '--',
        *runtime_environment, '--', request.cli, '--standalone', tty=True,
    )


def _session_action(args: argparse.Namespace, workspace: pathlib.Path,
                    state_root: pathlib.Path, *, collect: bool) -> int:
    sessions = importlib.import_module('oc2_session')
    workspaces = importlib.import_module('oc2_workspace')

    session = sessions.load(state_root, workspace)
    if session.sandbox != args.sandbox:
        raise Stop('requested Sandbox does not match the saved transfer receipt')
    if session.applied:
        raise Stop('this OC2 transfer has already been applied')
    if collect:
        if session.collected:
            raise Stop('changes have already been collected for this transfer')
        runner = Runner(args.sbx_user)
        if not is_compatible_sandbox(runner, session.sandbox):
            raise Stop('the recorded Sandbox no longer exists')
        collected = session.directory / 'collected'
        if collected.exists() or collected.is_symlink():
            raise Stop('collection destination already exists')
        staging = session.directory / 'collecting'
        staging.mkdir(mode=0o700)
        try:
            incoming = staging / 'incoming'
            grant_collection_directory_access(staging, args.sbx_user)
            try:
                runner.sbx('cp', f'{session.sandbox}:{session.remote}', str(incoming))
                grant_collected_workspace_access(
                    incoming, args.sbx_user, getpass.getuser(),
                )
                candidate = workspaces.snapshot(incoming)
                workspaces.materialize(incoming, collected, candidate)
            finally:
                if incoming.exists() or incoming.is_symlink():
                    run_operator(args.sbx_user, 'rm', '-rf', '--', str(incoming))
        except BaseException:
            if collected.exists() and not collected.is_symlink():
                shutil.rmtree(collected, ignore_errors=True)
            raise
        finally:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging)
        before = {item.path: item for item in session.manifest.files}
        after = {item.path: item for item in candidate.files}
        for relative in sorted(before.keys() | after.keys()):
            if relative not in before:
                status = 'ADDED'
            elif relative not in after:
                status = 'DELETED'
            elif before[relative] != after[relative]:
                status = 'MODIFIED'
            else:
                continue
            print(f'{status}: {relative}')
        sessions.update(session, collected=True)
        print('COLLECTED_FOR_REVIEW: ' + str(collected))
        return 0

    if not session.collected:
        raise Stop('run --collect before --apply')
    collected = session.directory / 'collected'
    changed = workspaces.apply_changes(
        workspace, collected, session.manifest, approved=True,
        allow_deletions=args.allow_deletions,
    )
    sessions.update(session, applied=True)
    print('APPLIED: ' + str(len(changed)) + ' reviewed paths')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=f'oc2 launcher 1.0; OpenCode v{VERSION}')
    p.add_argument('--repo-root', type=pathlib.Path, default=REPO_ROOT)
    p.add_argument('--workspace', type=pathlib.Path, default=pathlib.Path.cwd(),
                   help='host project directory (default: current directory)')
    p.add_argument('--sandbox', default='oc2-v2')
    p.add_argument('--dry-run', action='store_true', help='show planned actions without calling sbx')
    p.add_argument('--prepare-only', action='store_true',
                   help='export and verify APM config without Sandbox commands')
    p.add_argument('--allow-paid-inference', action='store_true',
                   help='authorize external inference for this interactive launch')
    p.add_argument('--use-cloudflare-ai-gateway', action='store_true',
                   help='enable Cloudflare AI Gateway and provision its Sandbox credential')
    args = p.parse_args(argv)
    oc2_workspace = importlib.import_module('oc2_workspace')

    try:
        if args.dry_run:
            workspace = args.workspace.resolve(strict=True)
            if not workspace.is_dir():
                raise Stop('workspace is not a directory')
            if not NAME_RE.fullmatch(args.sandbox):
                raise Stop('invalid Sandbox name')
            print('OC2 PLAN: clone-mode shell Sandbox=' + args.sandbox)
            print('OC2 PLAN: workspace=' + str(workspace))
            print(f'OC2 PLAN: install and verify @opencode/cli@{VERSION} inside the Sandbox')
            print('OC2 PLAN: no credentials, provider settings, MCP, plugins, or host config')
            print('OC2 PLAN: no Sandbox commands executed')
            return 0
        repo = args.repo_root.resolve(strict=True)
        if not (repo / 'apm.yml').is_file():
            raise Stop('dotfiles-ai apm.yml not found')
        if args.prepare_only:
            with tempfile.TemporaryDirectory(prefix='oc2-v2-config-') as temporary:
                export_v2_config(repo, pathlib.Path(temporary) / 'export')
            print('OC2_PREPARED_ONLY: APM V2 config verified; no Sandbox commands executed')
            return 0

        workspace = args.workspace
        if workspace.is_symlink():
            raise Stop('workspace root must not be a symlink')
        workspace = workspace.resolve(strict=True)
        if not workspace.is_dir():
            raise Stop('workspace is not a directory')
        if not NAME_RE.fullmatch(args.sandbox):
            raise Stop('invalid Sandbox name')
        validate_clone_workspace(workspace)
        git_root = subprocess.run(
            ['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if git_root.returncode != 0 or pathlib.Path(git_root.stdout.strip()) != workspace:
            raise Stop('workspace must be the root of a Git repository for Clone mode')
        clone_remotes = _safe_clone_remotes(workspace)
        with tempfile.TemporaryDirectory(prefix='oc2-v2-config-') as temporary:
            temporary_path = pathlib.Path(temporary)
            config_file = export_v2_config(repo, temporary_path / 'export')
            configure_cloudflare_provider(
                config_file,
                include_cloudflare=args.use_cloudflare_ai_gateway,
                generated_config=_trusted_v2_config(repo),
            )
            if (requires_external_inference(config_file)
                    and not args.allow_paid_inference):
                raise Stop('external inference requires --allow-paid-inference')
            cloudflare = cloudflare_gateway_runtime(
                config_file,
                os.environ.get('OC_CF_ACCOUNT_ID'),
                os.environ.get('OC_CF_GATEWAY_ID'),
            )
            if not shutil.which('sbx'):
                raise Stop('Docker Sandboxes CLI was not found')
            runner = Runner(getpass.getuser())
            sandbox_version = runner.sbx('version', capture=True).strip()
            if re.search(r'\bv\d+\.\d+\.\d+\b', sandbox_version) is None:
                raise Stop('could not verify Docker Sandboxes version')
            create_help = runner.sbx('create', '--help', capture=True)
            if '--clone' not in create_help:
                raise Stop('installed Docker Sandboxes CLI does not support Clone mode')
            if '--kit' not in create_help:
                raise Stop('installed Docker Sandboxes CLI does not support credential Mixins')
            print('OC2_DOCKER_SANDBOXES: ' + sandbox_version)
            existing = {line.strip() for line in runner.sbx('ls', '-q', capture=True).splitlines()}
            if args.sandbox in existing:
                raise Stop('Sandbox name already exists; refusing to reuse or rebuild it')
            clone_source_directory = _new_clone_source_directory(args.sandbox)
            retained_source = False
            try:
                def ignore_source_git(directory: str, names: list[str]) -> set[str]:
                    """Omit source metadata while retaining nested Git paths for rejection."""
                    return ({'.git'} if pathlib.Path(directory) == workspace and '.git' in names
                            else set())

                clone_workspace = clone_source_directory / 'workspace'
                shutil.copytree(workspace, clone_workspace, symlinks=True,
                                copy_function=_copy_regular_workspace_file,
                                ignore=ignore_source_git)
                _run_git(clone_workspace, 'init', '--quiet', '--template=')
                validate_clone_workspace(clone_workspace)
                _run_git(clone_workspace, 'add', '--all', '--force')
                _run_git(
                    clone_workspace,
                    '-c', 'user.name=OC2 Sanitized Workspace',
                    '-c', 'user.email=oc2-snapshot@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                    'commit', '--quiet', '--allow-empty',
                    '-m', 'OC2 sanitized workspace snapshot',
                )
                for remote in clone_remotes:
                    _run_git(clone_workspace, 'remote', 'add', remote.name, remote.fetch_urls[0])
                    for url in remote.fetch_urls[1:]:
                        _run_git(clone_workspace, 'remote', 'set-url', '--add', remote.name, url)
                    for url in remote.push_urls:
                        _run_git(
                            clone_workspace, 'remote', 'set-url', '--add', '--push',
                            remote.name, url,
                        )
                validate_clone_workspace(clone_workspace)
                git_root = subprocess.run(
                    ['git', '-C', str(clone_workspace), 'rev-parse', '--show-toplevel'],
                    capture_output=True, text=True, check=False, timeout=10,
                )
                if (git_root.returncode != 0
                        or pathlib.Path(git_root.stdout.strip()) != clone_workspace):
                    raise Stop('workspace must be the root of a Git repository for Clone mode')
                print('OC2: creating clone-mode shell Sandbox ' + args.sandbox)
                mixin_name = 'oc2-credentials-' + secrets.token_hex(6)
                with tempfile.TemporaryDirectory(prefix='oc2-credential-mixin-') as mixin_temporary:
                    mixin_path = pathlib.Path(mixin_temporary)
                    mixin_spec_path = mixin_path / 'spec.yaml'
                    mixin_spec_path.write_bytes(credential_mixin_spec(mixin_name))
                    os.chmod(mixin_spec_path, 0o600)
                    retained_source = True
                    print('OC2_CLONE_SOURCE: ' + str(clone_source_directory))
                    runner.sbx(*clone_create_args(args.sandbox, clone_workspace, mixin_path))
            finally:
                if not retained_source:
                    shutil.rmtree(clone_source_directory, ignore_errors=True)
            if cloudflare is not None:
                credential_scope = ensure_cloudflare_credential(
                    runner,
                    args.sandbox,
                    interactive=sys.stdin.isatty(),
                )
                print('OC2_CLOUDFLARE_CREDENTIAL: available (' + credential_scope + ' scope)')
            cli = provision_cli(runner, args.sandbox)
            workdir = runner.sbx('exec', args.sandbox, 'pwd', capture=True).strip()
            if not workdir.startswith('/') or '..' in pathlib.PurePosixPath(workdir).parts:
                raise Stop('Sandbox returned an unsafe clone working directory')
            clone_root = runner.sbx(
                'exec', args.sandbox, 'git', '-C', workdir,
                'rev-parse', '--show-toplevel', capture=True,
            ).strip()
            if clone_root != workdir:
                raise Stop('Sandbox working directory is not the Clone-mode Git root')
            runtime_sha = hashlib.sha256(
                (str(workspace) + '\0' + VERSION).encode(),
            ).hexdigest()
            print(f'OC2_READY: sandbox={args.sandbox} opencode=v{VERSION}')
            launch(
                runner,
                SandboxLaunch(args.sandbox, runtime_sha, cli, workdir, config_file, cloudflare),
            )
            return 0
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired,
            oc2_workspace.WorkspaceError) as exc:
        print('OC2_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
