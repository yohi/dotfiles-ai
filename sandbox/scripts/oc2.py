#!/usr/bin/env python3
"""Host-side one-command OpenCode v2 launcher using Docker Sandboxes.

Source configuration is exported from dotfiles-ai/apm.yml. No credential, MCP,
provider, or OpenCode v1 runtime files are copied. Host/workspace mounts are
not requested. Existing unrelated sandboxes are never modified.
"""
from __future__ import annotations

import argparse
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
import subprocess
import sys
import tarfile
import tempfile
from typing import TYPE_CHECKING, Final, Literal
from urllib.parse import urlsplit

import yaml
from oc2_oauth_bundle import oauth_helper_source
from oc2_identity import runtime_identity_sha256, verification_generator_fingerprint

if TYPE_CHECKING:
    from sandbox.scripts.oc2_workspace import Manifest as WorkspaceManifest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERSION = '2.2.5'
ROOT = '/home/agent/workspace/oc2'
SHELL_WORKLOAD: Final[str] = 'docker.io/docker/sbx-kit-shell:1.0.0'
CLI_ASSET_URL: Final[str] = (
    'https://github.com/anomalyco/opencode/releases/download/v2.2.5/'
    'opencode-linux-x64.tar.gz'
)
CLI_ASSET_SIZE: Final[int] = 119_196_162
CLI_ASSET_SHA256: Final[str] = '09f44302c10fd036912f59c81fd1aef5df45dd06f649197f9dfc9bbe2a79614e'
CLI_BINARY_SIZE: Final[int] = 252_713_136
CLI_REDIRECT_HOSTS: Final[frozenset[str]] = frozenset({
    'github.com',
    'release-assets.githubusercontent.com',
    'objects.githubusercontent.com',
})
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]$')
CF_GATEWAY_PROVIDER_ID: Final[str] = 'cloudflare-ai-gateway-custom'
CLOUDFLARE_SECRET_NAME: Final[str] = 'cloudflare-ai-gateway'
CLOUDFLARE_TOKEN_PLACEHOLDER: Final[str] = 'proxy-managed'
OPENAI_ACCESS_TOKEN_SENTINEL: Final[str] = 'oai-oat01-proxy-managed'
OPENAI_REFRESH_TOKEN_SENTINEL: Final[str] = 'oai-ort01-proxy-managed'
PINNED = (
    '/opt/oc2/bin/opencode',
)

