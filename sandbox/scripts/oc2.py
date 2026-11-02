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
    raw = runner.sbx('ls', '-q', capture=True)
    names = {line.strip() for line in raw.splitlines() if line.strip()}
    if name not in names:
        return False
    # A checkout may contain secrets. Reject sandboxes with host mounts rather
    # than trusting them for a purportedly mountless workflow.
    import json
    listing = json.loads(runner.sbx('ls', '--format', 'json', capture=True))
    records = listing if isinstance(listing, list) else listing.get('sandboxes', [])
    matches = [row for row in records if isinstance(row, dict)
               and (row.get('name') or row.get('sandbox')) == name]
    if len(matches) != 1:
        raise Stop('could not establish existing Sandbox identity')
    row = matches[0]
    if row.get('agent') not in (None, 'shell'):
        raise Stop('existing Sandbox agent is not shell')
    # The API has used both workspace and workspaces between CLI revisions.
    if 'workspace' not in row and 'workspaces' not in row:
        raise Stop('could not verify that the existing Sandbox has no Host mount')
    value = row.get('workspaces', row.get('workspace'))
    if value not in (None, '', '-', [], {}):
        raise Stop('existing Sandbox has a workspace mount; refusing reuse')
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
          guest_script: pathlib.Path) -> None:
    destination = f'{ROOT}/bundles/{manifest_sha[:16]}'
    script_sha = hashlib.sha256(guest_script.read_bytes()).hexdigest()
    script_dest = f'{ROOT}/scripts/oc2_guest_{script_sha[:16]}.py'
    execute(runner, name, 'bash', '-c',
            'set -eu; mkdir -p "$1" "$2"; chmod 700 "$1" "$2"',
            'oc2', f'{ROOT}/bundles', f'{ROOT}/scripts')
    # Never overwrite an existing bundle or bootstrap script. Reuse is allowed
    # only after the guest validates their content and hash.
    exists = runner.sbx('exec', name, 'bash', '-c',
                        'if test -e "$1"; then echo exists; else echo missing; fi',
                        'oc2', destination, capture=True).strip()
    if exists == 'missing':
        runner.sbx('cp', str(bundle), f'{name}:{destination}')
    elif exists != 'exists':
        raise Stop('cannot determine remote bundle state')
    script_exists = runner.sbx('exec', name, 'bash', '-c',
                               'if test -e "$1"; then echo exists; else echo missing; fi',
                               'oc2', script_dest, capture=True).strip()
    if script_exists == 'missing':
        runner.sbx('cp', str(guest_script), f'{name}:{script_dest}')
    elif script_exists != 'exists':
        raise Stop('cannot determine remote bootstrap script state')
    remote_sha = runner.sbx('exec', name, 'sha256sum', script_dest, capture=True).split()[0]
    if remote_sha != script_sha:
        raise Stop('guest bootstrap code SHA mismatch')
    execute(runner, name, 'python3', script_dest, '--bundle', destination,
            '--expected-sha', manifest_sha)


def cli_path(runner: Runner, name: str) -> str | None:
    for candidate in PINNED:
        result = runner.sbx('exec', name, 'bash', '-c',
                            'if test -x "$1"; then "$1" --version; fi',
                            'oc2', candidate, capture=True).strip()
        if result == 'opencode v' + VERSION:
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
    version = runner.sbx('exec', source, 'bash', '-c',
                         'if test -x "$1"; then "$1" --version; fi',
                         'oc2', binary, capture=True).strip()
    if version != 'opencode v' + VERSION:
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
    runtime = f'{ROOT}/runtime/{digest[:16]}'
    # Fixed bash command; only validated SHA and fixed executable paths are
    # interpolated. No local shell config / credentials are inherited.
    command = '''
set -eu
R="$1"
BIN="$2"
test -s "$R/config/opencode/opencode.jsonc"
cd "$R/project"
exec env -i HOME="$R/home" USER=agent SHELL=/bin/bash \
 PATH=/usr/local/bin:/usr/bin:/bin TERM="${TERM:-xterm-256color}" LANG=C.UTF-8 \
 XDG_CONFIG_HOME="$R/config" XDG_DATA_HOME="$R/data" \
 XDG_STATE_HOME="$R/state" XDG_CACHE_HOME="$R/cache" TMPDIR="$R/tmp" \
 OPENCODE_WATCHDOG_ENABLED=false OPENCODE_DISABLE_AUTOUPDATE=1 \
 OPENCODE_DISABLE_MODELS_FETCH=1 "$BIN" --standalone
'''
    runner.sbx('exec', '-it', name, 'bash', '-c', command, 'oc2', runtime, cli, tty=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=pathlib.Path, default=HERE.parents[1])
    p.add_argument('--sandbox', default='oc2-dev')
    p.add_argument('--sbx-user', default=os.getenv('OC2_SBX_USER', 'sbx-poc'))
    p.add_argument('--seed-sandbox', default=os.getenv('OC2_SEED_SANDBOX', 'oc-v2-poc'),
                   help='optional mountless PoC containing the pinned CLI; source is read-only')
    p.add_argument('--dry-run', action='store_true', help='show planned actions without writing or calling sbx')
    p.add_argument('--prepare-only', action='store_true', help='prepare config and CLI without opening TUI')
    args = p.parse_args(argv)
    try:
        if not NAME_RE.fullmatch(args.sandbox):
            raise Stop('invalid Sandbox name')
        if args.seed_sandbox and not NAME_RE.fullmatch(args.seed_sandbox):
            raise Stop('invalid seed Sandbox name')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.sbx_user):
            raise Stop('invalid Sandbox operator user')
        repo = args.repo_root.resolve(strict=True)
        if not (repo / 'apm.yml').is_file():
            raise Stop('dotfiles-ai apm.yml not found')
        if args.dry_run:
            print('OC2 PLAN: mountless sandbox=' + args.sandbox)
            print('OC2 PLAN: source=apm.yml; allowlist=shell,snapshot; no MCP/credentials')
            print('OC2 PLAN: export, stage, pinned CLI provision, --standalone TUI')
            return 0
        if not shutil.which('sbx'):
            # sbx can be installed only in operator PATH, so also check via sudo.
            if args.sbx_user == getpass.getuser():
                raise Stop('sbx CLI was not found')
        guest_script = HERE / 'oc2_guest.py'
        with tempfile.TemporaryDirectory(prefix='oc2-export-') as temp:
            tmp = pathlib.Path(temp)
            tmp.chmod(0o755)
            bundle, digest = export_config(repo, tmp / 'bundle')
            code = tmp / 'oc2_guest.py'
            shutil.copyfile(guest_script, code)
            code.chmod(0o644)
            runner = Runner(args.sbx_user)
            if not is_compatible_sandbox(runner, args.sandbox):
                print('OC2: creating mountless shell Sandbox ' + args.sandbox)
                runner.sbx('create', '--name', args.sandbox, 'shell')
            else:
                print('OC2: reusing verified mountless Sandbox ' + args.sandbox)
            stage(runner, args.sandbox, bundle, digest, code)
            cli = provision_cli(runner, args.sandbox, args.seed_sandbox, tmp)
            print('OC2_PREPARED: sandbox=' + args.sandbox + ' config_sha=' + digest[:16])
            if not args.prepare_only:
                launch(runner, args.sandbox, digest, cli)
        return 0
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # No credentials, source config, or raw subprocess dumps on failure.
        print('OC2_STOP: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
