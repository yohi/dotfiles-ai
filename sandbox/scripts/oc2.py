#!/usr/bin/env python3
"""Host-side one-command OpenCode v2 launcher using Docker Sandboxes.

Source configuration is exported from dotfiles-ai/apm.yml. No credential, MCP,
provider, or OpenCode v1 runtime files are copied. Host/workspace mounts are
not requested. Existing unrelated sandboxes are never modified.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
VERSION = '2.1.4'
ROOT = '/home/agent/workspace/oc2'
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]$')
PINNED = (
    '/home/agent/.local/opencode-v2/node_modules/.bin/opencode',
    '/home/agent/.local/oc2-runtime/node_modules/.bin/opencode',
)


class Stop(Exception):
    pass


class Runner:
    def __init__(self, user: str, *, dry_run: bool = False):
        self.user = user
        self.dry_run = dry_run

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        command = []
        if self.user != getpass.getuser():
            if not shutil.which('sudo'):
                raise Stop('sudo is required to use the separate Sandbox operator account')
            command.extend(['sudo', '-i', '-u', self.user, '--'])
        command.extend(['sbx', *args])
        if self.dry_run:
            print('PLAN: ' + ' '.join(command[:5]) + ' [...]')
            return ''
        try:
            result = subprocess.run(command, check=False, text=True,
                                    capture_output=capture, timeout=None if tty else 180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Stop('sbx command could not complete') from exc
        if result.returncode != 0:
            if capture:
                detail = (result.stderr or '').strip().splitlines()[-1:] or ['unknown error']
                raise Stop('sbx command failed: ' + '; '.join(detail)[:300])
            raise Stop(f'sbx command failed (exit {result.returncode})')
        return result.stdout if capture else ''


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
    from stage_opencode_v2 import verify_bundle

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
        quoted = shlex.quote(candidate)
        result = runner.sbx('exec', name, 'bash', '-c',
                            f'if test -x {quoted}; then {quoted} --version; fi',
                            capture=True).strip()
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
            raise Stop('seeded OpenCode CLI did not verify as v2.1.4')
        return binary
    finally:
        subprocess.run([*operator, 'rm', '-rf', '--', staging],
                       capture_output=True, timeout=30, check=False)


def provision_cli(runner: Runner, name: str, seed: str, scratch: pathlib.Path) -> str:
    found = cli_path(runner, name)
    if found:
        return found
    seeded = seed_cli(runner, name, seed, scratch)
    if seeded:
        return seeded
    print('OpenCode v2.1.4 is missing; installing pinned @opencode/cli in the Sandbox.')
    print('Network policy is NOT altered. Registry access must already be approved.')
    execute(runner, name, 'bash', '-c',
            'set -eu; command -v npm >/dev/null; '
            'mkdir -p /home/agent/.local/oc2-runtime; '
            'npm install --prefix /home/agent/.local/oc2-runtime '
            '--no-audit --no-fund --no-save @opencode/cli@2.1.4')
    found = cli_path(runner, name)
    if not found:
        raise Stop('installed CLI is not the pinned v2.1.4')
    return found


def launch(runner: Runner, name: str, digest: str, cli: str) -> None:
    # Use sbx exec's native --workdir and direct argv instead of bash -c
    # positional parameters. The configured runtime is fully sandbox-local.
    if re.fullmatch(r'[0-9a-f]{64}', digest) is None:
        raise Stop('invalid runtime digest')
    if cli not in PINNED:
        raise Stop('unapproved OpenCode executable path')
    runtime = f'{ROOT}/runtime/{digest[:16]}'
    runner.sbx(
        'exec', '-it', '-w', f'{runtime}/project', name,
        'env', '-i',
        f'HOME={runtime}/home',
        'USER=agent',
        'SHELL=/bin/bash',
        'PATH=/usr/local/bin:/usr/bin:/bin',
        'TERM=xterm-256color',
        'LANG=C.UTF-8',
        f'XDG_CONFIG_HOME={runtime}/config',
        f'XDG_DATA_HOME={runtime}/data',
        f'XDG_STATE_HOME={runtime}/state',
        f'XDG_CACHE_HOME={runtime}/cache',
        f'TMPDIR={runtime}/tmp',
        'OPENCODE_WATCHDOG_ENABLED=false',
        'OPENCODE_DISABLE_AUTOUPDATE=1',
        'OPENCODE_DISABLE_MODELS_FETCH=1',
        cli, '--standalone', tty=True,
    )

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=f'oc2 launcher 1.0; OpenCode v{VERSION}')
    p.add_argument('--repo-root', type=pathlib.Path, default=HERE.parents[1])
    p.add_argument('--workspace', type=pathlib.Path, default=pathlib.Path.cwd(),
                   help='host project directory (default: current directory)')
    p.add_argument('--sandbox', default='oc2-dev')
    p.add_argument('--sbx-user', default=os.getenv('OC2_SBX_USER', 'sbx-poc'))
    p.add_argument('--seed-sandbox', default=os.getenv('OC2_SEED_SANDBOX', 'oc-v2-poc'),
                   help='optional mountless PoC containing the pinned CLI; source is read-only')
    p.add_argument('--dry-run', action='store_true', help='show planned actions without writing or calling sbx')
    p.add_argument('--prepare-only', action='store_true', help='prepare config and CLI without opening TUI')
    p.add_argument('--collect', action='store_true', help='collect sandbox changes for review')
    p.add_argument('--apply', action='store_true', help='apply previously collected changes to the host')
    args = p.parse_args(argv)
    try:
        workspace_module = __import__('oc2_workspace')
        workspace = args.workspace
        if workspace.is_symlink():
            raise Stop('workspace root must not be a symlink')
        workspace = workspace.resolve(strict=True)
        if not workspace.is_dir():
            raise Stop('workspace is not a directory')
        if args.collect or args.apply:
            raise Stop('change collection requires a persisted transfer receipt; no receipt was supplied')
        if args.dry_run:
            manifest = workspace_module.snapshot(workspace)
            print('OC2 PLAN: workspace=' + str(workspace))
            print('OC2 PLAN: files=' + str(len(manifest.files)) +
                  ' manifest_sha256=' + hashlib.sha256(manifest.encode()).hexdigest())
            print('OC2 PLAN: secrets, credentials, symlinks, and special files excluded or rejected')
            print('OC2 PLAN: no Sandbox commands executed')
            return 0
        if not NAME_RE.fullmatch(args.sandbox):
            raise Stop('invalid Sandbox name')
        if args.seed_sandbox and not NAME_RE.fullmatch(args.seed_sandbox):
            raise Stop('invalid seed Sandbox name')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.sbx_user):
            raise Stop('invalid Sandbox operator user')
        repo = args.repo_root.resolve(strict=True)
        if not (repo / 'apm.yml').is_file():
            raise Stop('dotfiles-ai apm.yml not found')
        if not shutil.which('sbx'):
            # sbx can be installed only in operator PATH, so also check via sudo.
            if args.sbx_user == getpass.getuser():
                raise Stop('sbx CLI was not found')
        guest_script = HERE / 'oc2_guest.py'
        from oc2_assets import AssetError, build, write_new
        with tempfile.TemporaryDirectory(prefix='oc2-export-') as temp:
            tmp = pathlib.Path(temp)
            tmp.chmod(0o755)
            bundle, digest = export_config(repo, tmp / 'bundle')
            try:
                asset_bytes, asset_sha = build(repo)
                asset_file = tmp / 'oc2-assets.json'
                write_new(asset_file, asset_bytes)
            except AssetError as exc:
                raise Stop('safe settings export failed: ' + str(exc)) from exc
            code = tmp / 'oc2_guest.py'
            shutil.copyfile(guest_script, code)
            code.chmod(0o644)
            runner = Runner(args.sbx_user)
            if not is_compatible_sandbox(runner, args.sandbox):
                print('OC2: creating mountless shell Sandbox ' + args.sandbox)
                runner.sbx('create', '--name', args.sandbox, 'shell')
            else:
                print('OC2: reusing verified mountless Sandbox ' + args.sandbox)
            stage(runner, args.sandbox, bundle, digest, code, asset_file, asset_sha)
            cli = provision_cli(runner, args.sandbox, args.seed_sandbox, tmp)
            runtime_sha = hashlib.sha256(bytes.fromhex(digest) + bytes.fromhex(asset_sha)).hexdigest()
            print('OC2_PREPARED: sandbox=' + args.sandbox +
                  ' config_sha=' + digest[:16] + ' assets_sha=' + asset_sha[:16])
            if not args.prepare_only:
                launch(runner, args.sandbox, runtime_sha, cli)
        return 0
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired,
            workspace_module.WorkspaceError) as exc:
        # No credentials, source config, or raw subprocess dumps on failure.
        print('OC2_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
