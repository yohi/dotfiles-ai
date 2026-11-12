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
import platform
import re
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
from typing import TYPE_CHECKING, Final, Literal

import yaml
from oc2_oauth_bundle import oauth_helper_source
from oc2_workspace import DOTFILES_AI_PROFILE

if TYPE_CHECKING:
    from sandbox.scripts.oc2_workspace import Manifest as WorkspaceManifest
    from sandbox.scripts.oc2_workspace import WorkspaceProfile

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERSION = '2.2.5'
ROOT = '/home/agent/workspace/oc2'
V2_CONFIG_NAME = 'opencode.jsonc'
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]$')
CLI_ASSET_NAME: Final[str] = 'opencode-linux-x64.tar.gz'
CLI_ASSET_URL: Final[str] = (
    'https://github.com/anomalyco/opencode/releases/download/v2.2.5/' + CLI_ASSET_NAME
)
CLI_RELEASE_API_URL: Final[str] = (
    'https://api.github.com/repos/anomalyco/opencode/releases/tags/v2.2.5'
)
CLI_ASSET_SHA256: Final[str] = (
    '09f44302c10fd036912f59c81fd1aef5df45dd06f649197f9dfc9bbe2a79614e'
)
MAX_CLI_ASSET_BYTES: Final[int] = 150 * 1024 * 1024
CF_GATEWAY_PROVIDER_ID: Final[str] = 'cloudflare-ai-gateway-custom'
CLOUDFLARE_SECRET_NAME: Final[str] = 'cloudflare-ai-gateway'
CLOUDFLARE_TOKEN_PLACEHOLDER: Final[str] = 'proxy-managed'
OPENAI_ACCESS_TOKEN_SENTINEL: Final[str] = 'oai-oat01-proxy-managed'
OPENAI_REFRESH_TOKEN_SENTINEL: Final[str] = 'oai-ort01-proxy-managed'
CLONE_SOURCE_ROOT = pathlib.Path(
    os.environ.get('XDG_STATE_HOME', str(pathlib.Path.home() / '.local' / 'state')),
) / 'oc2' / 'clone-sources'
PINNED = (
    '/home/agent/.local/oc2-runtime/opencode',
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


@dataclass(frozen=True, slots=True)
class CliReleaseAsset:
    version: str
    url: str
    size: int
    sha256: str


class Stop(Exception):
    pass


def _parse_cli_release_asset(raw: bytes) -> CliReleaseAsset:
    """Parse GitHub release metadata and accept only the pinned Linux x64 asset."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop('OpenCode release metadata is invalid') from exc
    if (not isinstance(payload, dict) or payload.get('tag_name') != 'v' + VERSION
            or payload.get('immutable') is not True):
        raise Stop('OpenCode release metadata tag is not approved')
    assets = payload.get('assets')
    if not isinstance(assets, list):
        raise Stop('OpenCode release metadata asset list is invalid')
    matches = [item for item in assets
               if isinstance(item, dict) and item.get('name') == CLI_ASSET_NAME]
    if len(matches) != 1:
        raise Stop('OpenCode release metadata asset is missing or duplicated')
    asset = matches[0]
    size = asset.get('size')
    digest = asset.get('digest')
    url = asset.get('browser_download_url')
    if (type(size) is not int or not 0 < size <= MAX_CLI_ASSET_BYTES
            or digest != 'sha256:' + CLI_ASSET_SHA256 or url != CLI_ASSET_URL):
        raise Stop('OpenCode release asset metadata does not match the pinned asset')
    return CliReleaseAsset(VERSION, CLI_ASSET_URL, size, CLI_ASSET_SHA256)


def download_cli_binary(directory: pathlib.Path) -> pathlib.Path:
    """Fetch and verify the pinned standalone CLI in a private Host directory."""
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise Stop('the pinned OpenCode asset supports Linux x64 Hosts only')
    if directory.is_symlink() or not directory.is_dir():
        raise Stop('OpenCode asset destination is not a private directory')
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise Stop('OpenCode asset destination is not private')
    try:
        import httpx2
    except ImportError as exc:
        raise Stop('httpx2 is required to download the pinned OpenCode release') from exc
    try:
        transport = httpx2.HTTPTransport(
            http2=True,
            retries=3,
            limits=httpx2.Limits(
                max_connections=4, max_keepalive_connections=2, keepalive_expiry=30.0,
            ),
            socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
        )
        timeout = httpx2.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
        archive_path = directory / CLI_ASSET_NAME
        binary_path = directory / 'opencode'
        digest = hashlib.sha256()
        total = 0
        with httpx2.Client(
                transport=transport, timeout=timeout, follow_redirects=True) as client:
            metadata_response = client.get(
                CLI_RELEASE_API_URL,
                headers={'Accept': 'application/vnd.github+json',
                         'X-GitHub-Api-Version': '2022-11-28'},
            )
            metadata_response.raise_for_status()
            if len(metadata_response.content) > 4 * 1024 * 1024:
                raise Stop('OpenCode release metadata exceeds the size limit')
            asset = _parse_cli_release_asset(metadata_response.content)
            with client.stream('GET', asset.url) as response:
                response.raise_for_status()
                content_length = response.headers.get('content-length')
                if content_length is not None and content_length != str(asset.size):
                    raise Stop('OpenCode asset size differs from release metadata')
                with archive_path.open('xb') as archive:
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > asset.size or total > MAX_CLI_ASSET_BYTES:
                            raise Stop('OpenCode asset exceeds its declared size')
                        digest.update(chunk)
                        archive.write(chunk)
                    archive.flush()
                    os.fsync(archive.fileno())
        if total != asset.size or digest.hexdigest() != asset.sha256:
            raise Stop('OpenCode asset size or SHA-256 does not match the release')
        _extract_cli_binary(archive_path, binary_path)
        version = subprocess.run(
            [str(binary_path), '--version'], capture_output=True, text=True,
            check=False, timeout=30,
        )
        if (version.returncode != 0 or version.stdout.strip() not in
                (VERSION, 'v' + VERSION, 'opencode v' + VERSION)):
            raise Stop('Host OpenCode binary did not verify at the pinned version')
        return binary_path
    except httpx2.HTTPError as exc:
        raise Stop('OpenCode release download failed') from exc
    except (OSError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        raise Stop('OpenCode release asset could not be prepared safely') from exc


def _extract_cli_binary(archive_path: pathlib.Path, binary_path: pathlib.Path) -> None:
    """Extract exactly one regular opencode executable without trusting archive paths."""
    with tarfile.open(archive_path, mode='r:gz') as archive:
        members = archive.getmembers()
        for member in members:
            member_path = pathlib.PurePosixPath(member.name)
            if (member_path.is_absolute() or '..' in member_path.parts
                    or not (member.isfile() or member.isdir())):
                raise Stop('OpenCode archive contains an unsafe member')
        binaries = [member for member in members
                    if member.isfile() and pathlib.PurePosixPath(member.name).name == 'opencode']
        if len(binaries) != 1 or binaries[0].size > 300 * 1024 * 1024:
            raise Stop('OpenCode archive does not contain one approved executable')
        stream = archive.extractfile(binaries[0])
        if stream is None:
            raise Stop('OpenCode executable could not be read from the archive')
        descriptor = os.open(
            binary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
            0o700,
        )
        with stream, os.fdopen(descriptor, 'wb') as executable:
            shutil.copyfileobj(stream, executable, 1024 * 1024)
            executable.flush()
            os.fsync(executable.fileno())


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
    rendered = yaml.safe_dump(spec, sort_keys=False)
    if not isinstance(rendered, str):
        raise Stop('credential Mixin specification could not be serialized')
    return b'# syntax=docker/sandbox-kit:3\n' + rendered.encode('utf-8')


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
    """Keep Cloudflare selected only when requested or used as the default model."""
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
    """Accept the named service credential only in this Sandbox or global scope."""
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
    """Prefer Sandbox then global credentials; create and verify a Sandbox credential interactively."""
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


def workspace_create_args(name: str, mixin_path: pathlib.Path) -> list[str]:
    """Create a new shell Sandbox with its credential Mixin and no Host workspace mount."""
    return ['create', '--name', name, '--kit', str(mixin_path), 'shell']


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


def _workspace_profile(workspace: pathlib.Path) -> WorkspaceProfile | None:
    """Select R1 only when origin identifies the exact yohi/dotfiles-ai repository."""
    result = subprocess.run(
        ['git', '-C', str(workspace), 'remote', 'get-url', 'origin'],
        capture_output=True, text=True, check=False, timeout=10,
    )
    remote = result.stdout.strip()
    if result.returncode == 0 and re.fullmatch(
        r'(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)'
        r'yohi/dotfiles-ai(?:\.git)?', remote, re.IGNORECASE,
    ):
        selected_profile: WorkspaceProfile = DOTFILES_AI_PROFILE
        return selected_profile
    return None


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
        verify_bundle(output, trusted_root=output.parent)
    except StageError as exc:
        raise Stop('APM V2 config bundle failed verification') from exc
    config = output / V2_CONFIG_NAME
    if config.is_symlink() or not config.is_file():
        raise Stop('generated V2 config is missing or unsafe')
    return config


def validate_clone_workspace(
    workspace: pathlib.Path,
    *,
    profile: WorkspaceProfile | None = None,
    manifest: WorkspaceManifest | None = None,
) -> None:
    """Reject unsafe Git metadata and files omitted by the selected transfer scan."""
    oc2_workspace = importlib.import_module('oc2_workspace')

    if any((workspace / name).exists()
           for name in ('opencode.json', V2_CONFIG_NAME, 'cli.json')):
        raise Stop('workspace contains OpenCode project configuration')
    manifest = manifest or oc2_workspace.snapshot(workspace, profile=profile)
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
            candidate = current_path / name
            relative_path = pathlib.PurePosixPath(
                candidate.relative_to(workspace).as_posix(),
            )
            if name == '.git' and relative_path.as_posix() != '.git':
                raise Stop('workspace contains nested Git metadata')
            if candidate.is_symlink():
                raise Stop('workspace contains a symlink')
            if oc2_workspace._excluded(relative_path, manifest.profile):
                try:
                    excluded_content = oc2_workspace._read_regular(candidate)
                except oc2_workspace.WorkspaceError as exc:
                    raise Stop('excluded workspace file cannot be safely inspected') from exc
                if oc2_workspace.contains_credential_material(excluded_content):
                    raise Stop('workspace file appears to contain credential material')
    git_metadata = workspace / '.git'
    if git_metadata.is_symlink() or not git_metadata.is_dir():
        raise Stop('workspace requires a real .git directory')

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


def _sandbox_record(runner: Runner, name: str) -> tuple[dict[str, object], str]:
    import json

    try:
        listing = json.loads(runner.sbx('ls', '--format', 'json', capture=True))
    except (TypeError, ValueError) as exc:
        raise Stop('could not parse existing Sandbox identity') from exc
    records: list[object] | None
    if isinstance(listing, list):
        records = listing
    elif isinstance(listing, dict):
        candidate = listing.get('sandboxes')
        records = candidate if isinstance(candidate, list) else None
    else:
        records = None
    if records is None:
        raise Stop('could not establish existing Sandbox identity')
    matches = [row for row in records if isinstance(row, dict) and row.get('name') == name]
    if len(matches) != 1:
        raise Stop('could not establish existing Sandbox identity')
    record = matches[0]
    sandbox_id = record.get('id')
    if not isinstance(sandbox_id, str) or re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            sandbox_id) is None:
        raise Stop('existing Sandbox has no valid stable identifier')
    return record, sandbox_id


def sandbox_id(runner: Runner, name: str) -> str:
    return _sandbox_record(runner, name)[1]


def is_compatible_sandbox(runner: Runner, name: str, expected_id: str) -> bool:
    # sbx ls --format json on v0.49.2 gives identity but does not report
    # workspace/mounts. Inspect the exact named sandbox before trusting it.
    raw = runner.sbx('ls', '-q', capture=True)
    names = {line.strip() for line in raw.splitlines() if line.strip()}
    if name not in names:
        return False
    row, actual_id = _sandbox_record(runner, name)
    if actual_id != expected_id:
        raise Stop('Sandbox identity mismatch; refusing reuse')
    if row.get('agent') not in ('shell', 'sbx-kit-shell'):
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
    digest = verify_bundle(out, trusted_root=out.parent)
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


def provision_cli(runner: Runner, name: str, host_binary: pathlib.Path) -> str:
    found = cli_path(runner, name)
    if found:
        return found
    if host_binary.is_symlink() or not host_binary.is_file():
        raise Stop('Host OpenCode binary is missing or unsafe')
    print(f'OC2: copying the verified Host OpenCode v{VERSION} binary.')
    runner.sbx('exec', name, 'mkdir', '-p', str(pathlib.PurePosixPath(PINNED[0]).parent))
    runner.sbx('cp', str(host_binary), f'{name}:{PINNED[0]}')
    runner.sbx('exec', name, 'chmod', '700', PINNED[0])
    found = cli_path(runner, name)
    if not found:
        raise Stop(f'copied OpenCode binary is not the pinned v{VERSION}')
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
        if not is_compatible_sandbox(runner, session.sandbox, session.sandbox_id):
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
    p.add_argument('--resume', action='store_true',
                   help='resume post-create provisioning for a Sandbox with a retained source')
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
            print('OC2 PLAN: mountless shell Sandbox=' + args.sandbox)
            print('OC2 PLAN: workspace=' + str(workspace))
            print(f'OC2 PLAN: transfer a verified workspace snapshot and launch OpenCode v{VERSION}')
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
        profile = _workspace_profile(workspace)
        workspace_manifest = oc2_workspace.snapshot(workspace, profile=profile)
        validate_clone_workspace(workspace, profile=profile, manifest=workspace_manifest)
        git_root = subprocess.run(
            ['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if git_root.returncode != 0 or pathlib.Path(git_root.stdout.strip()) != workspace:
            raise Stop('workspace must be the root of a Git repository')
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
            if '--kit' not in create_help:
                raise Stop('installed Docker Sandboxes CLI does not support credential Mixins')
            print('OC2_DOCKER_SANDBOXES: ' + sandbox_version)
            existing = {line.strip() for line in runner.sbx('ls', '-q', capture=True).splitlines()}
            if args.sandbox in existing:
                if not args.resume:
                    raise Stop('Sandbox name already exists; refusing to reuse or rebuild it')
                retained = CLONE_SOURCE_ROOT / args.sandbox / 'workspace'
                if retained.is_symlink() or not retained.is_dir():
                    raise Stop('--resume requires the retained workspace source for this Sandbox')
                sessions = importlib.import_module('oc2_session')
                session = sessions.load(CLONE_SOURCE_ROOT / 'sessions', workspace)
                if session.sandbox != args.sandbox:
                    raise Stop('--resume Sandbox does not match the retained transfer receipt')
                if session.manifest != workspace_manifest:
                    raise Stop('--resume Workspace differs from the retained transfer snapshot')
                if not is_compatible_sandbox(runner, args.sandbox, session.sandbox_id):
                    raise Stop('--resume Sandbox identity or mount state could not be verified')
                if cloudflare is not None:
                    credential_scope = ensure_cloudflare_credential(
                        runner, args.sandbox, interactive=sys.stdin.isatty(),
                    )
                    print('OC2_CLOUDFLARE_CREDENTIAL: available (' + credential_scope + ' scope)')
                host_binary = download_cli_binary(temporary_path)
                cli = provision_cli(runner, args.sandbox, host_binary)
                workdir = session.remote
                clone_root = runner.sbx(
                    'exec', args.sandbox, 'git', '-C', workdir,
                    'rev-parse', '--show-toplevel', capture=True,
                ).strip()
                if clone_root != workdir:
                    raise Stop('Sandbox working directory is not the Clone-mode Git root')
                runtime_sha = hashlib.sha256(
                    (str(workspace) + '\0' + VERSION).encode(),
                ).hexdigest()
                launch(
                    runner,
                    SandboxLaunch(args.sandbox, runtime_sha, cli, workdir, config_file, cloudflare),
                )
                return 0
            host_binary = download_cli_binary(temporary_path)
            clone_source_directory = _new_clone_source_directory(args.sandbox)
            retained_source = False
            try:
                snapshot_directory = clone_source_directory / 'workspace'
                oc2_workspace.materialize(workspace, snapshot_directory, workspace_manifest)
                print('OC2: creating mountless shell Sandbox ' + args.sandbox)
                mixin_name = 'oc2-credentials-' + secrets.token_hex(6)
                with tempfile.TemporaryDirectory(prefix='oc2-credential-mixin-') as mixin_temporary:
                    mixin_path = pathlib.Path(mixin_temporary)
                    mixin_spec_path = mixin_path / 'spec.yaml'
                    mixin_spec_path.write_bytes(credential_mixin_spec(mixin_name))
                    os.chmod(mixin_spec_path, 0o600)
                    retained_source = True
                    print('OC2_WORKSPACE_SNAPSHOT: ' + str(snapshot_directory))
                    runner.sbx(*workspace_create_args(args.sandbox, mixin_path))
                workdir = transfer_workspace(
                    runner, args.sandbox, snapshot_directory, workspace_manifest, runner.user,
                )
                runner.sbx('exec', args.sandbox, 'git', '-C', workdir, 'init', '--quiet')
                for remote in clone_remotes:
                    runner.sbx('exec', args.sandbox, 'git', '-C', workdir,
                               'remote', 'add', remote.name, remote.fetch_urls[0])
                    for url in remote.fetch_urls[1:]:
                        runner.sbx('exec', args.sandbox, 'git', '-C', workdir,
                                   'remote', 'set-url', '--add', remote.name, url)
                    for url in remote.push_urls:
                        runner.sbx('exec', args.sandbox, 'git', '-C', workdir,
                                   'remote', 'set-url', '--add', '--push', remote.name, url)
                sessions = importlib.import_module('oc2_session')
                sessions.create(
                    CLONE_SOURCE_ROOT / 'sessions', args.sandbox, workdir,
                    workspace_manifest, sandbox_id=sandbox_id(runner, args.sandbox),
                )
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
            cli = provision_cli(runner, args.sandbox, host_binary)
            clone_root = runner.sbx(
                'exec', args.sandbox, 'git', '-C', workdir,
                'rev-parse', '--show-toplevel', capture=True,
            ).strip()
            if clone_root != workdir:
                raise Stop('Sandbox working directory is not the transferred workspace root')
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