DESTINATION_CHECK_SCRIPT = '''import errno, os, stat, sys
path = sys.argv[1] if len(sys.argv) == 2 else ""
parts = path.split("/")
if not path.startswith("/") or len(parts) < 3 or any(p in ("", ".", "..") for p in parts[1:]):
    sys.exit(12)
fd = None
try:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    for part in parts[1:-1]:
        child = os.open(part, flags, dir_fd=fd)
        os.close(fd)
        fd = child
    try:
        mode = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        sys.exit(0 if exc.errno == errno.ENOENT else 11)
    sys.exit(10 if stat.S_ISREG(mode) else 12)
except OSError as exc:
    sys.exit(12 if exc.errno in (errno.ELOOP, errno.ENOTDIR) else 11)
finally:
    if fd is not None:
        os.close(fd)
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
    assets_file: pathlib.Path | None = None
    assets_sha: str | None = None


class Stop(Exception):
    pass


class SandboxCommandTimeout(Stop):
    pass


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


def opencode_cli_mixin_spec() -> bytes:
    """Copy the verified standalone CLI into the Kit without network installs."""
    build = (
        'FROM scratch\n'
        'COPY --chmod=0755 opencode '
        '/opt/oc2/bin/opencode\n'
    )
    spec = {
        'schemaVersion': '3',
        'kind': 'mixin',
        'displayName': 'oc2-opencode-cli-2.2.5',
        'provides': [f'opencode-cli@{VERSION}'],
        'build': build,
    }
    return b'# syntax=docker/sandbox-kit:3\n' + yaml.safe_dump(
        spec, sort_keys=False,
    ).encode('utf-8')


def download_verified_cli(destination: pathlib.Path) -> pathlib.Path:
    """Download, authenticate, and safely extract the pinned official CLI."""
    if (sys.platform != 'linux' or platform.machine().lower() not in
            ('x86_64', 'amd64')):
        raise Stop('pinned OpenCode release asset requires Linux x86-64')
    if (destination.is_symlink() or not destination.is_dir()
            or destination.stat().st_mode & 0o077):
        raise Stop('official CLI download requires a private temporary directory')
    if any(destination.iterdir()):
        raise Stop('official CLI temporary directory must be empty')
    curl = shutil.which('curl')
    if curl is None:
        raise Stop('curl is required to download the official OpenCode release')

    archive_path = destination / 'opencode-linux-x64.tar.gz'
    binary_path = destination / 'opencode'
    command = [
        curl, '--disable', '--fail', '--location', '--max-redirs', '5',
        '--proto', '=https', '--proto-redir', '=https', '--tlsv1.2',
        '--connect-timeout', '20', '--max-time', '240', '--max-filesize',
        str(CLI_ASSET_SIZE), '--silent', '--show-error', '--output',
        str(archive_path), '--write-out',
        '\nOC2_HTTP_STATUS=%{http_code}\nOC2_FINAL_URL=%{url_effective}\n',
        CLI_ASSET_URL,
    ]
    binary_created = False
    try:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise Stop('official OpenCode release download timed out') from exc
        except OSError as exc:
            raise Stop('official OpenCode release download could not run') from exc

        fields = dict(
            line.split('=', 1) for line in result.stdout.splitlines()
            if line.startswith(('OC2_HTTP_STATUS=', 'OC2_FINAL_URL='))
        )
        if result.returncode != 0:
            if result.returncode == 6:
                raise Stop('official OpenCode release download failed: Host DNS resolution failed')
            if result.returncode == 7:
                raise Stop('official OpenCode release download failed: Host connection failed')
            if result.returncode == 28:
                raise Stop('official OpenCode release download timed out')
            raise Stop(f'official OpenCode release download failed (curl exit {result.returncode})')
        if fields.get('OC2_HTTP_STATUS') != '200':
            raise Stop('official OpenCode release returned an unexpected HTTP status')
        final_url = urlsplit(fields.get('OC2_FINAL_URL', ''))
        if (final_url.scheme != 'https'
                or (final_url.hostname or '').lower() not in CLI_REDIRECT_HOSTS):
            raise Stop('official OpenCode release redirected to an untrusted host')
        if archive_path.stat().st_size != CLI_ASSET_SIZE:
            raise Stop('official OpenCode release asset size mismatch')

        archive_hash = hashlib.sha256()
        with archive_path.open('rb') as archive_file:
            for chunk in iter(lambda: archive_file.read(1024 * 1024), b''):
                archive_hash.update(chunk)
        if archive_hash.hexdigest() != CLI_ASSET_SHA256:
            raise Stop('official OpenCode release integrity verification failed')

        with tarfile.open(archive_path, 'r:gz') as archive:
            members = archive.getmembers()
            if len(members) != 1:
                raise Stop('official OpenCode archive contents are invalid')
            member = members[0]
            member_path = pathlib.PurePosixPath(member.name)
            if (member.name != 'opencode' or member_path.is_absolute()
                    or '..' in member_path.parts or not member.isfile()
                    or not (member.mode & 0o111)
                    or member.size != CLI_BINARY_SIZE):
                raise Stop('official OpenCode archive contents are invalid')
            source = archive.extractfile(member)
            if source is None:
                raise Stop('official OpenCode executable is missing from its archive')
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
            fd = os.open(binary_path, flags, 0o600)
            binary_created = True
            with os.fdopen(fd, 'wb') as binary_file:
                extracted = 0
                while chunk := source.read(1024 * 1024):
                    extracted += len(chunk)
                    if extracted > member.size:
                        raise Stop('official OpenCode executable exceeds its archive size')
                    binary_file.write(chunk)
                if extracted != member.size:
                    raise Stop('official OpenCode executable is truncated')
        archive_path.unlink()
        return binary_path
    except Stop:
        archive_path.unlink(missing_ok=True)
        if binary_created:
            binary_path.unlink(missing_ok=True)
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        archive_path.unlink(missing_ok=True)
        if binary_created:
            binary_path.unlink(missing_ok=True)
        raise Stop('official OpenCode release artifact could not be validated') from exc


def cloudflare_gateway_runtime(
    config_file: pathlib.Path,
    account_id: str | None,
    gateway_id: str | None,
) -> CloudflareGatewayRuntime | None:
    """Return validated Cloudflare IDs when the Custom Gateway provider is selected."""
    if config_file.is_symlink() or not config_file.is_file():
        raise Stop('generated OpenCode config is missing or unsafe')
    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop('generated OpenCode config could not be read') from exc
    if not isinstance(config, dict):
        raise Stop('generated OpenCode config is not an object')
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop('generated OpenCode provider selection is invalid')
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


def configure_cloudflare_provider(
    config_file: pathlib.Path,
    *,
    include_cloudflare: bool,
) -> bool:
    """Expose the Gateway provider only when explicitly requested or defaulted."""
    if config_file.is_symlink() or not config_file.is_file():
        raise Stop('generated OpenCode config is missing or unsafe')
    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop('generated OpenCode config could not be read') from exc
    if not isinstance(config, dict):
        raise Stop('generated OpenCode config is not an object')
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop('generated OpenCode provider selection is invalid')
    cloudflare_provider = providers.get(CF_GATEWAY_PROVIDER_ID)
    if cloudflare_provider is not None and not isinstance(cloudflare_provider, dict):
        raise Stop('generated Cloudflare provider selection is invalid')

    default_model = config.get('model')
    default_uses_cloudflare = (
        isinstance(default_model, str)
        and default_model.partition('/')[0] == CF_GATEWAY_PROVIDER_ID
    )
    if include_cloudflare or default_uses_cloudflare:
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
        config_file.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
    except OSError as exc:
        raise Stop('generated OpenCode config could not be prepared') from exc
    return False


def _cloudflare_secret_scope(
    listing: str,
    sandbox_name: str,
) -> Literal['sandbox', 'global'] | None:
    """Parse only scope metadata for the Cloudflare service secret."""
    try:
        document = json.loads(listing)
    except json.JSONDecodeError as exc:
        raise Stop('Cloudflare credential listing JSON is invalid') from None
    if not isinstance(document, dict) or set(document) != {'secrets'}:
        raise Stop('Cloudflare credential listing JSON schema is unsupported')
    entries = document['secrets']
    if not isinstance(entries, list):
        raise Stop('Cloudflare credential listing JSON schema is invalid')

    scopes: set[Literal['sandbox', 'global']] = set()
    expected_fields = {'name', 'scope', 'secret', 'type'}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise Stop('Cloudflare credential entry schema is unsupported')
        name = entry['name']
        scope = entry['scope']
        secret_type = entry['type']
        if (not isinstance(name, str) or not isinstance(scope, str)
                or not isinstance(entry['secret'], str)
                or not isinstance(secret_type, str)):
            raise Stop('Cloudflare credential entry schema is invalid')
        if name != CLOUDFLARE_SECRET_NAME:
            continue
        if secret_type != 'service':
            raise Stop('Cloudflare credential type is unexpected')
        if scope == sandbox_name:
            scopes.add('sandbox')
        elif scope in ('(global)', 'global'):
            scopes.add('global')
        else:
            raise Stop('Cloudflare credential scope is unexpected')

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
        else (
            'secret', 'ls', '--sandbox', sandbox_name,
            '--service', CLOUDFLARE_SECRET_NAME, '--json',
        )
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

    runner.sbx(
        'secret', 'set', CLOUDFLARE_SECRET_NAME, '--sandbox', sandbox_name,
        tty=True,
    )
    scope = _read_cloudflare_secret_scope(runner, sandbox_name, global_scope=False)
    if scope != 'sandbox':
        raise Stop('Cloudflare sandbox-scoped credential was not verified')
    return scope


def requires_external_inference(config_file: pathlib.Path) -> bool:
    """Return whether the exported OpenCode config selects an external provider."""
    if config_file.is_symlink() or not config_file.is_file():
        raise Stop('generated OpenCode config is missing or unsafe')
    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop('generated OpenCode config could not be read') from exc
    if not isinstance(config, dict):
        raise Stop('generated OpenCode config is not an object')
    providers = config.get('providers', {})
    if not isinstance(providers, dict):
        raise Stop('generated OpenCode provider selection is invalid')
    return bool(providers)


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

    def destination_status(self, name: str, destination: str) -> int:
        command = operator_command(self.user, 'sbx', 'exec', name, 'python3', '-c',
                                   DESTINATION_CHECK_SCRIPT, destination)
        if self.dry_run:
            raise Stop('DESTINATION_CHECK_COMMAND_FAILED')
        try:
            result = subprocess.run(command, check=False, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise Stop('DESTINATION_CHECK_TIMEOUT') from exc
        except OSError as exc:
            raise Stop('DESTINATION_CHECK_COMMAND_FAILED') from exc
        return result.returncode

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        command = operator_command(self.user, 'sbx', *args)
        if self.dry_run:
            print('PLAN: ' + ' '.join(command[:5]) + ' [...]')
            return ''
        try:
            result = subprocess.run(command, check=False, text=True,
                                    capture_output=capture, timeout=None if tty else 180)
        except subprocess.TimeoutExpired as exc:
            raise SandboxCommandTimeout('sbx command could not complete') from exc
        except OSError as exc:
            raise Stop('sbx command could not complete') from exc
        if result.returncode != 0:
            raise Stop(f'sbx command failed (exit {result.returncode})')
        return result.stdout if capture else ''


def mountless_create_args(
    name: str,
    credential_mixin_path: pathlib.Path,
    cli_mixin_path: pathlib.Path,
) -> list[str]:
    return [
        'create', '--name', name,
        '--kit', str(credential_mixin_path),
        '--kit', str(cli_mixin_path),
        SHELL_WORKLOAD,
    ]


def workspace_transfer_profile(workspace: pathlib.Path) -> str | None:
    try:
        origin = subprocess.run(
            ['git', '-C', str(workspace), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if origin.returncode != 0:
        return None
    approved_origins = (
        r'git@github\.com:yohi/dotfiles-ai(?:\.git)?',
        r'ssh://git@github\.com/yohi/dotfiles-ai(?:\.git)?',
        r'https://github\.com/yohi/dotfiles-ai(?:\.git)?',
    )
    if any(re.fullmatch(pattern, origin.stdout.strip()) for pattern in approved_origins):
        return 'dotfiles-ai/workspace-safe-transfer/r1'
    return None


def export_v2_config(
    repo: pathlib.Path,
    output: pathlib.Path,
    *,
    verification_only: bool = False,
) -> pathlib.Path:
    script = HERE / 'prepare_opencode_v2.py'
    try:
        command = [sys.executable, str(script), '--repo-root', str(repo), '--out', str(output)]
        if verification_only:
            command.append('--verification-only')
        result = subprocess.run(
            command,
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
    if operator == getpass.getuser():
        return
    if re.fullmatch(r'[a-z_][a-z0-9_-]*', operator) is None:
        raise Stop('invalid Sandbox operator user')
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
    status = runner.destination_status(name, destination)
    if status in (10, 12):
        raise Stop('DESTINATION_EXISTS')
    if status == 11:
        raise Stop('DESTINATION_CHECK_INDETERMINATE')
    if status != 0:
        raise Stop('DESTINATION_CHECK_COMMAND_FAILED')
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
    native_helper = HERE / 'oc2_agent_native.py'
    native_helper_sha = hashlib.sha256(native_helper.read_bytes()).hexdigest()
    identity_helper = HERE / 'oc2_identity.py'
    identity_helper_sha = hashlib.sha256(identity_helper.read_bytes()).hexdigest()
    verifier_dir = (
        f'{ROOT}/scripts/oc2_guest_{script_sha[:16]}_{native_helper_sha[:16]}_'
        f'{identity_helper_sha[:16]}'
    )
    script_dest = f'{verifier_dir}/oc2_guest.py'
    native_helper_dest = f'{verifier_dir}/oc2_agent_native.py'
    identity_helper_dest = f'{verifier_dir}/oc2_identity.py'
    # sbx exec v0.49.2 was observed invoking bash -c without the expected
    # trailing positional parameters. Use direct argv for filesystem operations.
    execute(runner, name, 'mkdir', '-p', ROOT, f'{ROOT}/bundles', f'{ROOT}/scripts', verifier_dir)
    execute(runner, name, 'chmod', '700', ROOT, f'{ROOT}/bundles', f'{ROOT}/scripts', verifier_dir)
    # Never overwrite an existing bundle or bootstrap script. Reuse is allowed
    # only after the guest validates their content and hash.
    exists = runner.sbx('exec', name, 'bash', '-c',
                        f'if test -e {shlex.quote(destination)}; then echo exists; else echo missing; fi',
                        capture=True).strip()
    if exists == 'missing':
        runner.sbx('cp', str(bundle), f'{name}:{destination}')
    elif exists != 'exists':
        raise Stop('cannot determine remote bundle state')
    script_status = runner.destination_status(name, script_dest)
    if script_status == 0:
        runner.sbx('cp', str(guest_script), f'{name}:{script_dest}')
    elif script_status == 10:
        pass
    elif script_status == 12:
        raise Stop('unsafe guest asset verifier path')
    else:
        raise Stop('cannot determine remote bootstrap script state')
    remote_sha = runner.sbx('exec', name, 'sha256sum', script_dest, capture=True).split()[0]
    if remote_sha != script_sha:
        raise Stop('guest bootstrap code SHA mismatch')
    helper_status = runner.destination_status(name, native_helper_dest)
    if helper_status == 0:
        runner.sbx('cp', str(native_helper), f'{name}:{native_helper_dest}')
    elif helper_status == 10:
        pass
    elif helper_status == 12:
        raise Stop('unsafe guest native verifier path')
    else:
        raise Stop('cannot determine remote native verifier state')
    helper_sha = runner.sbx(
        'exec', name, 'sha256sum', native_helper_dest, capture=True,
    ).split()[0]
    if helper_sha != native_helper_sha:
        raise Stop('guest native verifier SHA mismatch')
    identity_status = runner.destination_status(name, identity_helper_dest)
    if identity_status == 0:
        runner.sbx('cp', str(identity_helper), f'{name}:{identity_helper_dest}')
    elif identity_status == 10:
        pass
    elif identity_status == 12:
        raise Stop('unsafe guest identity verifier path')
    else:
        raise Stop('cannot determine guest identity verifier state')
    identity_sha = runner.sbx(
        'exec', name, 'sha256sum', identity_helper_dest, capture=True,
    ).split()[0]
    if identity_sha != identity_helper_sha:
        raise Stop('guest identity verifier SHA mismatch')
    args = ['--bundle', destination, '--expected-sha', manifest_sha]
    if (assets_file is None) != (assets_sha is None):
        raise Stop('asset file and hash must be supplied together')
    if assets_file is not None and assets_sha is not None:
        if re.fullmatch(r'[0-9a-f]{64}', assets_sha) is None:
            raise Stop('invalid asset hash')
        remote_assets = f'{ROOT}/assets/{assets_sha[:16]}.json'
        execute(runner, name, 'mkdir', '-p', f'{ROOT}/assets')
        status = runner.destination_status(name, remote_assets)
        if status == 0:
            runner.sbx('cp', str(assets_file), f'{name}:{remote_assets}')
        elif status == 10:
            pass
        elif status == 12:
            raise Stop('unsafe guest asset bundle path')
        else:
            raise Stop('cannot establish guest asset state')
        actual = runner.sbx('exec', name, 'sha256sum',
                            remote_assets, capture=True).split()[0]
        if actual != assets_sha:
            raise Stop('guest asset bundle SHA mismatch')
        args.extend(['--assets', remote_assets, '--expected-assets-sha', assets_sha])
    execute(runner, name, 'python3', script_dest, *args)


def prepare_verification_runtime(
    repo: pathlib.Path,
    sandbox: str,
    plugin_dir: pathlib.Path,
) -> str:
    runner = Runner(getpass.getuser())
    if not is_compatible_sandbox(runner, sandbox):
        raise Stop('verification mode requires an existing compatible mountless Sandbox')
    if cli_path(runner, sandbox) is None:
        raise Stop('verification mode requires the pinned OpenCode CLI to be present')
    from sandbox.scripts.stage_opencode_v2 import verify_bundle

    with tempfile.TemporaryDirectory(prefix='oc2-plugin-mcp-') as temporary:
        temporary_path = pathlib.Path(temporary)
        bundle = temporary_path / 'bundle'
        export_v2_config(repo, bundle, verification_only=True)
        config_sha = verify_bundle(bundle)
        from oc2_assets import AssetError, build as build_assets, write_new

        try:
            asset_raw, asset_sha = build_assets(
                repo, verification_only=True, plugin_dir=plugin_dir,
            )
        except AssetError as exc:
            raise Stop('verification Plugin/MCP asset export failed: ' + str(exc)) from exc
        asset_file = temporary_path / 'assets.json'
        write_new(asset_file, asset_raw)
        generator_fingerprint = verification_generator_fingerprint(
            HERE / 'oc2_guest.py', HERE / 'oc2_agent_native.py', HERE / 'oc2_identity.py',
        )
        runtime_sha = runtime_identity_sha256(
            config_sha, asset_sha, generator_fingerprint,
        )
        runtime_destination = f'{ROOT}/runtime/{runtime_sha[:16]}'
        destination_status = runner.destination_status(sandbox, runtime_destination)
        if destination_status == 10:
            raise Stop('verification Runtime identity already exists; refusing reuse')
        if destination_status == 12:
            raise Stop('verification Runtime destination is unsafe')
        if destination_status != 0:
            raise Stop('could not establish verification Runtime identity availability')
        stage(
            runner, sandbox, bundle, config_sha, HERE / 'oc2_guest.py',
            asset_file, asset_sha,
        )
        print('OC2_VERIFICATION_PREPARED: sandbox=' + sandbox + ' runtime=' + runtime_sha[:16])
        return runtime_sha


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


def provision_cli(runner: Runner, name: str) -> str:
    found = cli_path(runner, name)
    if found is None:
        raise Stop('pinned OpenCode CLI is not present in the Sandbox kit')
    return found


GUEST_EXEC_WRAPPER = r'''import os
import re
import sys
from urllib.parse import urlsplit

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
        parsed = urlsplit(proxy)
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


