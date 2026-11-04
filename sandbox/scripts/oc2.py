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
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Final

import yaml

if TYPE_CHECKING:
    from sandbox.scripts.oc2_workspace import Manifest as WorkspaceManifest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERSION = '2.2.5'
ROOT = '/home/agent/workspace/oc2'
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]$')
CF_GATEWAY_PROVIDER_ID: Final[str] = 'cloudflare-ai-gateway-custom'
CLOUDFLARE_TOKEN_PLACEHOLDER: Final[str] = 'proxy-managed'
OPENAI_ACCESS_TOKEN_SENTINEL: Final[str] = 'oai-oat01-proxy-managed'
OPENAI_REFRESH_TOKEN_SENTINEL: Final[str] = 'oai-ort01-proxy-managed'
PINNED = (
    '/home/agent/.local/oc2-runtime/node_modules/.bin/opencode',
)


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


def credential_mixin_spec(name: str) -> bytes:
    """Serialize the proxy credential bindings without embedding credentials."""
    if re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) is None:
        raise Stop('invalid credential Mixin name')
    spec = {
        'schemaVersion': '2',
        'kind': 'mixin',
        'name': name,
        'requires': {'agent': 'shell'},
        'credentials': [
            {
                'service': 'openai',
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
            {
                'service': 'cloudflare-ai-gateway',
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
        ],
        'permissions': {
            'network': {
                'allow': [
                    'auth.openai.com',
                    'chatgpt.com',
                    'gateway.ai.cloudflare.com',
                ],
            },
        },
    }
    return yaml.safe_dump(spec, sort_keys=False).encode('utf-8')


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
    providers = config.get('providers')
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

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        command = operator_command(self.user, 'sbx', *args)
        if self.dry_run:
            print('PLAN: ' + ' '.join(command[:5]) + ' [...]')
            return ''
        try:
            result = subprocess.run(command, check=False, text=True,
                                    capture_output=capture, timeout=None if tty else 180)
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
    for current, directories, filenames in os.walk(workspace, followlinks=False):
        directories[:] = [name for name in directories if name != '.git']
        current_path = pathlib.Path(current)
        exposed.update(
            (current_path / name).relative_to(workspace).as_posix()
            for name in filenames
        )
    if exposed != checked:
        raise Stop('clone mode would expose files excluded from the safe workspace scan')


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


def seed_cli(runner: Runner, name: str, source: str, scratch: pathlib.Path) -> str | None:
    """Copy only a verified CLI package tree from a separate mountless PoC.

    This avoids changing network policy. Neither credentials nor XDG data are
    read from the source Sandbox. No existing target installation is overwritten.
    """
    if not source or source == name:
        return None
    if not is_compatible_sandbox(runner, source):
        return None
    binary = PINNED[0]
    quoted = shlex.quote(binary)
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
        created = subprocess.run([*operator, 'mktemp', '-d', '/tmp/oc2-seed-XXXXXXXX'],
                                 capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise Stop('could not create private Sandbox operator staging directory') from exc
    staging = created.stdout.strip()
    if re.fullmatch(r'/tmp/oc2-seed-[A-Za-z0-9]{8}', staging) is None:
        raise Stop('unsafe seed staging path')
    local = pathlib.Path(staging) / 'node_modules'
    try:
        print('OC2: seeding pinned CLI from read-only PoC sandbox ' + source)
        runner.sbx('cp', f'{source}:/home/agent/.local/opencode-v2/node_modules', str(local))
        runner.sbx('exec', name, 'bash', '-c',
                   'set -eu; mkdir -p /home/agent/.local/opencode-v2; '
                   'test ! -e /home/agent/.local/opencode-v2/node_modules')
        runner.sbx('cp', str(local), f'{name}:/home/agent/.local/opencode-v2/node_modules')
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
    runner.sbx(*install_cli_args(name))
    found = cli_path(runner, name)
    if not found:
        raise Stop(f'installed CLI is not the pinned v{VERSION}')
    return found


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
    runner.sbx(
        'exec', '-it', '-w', workdir, request.name,
        'env', '-i',
        f'HOME={runtime}/home',
        'USER=agent',
        'SHELL=/bin/bash',
        'PATH=/usr/local/bin:/usr/bin:/bin',
        'TERM=xterm-256color',
        'LANG=C.UTF-8',
        f'XDG_CONFIG_HOME={runtime}/config',
        f'XDG_DATA_HOME={runtime}/home/.local/share',
        f'XDG_STATE_HOME={runtime}/state',
        f'XDG_CACHE_HOME={runtime}/cache',
        f'TMPDIR={runtime}/tmp',
        'OPENCODE_WATCHDOG_ENABLED=false',
        'OPENCODE_DISABLE_AUTOUPDATE=1',
        'OPENCODE_DISABLE_MODELS_FETCH=1',
        *cloudflare_environment,
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
                    candidate = workspaces.snapshot(incoming)
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
                   help='export and verify APM config without Sandbox commands')
    p.add_argument('--allow-paid-inference', action='store_true',
                   help='authorize external inference for this interactive launch')
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
        with tempfile.TemporaryDirectory(prefix='oc2-v2-config-') as temporary:
            temporary_path = pathlib.Path(temporary)
            config_file = export_v2_config(repo, temporary_path / 'export')
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
            print('OC2: creating clone-mode shell Sandbox ' + args.sandbox)
            mixin_name = 'oc2-credentials-' + secrets.token_hex(6)
            with tempfile.TemporaryDirectory(prefix='oc2-credential-mixin-') as mixin_temporary:
                mixin_path = pathlib.Path(mixin_temporary)
                mixin_spec_path = mixin_path / 'spec.yaml'
                mixin_spec_path.write_bytes(credential_mixin_spec(mixin_name))
                os.chmod(mixin_spec_path, 0o600)
                runner.sbx(*clone_create_args(args.sandbox, workspace, mixin_path))
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