def launch(runner: Runner, request: SandboxLaunch) -> None:
    # Use sbx exec's native --workdir and direct argv instead of bash -c
    # positional parameters. The configured runtime is fully sandbox-local.
    if re.fullmatch(r'[0-9a-f]{64}', request.digest) is None:
        raise Stop('invalid runtime digest')
    if request.cli not in PINNED:
        raise Stop('unapproved OpenCode executable path')
    runtime = f'{ROOT}/runtime/{request.digest[:16]}'
    if (request.assets_file is None) != (request.assets_sha is None):
        raise Stop('asset file and hash must be supplied together')
    if request.assets_file is not None and request.assets_sha is not None:
        if re.fullmatch(r'[0-9a-f]{64}', request.assets_sha) is None:
            raise Stop('invalid asset hash')
        remote_assets = f'{ROOT}/assets/{request.assets_sha[:16]}.json'
        guest_script = HERE / 'oc2_guest.py'
        guest_script_sha = hashlib.sha256(guest_script.read_bytes()).hexdigest()
        native_helper = HERE / 'oc2_agent_native.py'
        native_helper_sha = hashlib.sha256(native_helper.read_bytes()).hexdigest()
        verifier_dir = (
            f'{ROOT}/scripts/oc2_guest_{guest_script_sha[:16]}_{native_helper_sha[:16]}'
        )
        remote_script = f'{verifier_dir}/oc2_guest.py'
        remote_helper = f'{verifier_dir}/oc2_agent_native.py'
        runner.sbx(
            'exec', request.name, 'mkdir', '-p',
            f'{ROOT}/assets', f'{ROOT}/scripts', verifier_dir,
        )
        for local, remote, label in (
            (request.assets_file, remote_assets, 'asset bundle'),
            (guest_script, remote_script, 'asset verifier'),
            (native_helper, remote_helper, 'native verifier'),
        ):
            state = runner.destination_status(request.name, remote)
            if state == 0:
                runner.sbx('cp', str(local), f'{request.name}:{remote}')
            elif state == 10:
                pass
            elif state == 12:
                raise Stop('unsafe guest ' + label + ' path')
            else:
                raise Stop('cannot establish guest ' + label + ' state')
            expected = (
                request.assets_sha if label == 'asset bundle'
                else guest_script_sha if label == 'asset verifier'
                else native_helper_sha
            )
            actual = runner.sbx('exec', request.name, 'sha256sum', remote, capture=True).split()
            if not actual or actual[0] != expected:
                raise Stop('guest ' + label + ' SHA mismatch')
        runner.sbx(
            'exec', request.name, 'python3', remote_script,
            '--assets', remote_assets, '--expected-assets-sha', request.assets_sha,
            '--install-assets-runtime', request.digest,
        )
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
        'exec', request.name, 'mkdir', '-p', '-m', '700', runtime,
        *(f'{runtime}/{directory}' for directory in
          ('home', 'home/.local/share', 'config', 'config/opencode',
           'state', 'cache', 'tmp')),
    )
    runner.sbx('exec', request.name, 'mkdir', '-p', '-m', '700',
               f'{runtime}/home/.local/share/opencode')
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
        'OPENCODE_DISABLE_AUTOUPDATE=1',
        'OPENCODE_DISABLE_MODELS_FETCH=1',
        'OPENCODE_CONFIG_PROJECT_DISABLE=1',
        *cloudflare_environment,
    )
    helper = oauth_helper_source(HERE)
    runner.sbx(
        'exec', '-w', workdir, request.name,
        'python3', '-c', GUEST_EXEC_WRAPPER, '--', *runtime_environment, '--',
        'python3', '-c', helper, request.cli, 'oc2_oauth.py',
    )
    runner.sbx(
        'exec', '-it', '-w', workdir, request.name,
        'python3', '-c', GUEST_EXEC_WRAPPER, '--', *runtime_environment, '--',
        request.cli, '--standalone', tty=True,
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
        try:
            with tempfile.TemporaryDirectory(prefix='oc2-collect-', dir='/tmp') as temp:
                staging = pathlib.Path(temp)
                incoming = staging / 'incoming'
                grant_collection_directory_access(staging, args.sbx_user)
                try:
                    runner.sbx('cp', f'{session.sandbox}:{session.remote}', str(incoming))
                    grant_collected_workspace_access(
                        incoming, args.sbx_user, getpass.getuser(),
                    )
                    candidate = workspaces.snapshot(
                        incoming, profile=session.manifest.profile,
                    )
                    workspaces.materialize(incoming, collected, candidate)
                finally:
                    if incoming.exists() or incoming.is_symlink():
                        run_operator(args.sbx_user, 'rm', '-rf', '--', str(incoming))
        except BaseException:
            if collected.exists() and not collected.is_symlink():
                shutil.rmtree(collected, ignore_errors=True)
            raise
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
                   help='prepare config without launching OpenCode')
    p.add_argument('--verification-only', action='store_true',
                   help='prepare the fixed Plugin/MCP Runtime without launching OpenCode')
    p.add_argument('--plugin-dir', type=pathlib.Path,
                   help='clean local Git checkout for the pinned Superpowers Plugin')
    p.add_argument('--allow-paid-inference', action='store_true',
                   help='authorize external inference for this interactive launch')
    p.add_argument('--use-cloudflare-ai-gateway', action='store_true',
                   help='enable Cloudflare AI Gateway and provision its Sandbox credential')
    args = p.parse_args(argv)
    oc2_workspace = importlib.import_module('oc2_workspace')

    try:
        if args.verification_only:
            if not args.prepare_only:
                raise Stop('--verification-only requires --prepare-only')
            if args.plugin_dir is None:
                raise Stop('--verification-only requires --plugin-dir')
            if args.use_cloudflare_ai_gateway or args.allow_paid_inference:
                raise Stop('verification mode does not permit provider credentials or inference')
        elif args.plugin_dir is not None:
            raise Stop('--plugin-dir is only valid with --verification-only')
        if args.dry_run:
            if args.verification_only:
                if not NAME_RE.fullmatch(args.sandbox):
                    raise Stop('invalid Sandbox name')
                print('OC2 PLAN: verification-only Sandbox=' + args.sandbox)
                print('OC2 PLAN: require an existing compatible mountless Sandbox and pinned CLI')
                print('OC2 PLAN: verify the pinned local Superpowers Git checkout')
                print('OC2 PLAN: select pinned Superpowers Git package and oc2-status MCP')
                print('OC2 PLAN: no Sandbox creation, credential provisioning, CLI install, or TUI launch')
                print('OC2 PLAN: no Sandbox commands executed')
                return 0
            workspace = args.workspace.resolve(strict=True)
            if not workspace.is_dir():
                raise Stop('workspace is not a directory')
            if not NAME_RE.fullmatch(args.sandbox):
                raise Stop('invalid Sandbox name')
            print('OC2 PLAN: mountless shell Sandbox=' + args.sandbox)
            print('OC2 PLAN: workspace=' + str(workspace))
            print('OC2 PLAN: transfer only the verified Workspace Snapshot; no .git or OpenCode project config')
            print(f'OC2 PLAN: install and verify @opencode/cli@{VERSION} inside the Sandbox')
            print('OC2 PLAN: no credentials, provider settings, MCP, plugins, or host config')
            print('OC2 PLAN: no Sandbox commands executed')
            return 0
        repo = args.repo_root.resolve(strict=True)
        if not (repo / 'apm.yml').is_file():
            raise Stop('dotfiles-ai apm.yml not found')
        if args.verification_only:
            prepare_verification_runtime(repo, args.sandbox, args.plugin_dir)
            return 0
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
        git_root = subprocess.run(
            ['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if git_root.returncode != 0 or pathlib.Path(git_root.stdout.strip()) != workspace:
            raise Stop('workspace must be the root of a Git repository')
        profile_id = workspace_transfer_profile(workspace)
        workspace_profile = oc2_workspace.profile_by_id(profile_id)
        workspace_manifest = oc2_workspace.snapshot(
            workspace, profile=workspace_profile,
        )
        with tempfile.TemporaryDirectory(prefix='oc2-v2-config-') as temporary:
            temporary_path = pathlib.Path(temporary)
            config_file = export_v2_config(repo, temporary_path / 'export')
            from oc2_assets import build as build_assets

            asset_raw, asset_sha = build_assets(repo)
            asset_payload = json.loads(asset_raw)
            asset_file = temporary_path / 'assets.json'
            asset_file.write_bytes(asset_raw)
            configure_cloudflare_provider(
                config_file,
                include_cloudflare=args.use_cloudflare_ai_gateway,
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
                raise Stop('Sandbox name already exists; refusing to reuse or rebuild it')
            mixin_name = 'oc2-credentials-' + secrets.token_hex(6)
            print('OC2: verifying official OpenCode v2.2.5 Linux x64 artifact')
            with tempfile.TemporaryDirectory(prefix='oc2-cli-artifact-') as artifact_temporary:
                cli_binary = download_verified_cli(pathlib.Path(artifact_temporary))
                print('OC2_CLI_ARTIFACT_VERIFIED: v2.2.5 sha256=' + CLI_ASSET_SHA256)
                print('OC2: creating mountless shell Sandbox ' + args.sandbox)
                with tempfile.TemporaryDirectory(prefix='oc2-kits-') as kits_temporary:
                    kits_root = pathlib.Path(kits_temporary)
                    credential_mixin = kits_root / 'oc2-credentials'
                    cli_mixin = kits_root / 'oc2-opencode-cli'
                    credential_mixin.mkdir()
                    cli_mixin.mkdir()
                    credential_spec = credential_mixin / 'spec.yaml'
                    credential_spec.write_bytes(credential_mixin_spec(mixin_name))
                    os.chmod(credential_spec, 0o600)
                    cli_spec = cli_mixin / 'spec.yaml'
                    cli_spec.write_bytes(opencode_cli_mixin_spec())
                    os.chmod(cli_spec, 0o600)
                    staged_cli = cli_mixin / 'opencode'
                    shutil.copyfile(cli_binary, staged_cli)
                    os.chmod(staged_cli, 0o600)
                    runner.sbx(*mountless_create_args(
                        args.sandbox, credential_mixin, cli_mixin,
                    ))
            if cloudflare is not None:
                credential_scope = ensure_cloudflare_credential(
                    runner,
                    args.sandbox,
                    interactive=sys.stdin.isatty(),
                )
                print('OC2_CLOUDFLARE_CREDENTIAL: available (' + credential_scope + ' scope)')
            cli = provision_cli(runner, args.sandbox)
            snapshot_path = temporary_path / 'workspace-snapshot'
            workdir = transfer_workspace(
                runner, args.sandbox, snapshot_path, workspace_manifest, runner.user,
            )
            runtime_sha = hashlib.sha256(
                (str(workspace) + '\0' + VERSION + '\0' + asset_sha).encode(),
            ).hexdigest()
            config = json.loads(config_file.read_text(encoding='utf-8'))
            config['instructions'] = [
                f'{ROOT}/runtime/{runtime_sha[:16]}/{name}'
                for name in sorted(asset_payload['files'])
                if name == 'config/opencode/AGENTS.md'
                or name.startswith('config/opencode/rules/')
            ]
            config_file.write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
            )
            print(f'OC2_READY: sandbox={args.sandbox} opencode=v{VERSION}')
            launch(
                runner,
                SandboxLaunch(args.sandbox, runtime_sha, cli, workdir, config_file,
                              cloudflare, asset_file, asset_sha),
            )
            return 0
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired,
            oc2_workspace.WorkspaceError) as exc:
        print('OC2_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
