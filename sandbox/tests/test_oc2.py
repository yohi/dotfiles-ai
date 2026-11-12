"""Offline tests for the host launcher and guest config materializer.

No sbx, sudo, network, package installation, or OpenCode binary is invoked.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

import yaml

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    if spec is None or spec.loader is None:
        raise ImportError(f'could not load module: {name}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oc2 = load('oc2')
oauth_bundle = load('oc2_oauth_bundle')
guest = load('oc2_guest')
assets = load('oc2_assets')
native = load('oc2_native')
bootstrap = load('oc2_oauth_bootstrap')
oauth = load('oc2_oauth')


class FakeRunner:
    def __init__(self, rows=None, inspection=None):
        self.rows = rows or []
        self.inspection = (
            {'name': 'oc2-dev', 'runtime_mounts': []}
            if inspection is None else inspection
        )
        self.calls = []
        self.workspace_copies = []
        self.remote_files = {}
        self.destination_states = {}

    def destination_status(self, name, destination):
        self.calls.append(('destination_status', name, destination))
        if destination in self.destination_states:
            return self.destination_states[destination]
        remote = name + ':' + destination
        return 10 if any(target == remote for _, target in self.workspace_copies) else 0

    def sbx(self, *args, **kwargs):
        self.calls.append(args)
        if args == ('ls', '-q'):
            return '\n'.join(row['name'] for row in self.rows)
        if args == ('ls', '--format', 'json'):
            return json.dumps(self.rows)
        if args == ('inspect', 'oc2-dev', '--json'):
            return json.dumps(self.inspection)
        if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
            remote_file = args[3]
            for source, destination in self.workspace_copies:
                if source.is_file() and remote_file == destination.split(':', 1)[1]:
                    return hashlib.sha256(source.read_bytes()).hexdigest() + '  ' + remote_file + '\n'
                prefix = destination.split(':', 1)[1] + '/'
                if remote_file.startswith(prefix):
                    relative = remote_file[len(prefix):]
                    data = (source / relative).read_bytes()
                    return hashlib.sha256(data).hexdigest() + '  ' + relative + '\n'
            return '0' * 64 + ' /tmp/file\n'
        if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
            return 'missing\n'
        if args[0] == 'cp' and len(args) == 3:
            self.workspace_copies.append((pathlib.Path(args[1]), args[2]))
        return ''


class FakeSecretRunner:
    def __init__(self, sandbox_scope=None, global_scope=None,
                 *, set_fails=False, store_after_set=True,
                 sandbox_service='cloudflare-ai-gateway', sandbox_type='service',
                 sandbox_listing=None, global_listing=None, list_fails=False):
        self.sandbox_scope = sandbox_scope
        self.global_scope = global_scope
        self.set_fails = set_fails
        self.store_after_set = store_after_set
        self.sandbox_service = sandbox_service
        self.sandbox_type = sandbox_type
        self.sandbox_listing_override = sandbox_listing
        self.global_listing_override = global_listing
        self.list_fails = list_fails
        self.calls = []

    @staticmethod
    def listing(scope, service='cloudflare-ai-gateway', secret_type='service'):
        secrets = []
        if scope is not None:
            secrets.append({
                'name': service,
                'scope': scope,
                'secret': '(stored)',
                'type': secret_type,
            })
        return json.dumps({'secrets': secrets})

    def sbx(self, *args, capture=False, tty=False):
        self.calls.append((args, capture, tty))
        if args == (
            'secret', 'ls', '--sandbox', 'oc2-dev',
            '--service', 'cloudflare-ai-gateway', '--json',
        ):
            if self.list_fails:
                raise oc2.Stop('sbx command failed (exit 1)')
            if self.sandbox_listing_override is not None:
                return self.sandbox_listing_override
            return self.listing(self.sandbox_scope, self.sandbox_service, self.sandbox_type)
        if args == (
            'secret', 'ls', '--global', '--service', 'cloudflare-ai-gateway', '--json',
        ):
            if self.list_fails:
                raise oc2.Stop('sbx command failed (exit 1)')
            if self.global_listing_override is not None:
                return self.global_listing_override
            return self.listing(self.global_scope)
        if args == ('secret', 'set', 'cloudflare-ai-gateway', '--sandbox', 'oc2-dev'):
            if self.set_fails:
                raise oc2.Stop('sbx command failed (exit 1)')
            if self.store_after_set:
                self.sandbox_scope = 'oc2-dev'
            return ''
        raise AssertionError(f'unexpected FakeRunner command: {args!r}')


class HostTest(unittest.TestCase):
    def run_guest_wrapper(self, guest_environment, runtime_environment=()):
        target = (
            'import json, os; '
            'print(json.dumps(dict(os.environ), sort_keys=True))'
        )
        command = [
            sys.executable, '-c', oc2.GUEST_EXEC_WRAPPER, '--',
            *runtime_environment, '--', sys.executable, '-c', target,
        ]
        return subprocess.run(
            command, capture_output=True, text=True, check=False,
            env=guest_environment,
        )

    def test_guest_wrapper_prefers_guest_proxy_and_discards_other_environment(self):
        guest_environment = {
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'http://guest-proxy.example.test:8080',
            'GUEST_SECRET': 'guest-poison-value',
        }
        with patch.dict(os.environ, {
            'HTTPS_PROXY': 'http://host-proxy.example.test:8080',
            'HOST_SECRET': 'host-poison-value',
        }):
            result = self.run_guest_wrapper(
                guest_environment, ('HOME=/runtime/home', 'OPENCODE_DB=/runtime/db'),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        child_environment = json.loads(result.stdout)
        self.assertEqual(
            child_environment['HTTPS_PROXY'],
            'http://guest-proxy.example.test:8080',
        )
        self.assertEqual(child_environment['HOME'], '/runtime/home')
        self.assertEqual(child_environment['OPENCODE_DB'], '/runtime/db')
        self.assertNotIn('HOST_SECRET', child_environment)
        self.assertNotIn('GUEST_SECRET', child_environment)

    def test_guest_wrapper_fails_closed_when_only_host_has_https_proxy(self):
        with patch.dict(os.environ, {
            'HTTPS_PROXY': 'http://host-proxy.example.test:8080',
        }):
            result = self.run_guest_wrapper({'PATH': os.environ['PATH']})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('host-proxy.example.test', result.stderr)

    def test_guest_wrapper_rejects_invalid_guest_proxy_without_logging_value(self):
        invalid_proxy = 'http://user:secret@guest-proxy.example.test:8080'
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': invalid_proxy,
        })

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(invalid_proxy, result.stdout + result.stderr)

    def test_guest_wrapper_rejects_unsupported_proxy_scheme(self):
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'file:///tmp/proxy.sock',
        })

        self.assertNotEqual(result.returncode, 0)

    def test_guest_wrapper_rejects_credentials_in_optional_http_proxy(self):
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'http://guest-proxy.example.test:8080',
            'HTTP_PROXY': 'http://user:secret@guest-proxy.example.test:8080',
        })

        self.assertNotEqual(result.returncode, 0)

    def test_guest_wrapper_rejects_conflicting_case_variants(self):
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'http://one.example.test:8080',
            'https_proxy': 'http://two.example.test:8080',
        })

        self.assertNotEqual(result.returncode, 0)

    def test_guest_wrapper_rejects_openai_host_in_no_proxy(self):
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'http://guest-proxy.example.test:8080',
            'NO_PROXY': 'localhost,chatgpt.com',
        })

        self.assertNotEqual(result.returncode, 0)

    def test_guest_wrapper_accepts_gateway_docker_internal_exact_no_proxy(self):
        no_proxy = 'localhost,127.0.0.1,::1,gateway.docker.internal'
        result = self.run_guest_wrapper({
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': 'http://guest-proxy.example.test:8080',
            'NO_PROXY': no_proxy,
        })

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['NO_PROXY'], no_proxy)

    def test_guest_wrapper_rejects_nonexact_or_unsafe_no_proxy_entries(self):
        for no_proxy in (
            '.gateway.docker.internal',
            'evil.gateway.docker.internal',
            '*.docker.internal',
            '*',
            'openai.com',
            'gateway.docker.internal,chatgpt.com',
        ):
            with self.subTest(no_proxy=no_proxy):
                result = self.run_guest_wrapper({
                    'PATH': os.environ['PATH'],
                    'HTTPS_PROXY': 'http://guest-proxy.example.test:8080',
                    'NO_PROXY': no_proxy,
                })

                self.assertNotEqual(result.returncode, 0)

    def test_launch_uses_guest_wrapper_for_both_processes_without_host_proxy_values(self):
        runner = FakeRunner()
        request = oc2.SandboxLaunch(
            'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
            pathlib.Path('/tmp/config'),
        )
        with patch.dict(os.environ, {
            'HTTPS_PROXY': 'http://host-proxy.example.test:8080',
            'SENSITIVE_FAKE_KEY': 'host-poison-value',
        }, clear=True):
            oc2.launch(runner, request)

        auth, tui = runner.calls[-2:]
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, auth)
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, tui)
        self.assertNotIn('host-proxy.example.test', repr(runner.calls))
        self.assertNotIn('host-poison-value', repr(runner.calls))
        self.assertEqual(auth[4:6], ('python3', '-c'))
        self.assertNotIn('-i', auth)
        self.assertNotIn('-i', tui)

    def test_launch_transfers_and_guest_verifies_selected_assets(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            assets_file = pathlib.Path(temporary) / 'assets.json'
            assets_file.write_text('{}')
            digest = hashlib.sha256(assets_file.read_bytes()).hexdigest()
            guest_sha = hashlib.sha256((SCRIPTS / 'oc2_guest.py').read_bytes()).hexdigest()
            native_sha = hashlib.sha256((SCRIPTS / 'oc2_agent_native.py').read_bytes()).hexdigest()
            verifier_dir = f'{oc2.ROOT}/scripts/oc2_guest_{guest_sha[:16]}_{native_sha[:16]}'
            oc2.launch(runner, oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
                pathlib.Path('/tmp/config'), assets_file=assets_file, assets_sha=digest,
            ))
        copied = {call[2] for call in runner.calls if call[0] == 'cp'}
        self.assertTrue(any('/assets/' in target for target in copied))
        self.assertIn(f'oc2-dev:{verifier_dir}/oc2_guest.py', copied)
        self.assertIn(f'oc2-dev:{verifier_dir}/oc2_agent_native.py', copied)
        self.assertTrue(any(target.endswith('/oc2_agent_native.py')
                            for target in copied))
        verify_call = next(call for call in runner.calls if '--install-assets-runtime' in call)
        self.assertIn('--expected-assets-sha', verify_call)
        self.assertIn('a' * 64, verify_call)

    def test_launch_reuses_preexisting_files_only_after_matching_sha(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            assets_file = pathlib.Path(temporary) / 'assets.json'
            assets_file.write_text('{}')
            digest = hashlib.sha256(assets_file.read_bytes()).hexdigest()
            script = oc2.HERE / 'oc2_guest.py'
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            native_helper = oc2.HERE / 'oc2_agent_native.py'
            native_sha = hashlib.sha256(native_helper.read_bytes()).hexdigest()
            verifier_dir = f'{oc2.ROOT}/scripts/oc2_guest_{script_sha[:16]}_{native_sha[:16]}'
            runner.workspace_copies.extend((
                (assets_file, f'oc2-dev:{oc2.ROOT}/assets/{digest[:16]}.json'),
                (script, f'oc2-dev:{verifier_dir}/oc2_guest.py'),
                (native_helper, f'oc2-dev:{verifier_dir}/oc2_agent_native.py'),
            ))

            oc2.launch(runner, oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
                pathlib.Path('/tmp/config'), assets_file=assets_file, assets_sha=digest,
            ))

        copied_targets = {call[2] for call in runner.calls if call[0] == 'cp'}
        self.assertFalse(any('/assets/' in target or '/scripts/oc2_guest_' in target
                             or target.endswith('/oc2_agent_native.py')
                             for target in copied_targets))

    def test_launch_fails_closed_for_unsafe_and_unknown_asset_probe_states(self):
        for target_kind in ('asset', 'verifier', 'native-helper'):
            for status in (1, 11, 12, 99):
                with self.subTest(target=target_kind, status=status), \
                        tempfile.TemporaryDirectory() as temporary:
                    runner = FakeRunner()
                    assets_file = pathlib.Path(temporary) / 'assets.json'
                    assets_file.write_text('{}')
                    digest = hashlib.sha256(assets_file.read_bytes()).hexdigest()
                    script_sha = hashlib.sha256((oc2.HERE / 'oc2_guest.py').read_bytes()).hexdigest()
                    native_sha = hashlib.sha256(
                        (oc2.HERE / 'oc2_agent_native.py').read_bytes(),
                    ).hexdigest()
                    verifier_dir = (
                        f'{oc2.ROOT}/scripts/oc2_guest_{script_sha[:16]}_{native_sha[:16]}'
                    )
                    path = (
                        f'{oc2.ROOT}/assets/{digest[:16]}.json'
                        if target_kind == 'asset'
                        else f'{verifier_dir}/oc2_guest.py'
                        if target_kind == 'verifier'
                        else f'{verifier_dir}/oc2_agent_native.py'
                    )
                    runner.destination_states[path] = status

                    with self.assertRaises(oc2.Stop):
                        oc2.launch(runner, oc2.SandboxLaunch(
                            'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
                            pathlib.Path('/tmp/config'), assets_file=assets_file,
                            assets_sha=digest,
                        ))
                    copied_targets = {call[2] for call in runner.calls if call[0] == 'cp'}
                    if target_kind == 'asset':
                        self.assertFalse(any('/assets/' in target for target in copied_targets))
                    elif target_kind == 'native-helper':
                        self.assertFalse(any(target.endswith('/oc2_agent_native.py')
                                             for target in copied_targets))
                    else:
                        self.assertFalse(any('/scripts/oc2_guest_' in target
                                             for target in copied_targets))

    def test_launch_rejects_existing_asset_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = FakeRunner()
            assets_file = pathlib.Path(temporary) / 'assets.json'
            assets_file.write_text('{}')
            digest = hashlib.sha256(assets_file.read_bytes()).hexdigest()
            runner.destination_states[f'{oc2.ROOT}/assets/{digest[:16]}.json'] = 10

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.launch(runner, oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
                    pathlib.Path('/tmp/config'), assets_file=assets_file, assets_sha=digest,
                ))
            self.assertFalse(any(call[0] == 'cp' and '/assets/' in call[2]
                                 for call in runner.calls))

    def test_launch_rejects_existing_verifier_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = FakeRunner()
            assets_file = pathlib.Path(temporary) / 'assets.json'
            assets_file.write_text('{}')
            digest = hashlib.sha256(assets_file.read_bytes()).hexdigest()
            script_sha = hashlib.sha256((oc2.HERE / 'oc2_guest.py').read_bytes()).hexdigest()
            native_sha = hashlib.sha256((oc2.HERE / 'oc2_agent_native.py').read_bytes()).hexdigest()
            verifier_dir = f'{oc2.ROOT}/scripts/oc2_guest_{script_sha[:16]}_{native_sha[:16]}'
            remote_script = f'{verifier_dir}/oc2_guest.py'
            stale_script = pathlib.Path(temporary) / 'stale-guest.py'
            stale_script.write_text('unapproved verifier\n')
            runner.workspace_copies.append((
                stale_script, f'oc2-dev:{remote_script}',
            ))
            runner.destination_states[remote_script] = 10

            with self.assertRaisesRegex(oc2.Stop, 'asset verifier SHA mismatch'):
                oc2.launch(runner, oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], '/workspace/project',
                    pathlib.Path('/tmp/config'), assets_file=assets_file, assets_sha=digest,
                ))
            self.assertFalse(any(call[0] == 'cp' and '/scripts/oc2_guest_' in call[2]
                                 for call in runner.calls))

    def test_cloudflare_credential_accepts_existing_sandbox_scope(self):
        runner = FakeSecretRunner(sandbox_scope='oc2-dev', global_scope='(global)')

        scope = oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertEqual(scope, 'sandbox')
        self.assertEqual(
            runner.calls,
            [(('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
               'cloudflare-ai-gateway', '--json'), True, False)],
        )

    def test_cloudflare_credential_accepts_existing_global_scope_without_changes(self):
        runner = FakeSecretRunner(global_scope='(global)')

        scope = oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertEqual(scope, 'global')
        self.assertEqual(
            runner.calls,
            [
                (('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
                  'cloudflare-ai-gateway', '--json'), True, False),
                (('secret', 'ls', '--global', '--service',
                  'cloudflare-ai-gateway', '--json'), True, False),
            ],
        )

    def test_cloudflare_credential_rejects_sandbox_scope_in_global_listing(self):
        runner = FakeSecretRunner(global_scope='oc2-dev')

        with self.assertRaisesRegex(oc2.Stop, 'scope'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertFalse(any(call[0][:2] == ('secret', 'set') for call in runner.calls))

    def test_cloudflare_credential_missing_without_terminal_fails_closed(self):
        runner = FakeSecretRunner()

        with self.assertRaisesRegex(oc2.Stop, 'interactive terminal'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
                 'cloudflare-ai-gateway', '--json'),
                ('secret', 'ls', '--global', '--service',
                 'cloudflare-ai-gateway', '--json'),
            ],
        )
        self.assertFalse(any(call[0][:2] == ('secret', 'set') for call in runner.calls))

    def test_cloudflare_credential_missing_with_terminal_sets_and_verifies_scope(self):
        runner = FakeSecretRunner()

        scope = oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertEqual(scope, 'sandbox')
        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
                 'cloudflare-ai-gateway', '--json'),
                ('secret', 'ls', '--global', '--service',
                 'cloudflare-ai-gateway', '--json'),
                ('secret', 'set', 'cloudflare-ai-gateway', '--sandbox', 'oc2-dev'),
                ('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
                 'cloudflare-ai-gateway', '--json'),
            ],
        )
        self.assertEqual(runner.calls[2][1:], (False, True))

    def test_cloudflare_credential_set_failure_stops_before_verification(self):
        runner = FakeSecretRunner(set_fails=True)

        with self.assertRaisesRegex(oc2.Stop, 'sbx command failed'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(runner.calls[-1][0][0:2], ('secret', 'set'))

    def test_cloudflare_credential_unverified_after_set_fails_closed(self):
        runner = FakeSecretRunner(store_after_set=False)

        with self.assertRaisesRegex(oc2.Stop, 'not verified'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertEqual(
            runner.calls[-1][0],
            ('secret', 'ls', '--sandbox', 'oc2-dev', '--service',
             'cloudflare-ai-gateway', '--json'),
        )

    def test_cloudflare_credential_malformed_listing_fails_closed(self):
        malformed_listings = (
            '',
            'not-json',
            '{}',
            '{"secrets":null}',
            '{"secrets":{}}',
            '{"secrets":[{"name":"cloudflare-ai-gateway"}]}',
            '{"secrets":[{"name":"cloudflare-ai-gateway","scope":"oc2-dev",'
            '"secret":"(stored)","type":"service","extra":true}]}',
        )
        for listing in malformed_listings:
            with self.subTest(listing=listing):
                runner = FakeSecretRunner(sandbox_listing=listing)
                with self.assertRaisesRegex(oc2.Stop, 'JSON|schema'):
                    oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)
                self.assertFalse(
                    any(call[0][:2] == ('secret', 'set') for call in runner.calls),
                )

    def test_cloudflare_credential_ignores_different_service_name(self):
        runner = FakeSecretRunner(
            sandbox_scope='oc2-dev', sandbox_service='another-service',
        )

        with self.assertRaisesRegex(oc2.Stop, 'interactive terminal'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertFalse(any(call[0][:2] == ('secret', 'set') for call in runner.calls))

    def test_cloudflare_credential_rejects_unknown_secret_type(self):
        runner = FakeSecretRunner(sandbox_scope='oc2-dev', sandbox_type='registry')

        with self.assertRaisesRegex(oc2.Stop, 'type'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertFalse(any(call[0][:2] == ('secret', 'set') for call in runner.calls))

    def test_cloudflare_credential_list_command_failure_is_not_empty_list(self):
        runner = FakeSecretRunner(list_fails=True)

        with self.assertRaisesRegex(oc2.Stop, 'could not be checked'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertEqual(len(runner.calls), 1)

    def test_destination_guest_exit_codes_for_real_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = pathlib.Path(tmp) / 'parent'
            parent.mkdir()
            candidate = parent / 'target'
            def check(path):
                return subprocess.run([sys.executable, '-c', oc2.DESTINATION_CHECK_SCRIPT, str(path)], capture_output=True, check=False).returncode
            self.assertEqual(check(candidate), 0)
            candidate.write_text('existing')
            self.assertEqual(check(candidate), 10)
            candidate.unlink()
            candidate.mkdir()
            self.assertEqual(check(candidate), 12)
            candidate.rmdir()
            candidate.symlink_to(parent / 'missing')
            self.assertEqual(check(candidate), 12)
            candidate.unlink()
            os.mkfifo(candidate)
            self.assertEqual(check(candidate), 12)
            candidate.unlink()
            link = pathlib.Path(tmp) / 'link'
            link.symlink_to(parent, target_is_directory=True)
            self.assertEqual(check(link / 'target'), 12)
            self.assertEqual(check(pathlib.Path(tmp) / 'missing' / 'target'), 11)
            self.assertEqual(check(pathlib.Path('relative')), 12)

    def test_destination_guest_permission_error_is_indeterminate(self):
        program = (
            'import os, sys\n'
            'def deny(*args, **kwargs): raise PermissionError(13, "denied")\n'
            'os.open = deny\n'
            'exec(' + repr(oc2.DESTINATION_CHECK_SCRIPT) + ')\n'
        )
        result = subprocess.run([sys.executable, '-c', program, '/safe/target'],
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 11)

    def test_destination_status_uses_exit_code_not_output(self):
        runner = oc2.Runner(oc2.getpass.getuser())
        for status in (0, 10, 11, 12, 23):
            with self.subTest(status=status), patch.object(
                oc2.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], status, b'missing\nSandbox notification', b'warning',
                ),
            ):
                self.assertEqual(runner.destination_status('oc2-dev', '/safe/target'), status)

    def test_destination_status_timeout_fails_closed(self):
        runner = oc2.Runner(oc2.getpass.getuser())
        with patch.object(oc2.subprocess, 'run', side_effect=subprocess.TimeoutExpired('sbx', 180)):
            with self.assertRaisesRegex(oc2.Stop, 'DESTINATION_CHECK_TIMEOUT'):
                runner.destination_status('oc2-dev', '/safe/target')
    def test_inline_module_source_loads_embedded_python_module(self):
        loader = oauth_bundle.inline_python_module('oc2_embedded_fixture', 'value = 42\n')
        program = loader + '\nimport oc2_embedded_fixture\nprint(oc2_embedded_fixture.value)\n'
        result = subprocess.run([sys.executable, '-c', program], capture_output=True,
                                text=True, check=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '42')

    def test_oauth_helper_bundle_compiles(self):
        source = oauth_bundle.oauth_helper_source(SCRIPTS)

        compile(source, '<oc2-oauth-helper>', 'exec')

    def test_launch_stops_before_tui_when_auth_identity_check_fails(self):
        class AuthFailureRunner(FakeRunner):
            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                if 'oc2_oauth.py' in ' '.join(args):
                    raise oc2.Stop('authentication failed')
                return ''

        runner = AuthFailureRunner()
        request = oc2.SandboxLaunch('oc2-dev', 'a' * 64, oc2.PINNED[0],
                                    '/workspace/project', pathlib.Path('/tmp/config'))
        with self.assertRaises(oc2.Stop):
            oc2.launch(runner, request)
        self.assertFalse(any('-it' in call for call in runner.calls))

    def test_mountless_sandbox_create_omits_host_workspace_path(self):
        self.assertEqual(
            oc2.mountless_create_args(
                'oc2-safe', pathlib.Path('/tmp/oc2-credential-mixin'),
                pathlib.Path('/tmp/oc2-runtime-mixin'),
            ),
            [
                'create', '--name', 'oc2-safe',
                '--kit', '/tmp/oc2-credential-mixin',
                '--kit', '/tmp/oc2-runtime-mixin',
                oc2.SHELL_WORKLOAD,
            ],
        )

    def test_workspace_snapshot_excludes_project_config_and_git_metadata(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            (root / 'opencode.json').write_text('{"mcp":{"unsafe":true}}\n')
            (root / 'opencode.jsonc').write_text('{"model":"unsafe/model"}\n')
            (root / 'cli.json').write_text('{"theme":{"name":"unsafe"}}\n')
            (root / '.opencode').mkdir()
            (root / '.opencode' / 'opencode.jsonc').write_text('{"provider":"unsafe"}\n')
            (root / '.env').write_text('TOKEN=fixture-value')
            (root / '.git').mkdir()
            (root / '.git' / 'config').write_text('[remote "origin"]\n')

            manifest = workspace.snapshot(root)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])

    def test_workspace_snapshot_excludes_claude_json_from_guest_materialize(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'source'
            root.mkdir()
            (root / 'main.py').write_text('print("safe")\n')
            credential_config = root / '.claude.json'
            credential_config.write_text(
                '{"github_token":"ghp_' + 'A' * 24 + '"}\n'
            )
            original = credential_config.read_bytes()
            manifest = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            workspace.materialize(root, guest, manifest)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])
            self.assertEqual(sorted(path.name for path in guest.iterdir()), ['main.py'])
            self.assertEqual(credential_config.read_bytes(), original)

    def test_workspace_snapshot_keeps_nested_opencode_named_source_file(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            nested = root / 'src' / 'opencode.json'
            nested.parent.mkdir()
            nested.write_text('{"this":"is application data"}\n')

            manifest = workspace.snapshot(root)

            self.assertEqual([entry.path for entry in manifest.files], ['src/opencode.json'])

    def test_workspace_snapshot_excludes_local_generated_trees_and_claude_settings(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            for directory in ('.worktrees', '.nexus', 'apm_modules'):
                nested = root / directory / 'generated'
                nested.mkdir(parents=True)
                (nested / 'fixture.txt').write_text('api_key = "' + 'A' * 32 + '"\n')
            (root / 'claude').mkdir()
            (root / 'claude' / 'settings.json').write_text(
                '{"github_token":"ghp_' + 'B' * 24 + '"}\n'
            )
            evals = root / '.agents/skills/agent-driven-setup/evals'
            evals.mkdir(parents=True)
            (evals / 'evals.json').write_text('api_key = "' + 'C' * 32 + '"\n')
            skill = root / '.agents/skills/agent-driven-setup/SKILL.md'
            skill.write_text('Safe skill content.\n')
            nested_app = root / 'src/apm_modules/application.py'
            nested_app.parent.mkdir(parents=True)
            nested_app.write_text('print("application module")\n')
            nested_config = root / 'src/claude/settings.json'
            nested_config.parent.mkdir(parents=True)
            nested_config.write_text('{"application":"settings"}\n')

            manifest = workspace.snapshot(root)

            self.assertEqual(
                [entry.path for entry in manifest.files],
                ['.agents/skills/agent-driven-setup/SKILL.md', 'main.py',
                 'src/apm_modules/application.py', 'src/claude/settings.json'],
            )

    def test_workspace_profile_excludes_apm_and_restricted_dotfiles_artifacts(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            (root / 'apm.yml').write_text('apiKey: ' + 'A' * 32 + '\n')
            for relative in (
                '_docs/aws-resource-inventory.md',
                '_scripts/generate_atlassian_auth.py',
                '.agents/skills/claude-api/csharp/claude-api/README.md',
                'sandbox/tests/test_v2_provider_security.py',
                'OC2_CF_G4_PLACEHOLDER_LOOKUP_R2_20261103 (1).zip',
                'OC2_CLOUDFLARE_R1_OFFLINE_CANDIDATE_20261103.zip',
                'OC2_REMOVE_OMO_R2_VERIFICATION_KIT_20261103.zip',
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('apiKey: ' + 'B' * 32 + '\n')

            manifest = workspace.snapshot(root, profile=workspace.DOTFILES_AI_PROFILE)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])
            self.assertEqual(manifest.profile_id, 'dotfiles-ai/workspace-safe-transfer/r1')

    def test_workspace_profile_is_not_applied_to_an_unrelated_repository(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'apm.yml').write_text('provider: safe\n')

            manifest = workspace.snapshot(root)

            self.assertEqual([entry.path for entry in manifest.files], ['apm.yml'])
            self.assertIsNone(manifest.profile_id)

    def test_workspace_profile_manifest_rejects_reintroduced_apm_path(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            manifest = workspace.snapshot(root, profile=workspace.DOTFILES_AI_PROFILE)
            payload = json.loads(manifest.encode())
            payload['files'].append({
                'path': 'apm.yml',
                'size': 0,
                'sha256': hashlib.sha256(b'').hexdigest(),
            })
            payload['files'].sort(key=lambda entry: entry['path'])

            with self.assertRaisesRegex(workspace.WorkspaceError, 'unsafe or excluded'):
                workspace.decode_manifest(json.dumps(payload).encode(), root)

    def test_workspace_profile_omits_new_apm_from_guest_changes_and_apply(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            host = pathlib.Path(tmp) / 'host'
            guest = pathlib.Path(tmp) / 'guest'
            host.mkdir()
            (host / 'main.py').write_text('print("safe")\n')
            (host / 'apm.yml').write_text('host-only APM source\n')
            baseline = workspace.snapshot(host, profile=workspace.DOTFILES_AI_PROFILE)
            workspace.materialize(host, guest, baseline, for_guest=True)
            self.assertFalse((guest / 'apm.yml').exists())
            (guest / 'apm.yml').write_text('new guest file\n')
            decoded = workspace.decode_manifest(baseline.encode(), host)

            self.assertEqual(workspace.changes(decoded, guest), ())
            self.assertEqual(
                workspace.apply_changes(host, guest, decoded, approved=True), (),
            )
            self.assertEqual((host / 'apm.yml').read_text(), 'host-only APM source\n')

    def test_workspace_profile_selector_requires_exact_github_repository_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(
                ['git', '-C', str(root), 'remote', 'add', 'origin',
                 'git@github.com:yohi/dotfiles-ai.git'],
                check=True,
            )

            profile = oc2.workspace_transfer_profile(root)

            self.assertEqual(profile, 'dotfiles-ai/workspace-safe-transfer/r1')

            subprocess.run(
                ['git', '-C', str(root), 'remote', 'set-url', 'origin',
                 'git@github.com:other/dotfiles-ai.git'],
                check=True,
            )
            self.assertIsNone(oc2.workspace_transfer_profile(root))

    def test_workspace_profile_excludes_known_symlink_adapters_without_following(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'repo'
            root.mkdir()
            outside = pathlib.Path(tmp) / 'external.mk'
            outside.write_text('not transferred\n')
            (root / '_mk').mkdir()
            (root / '_mk' / 'core.mk').symlink_to(outside)
            (root / 'main.py').write_text('print("safe")\n')

            manifest = workspace.snapshot(root, profile=workspace.DOTFILES_AI_PROFILE)
            guest = pathlib.Path(tmp) / 'guest'
            workspace.materialize(root, guest, manifest)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])
            self.assertFalse((guest / '_mk' / 'core.mk').exists())
            self.assertTrue(outside.exists())

    def test_opencode_cli_mixin_uses_local_standalone_binary(self):
        self.assertEqual(oc2.VERSION, '2.2.5')
        spec = yaml.safe_load(oc2.opencode_cli_mixin_spec())

        self.assertEqual(spec['schemaVersion'], '3')
        self.assertEqual(spec['kind'], 'mixin')
        self.assertEqual(spec['provides'], ['opencode-cli@2.2.5'])
        self.assertIn('FROM scratch', spec['build'])
        self.assertIn(
            'COPY --chmod=0755 opencode '
            '/opt/oc2/bin/opencode',
            spec['build'],
        )
        self.assertNotIn('npm', spec['build'])
        self.assertNotIn('node:', spec['build'])
        self.assertEqual(oc2.PINNED, ('/opt/oc2/bin/opencode',))
        self.assertNotIn('/home/agent', spec['build'])

    def test_official_cli_download_verifies_digest_and_extracts_binary(self):
        binary = b'verified but not executed'
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
            member = tarfile.TarInfo('opencode')
            member.size = len(binary)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(binary))
        payload = archive_buffer.getvalue()
        official_url = (
            'https://github.com/anomalyco/opencode/releases/download/v2.2.5/'
            'opencode-linux-x64.tar.gz'
        )

        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / 'private'
            destination.mkdir(mode=0o700)

            def fake_curl(command, **kwargs):
                pathlib.Path(command[command.index('--output') + 1]).write_bytes(payload)
                stdout = f'OC2_HTTP_STATUS=200\nOC2_FINAL_URL={official_url}\n'
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

            with (
                patch.object(oc2.shutil, 'which', return_value='/usr/bin/curl'),
                patch.object(oc2.subprocess, 'run', side_effect=fake_curl),
                patch.object(oc2, 'CLI_ASSET_SIZE', len(payload)),
                patch.object(oc2, 'CLI_ASSET_SHA256', hashlib.sha256(payload).hexdigest()),
                patch.object(oc2, 'CLI_BINARY_SIZE', len(binary)),
            ):
                result = oc2.download_verified_cli(destination)

            self.assertEqual(result.read_bytes(), binary)
            self.assertEqual(result.name, 'opencode')
            self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o600)
            self.assertEqual(sorted(path.name for path in destination.iterdir()), ['opencode'])

    def test_official_cli_download_rejects_digest_mismatch(self):
        binary = b'fixture'
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
            member = tarfile.TarInfo('opencode')
            member.size = len(binary)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(binary))
        payload = archive_buffer.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / 'private'
            destination.mkdir(mode=0o700)

            def fake_curl(command, **kwargs):
                pathlib.Path(command[command.index('--output') + 1]).write_bytes(payload)
                stdout = 'OC2_HTTP_STATUS=200\nOC2_FINAL_URL=https://github.com/anomalyco/opencode/release\n'
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

            with (
                patch.object(oc2.shutil, 'which', return_value='/usr/bin/curl'),
                patch.object(oc2.subprocess, 'run', side_effect=fake_curl),
                patch.object(oc2, 'CLI_ASSET_SIZE', len(payload)),
                patch.object(oc2, 'CLI_ASSET_SHA256', '0' * 64),
                patch.object(oc2, 'CLI_BINARY_SIZE', len(binary)),
            ):
                with self.assertRaisesRegex(oc2.Stop, 'integrity verification failed'):
                    oc2.download_verified_cli(destination)

            self.assertEqual(list(destination.iterdir()), [])

    def test_official_cli_download_rejects_unsafe_archive_path(self):
        binary = b'fixture'
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
            member = tarfile.TarInfo('../opencode')
            member.size = len(binary)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(binary))
        payload = archive_buffer.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / 'private'
            destination.mkdir(mode=0o700)

            def fake_curl(command, **kwargs):
                pathlib.Path(command[command.index('--output') + 1]).write_bytes(payload)
                stdout = 'OC2_HTTP_STATUS=200\nOC2_FINAL_URL=https://github.com/anomalyco/opencode/release\n'
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

            with (
                patch.object(oc2.shutil, 'which', return_value='/usr/bin/curl'),
                patch.object(oc2.subprocess, 'run', side_effect=fake_curl),
                patch.object(oc2, 'CLI_ASSET_SIZE', len(payload)),
                patch.object(oc2, 'CLI_ASSET_SHA256', hashlib.sha256(payload).hexdigest()),
                patch.object(oc2, 'CLI_BINARY_SIZE', len(binary)),
            ):
                with self.assertRaisesRegex(oc2.Stop, 'archive contents are invalid'):
                    oc2.download_verified_cli(destination)

            self.assertEqual(list(destination.iterdir()), [])

    def test_official_cli_download_rejects_untrusted_redirect_host(self):
        binary = b'fixture'
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
            member = tarfile.TarInfo('opencode')
            member.size = len(binary)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(binary))
        payload = archive_buffer.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / 'private'
            destination.mkdir(mode=0o700)

            def fake_curl(command, **kwargs):
                pathlib.Path(command[command.index('--output') + 1]).write_bytes(payload)
                stdout = (
                    'OC2_HTTP_STATUS=200\n'
                    'OC2_FINAL_URL=https://untrusted.example/opencode.tar.gz\n'
                )
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

            with (
                patch.object(oc2.shutil, 'which', return_value='/usr/bin/curl'),
                patch.object(oc2.subprocess, 'run', side_effect=fake_curl),
                patch.object(oc2, 'CLI_ASSET_SIZE', len(payload)),
                patch.object(oc2, 'CLI_ASSET_SHA256', hashlib.sha256(payload).hexdigest()),
                patch.object(oc2, 'CLI_BINARY_SIZE', len(binary)),
            ):
                with self.assertRaisesRegex(oc2.Stop, 'untrusted host'):
                    oc2.download_verified_cli(destination)

            self.assertEqual(list(destination.iterdir()), [])

    def test_official_cli_download_rejects_unsupported_host_architecture(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / 'private'
            destination.mkdir(mode=0o700)
            with (
                patch.object(oc2.platform, 'machine', return_value='aarch64'),
                patch.object(oc2.subprocess, 'run') as run,
            ):
                with self.assertRaisesRegex(oc2.Stop, 'Linux x86-64'):
                    oc2.download_verified_cli(destination)

            run.assert_not_called()

    def test_cli_provisioning_stops_without_kit_binary_and_never_runs_npm(self):
        runner = FakeRunner()

        with self.assertRaisesRegex(oc2.Stop, 'not present in the Sandbox kit'):
            oc2.provision_cli(runner, 'oc2-dev')

        self.assertFalse(any(call[2:4] == ('npm', 'install') for call in runner.calls))

    def test_workspace_snapshot_excludes_secrets_and_symlinks(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'src').mkdir()
            (root / 'src' / 'main.py').write_text('print(1)\n')
            (root / '.env').write_text('TOKEN=not-for-sandbox')
            manifest = workspace.snapshot(root)
            self.assertEqual([entry.path for entry in manifest.files], ['src/main.py'])
            self.assertNotIn('not-for-sandbox', repr(manifest))
            (root / 'linked').symlink_to(root / 'src' / 'main.py')
            with self.assertRaises(workspace.WorkspaceError):
                workspace.snapshot(root)

    def test_workspace_snapshot_rejects_embedded_credential_material(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'settings.py').write_text(
                'api_key = "' + '0123456789abcdef' * 2 + '"\n'
            )
            with self.assertRaisesRegex(workspace.WorkspaceError, 'credential material') as error:
                workspace.snapshot(root)
            self.assertEqual(
                str(error.exception),
                'workspace file appears to contain credential material',
            )
            (root / 'settings.py').write_text('api_key = "TOP_SECRET_DO_NOT_EXPORT"\n')
            manifest = workspace.snapshot(root)
            self.assertEqual([entry.path for entry in manifest.files], ['settings.py'])

    def test_workspace_snapshot_rejects_special_files(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            os.mkfifo(root / 'pipe')
            with self.assertRaisesRegex(workspace.WorkspaceError, 'special'):
                workspace.snapshot(root)

    def test_workspace_collect_rejects_host_conflicts_and_unapproved_apply(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            source = root / 'note.txt'
            source.write_text('original')
            baseline = workspace.snapshot(root)
            sandbox = pathlib.Path(tmp) / 'guest'
            sandbox.mkdir()
            (sandbox / 'note.txt').write_text('sandbox change')
            with self.assertRaises(workspace.WorkspaceError):
                workspace.apply_changes(root, sandbox, baseline, approved=False)
            source.write_text('host concurrent change')
            with self.assertRaisesRegex(workspace.WorkspaceError, 'conflict'):
                workspace.apply_changes(root, sandbox, baseline, approved=True)

    def test_workspace_snapshot_materializes_only_manifest_files(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'source'
            root.mkdir()
            (root / 'app.py').write_text('print("safe")\n')
            (root / '.env.production').write_text('SECRET=value')
            manifest = workspace.snapshot(root)
            stage = pathlib.Path(tmp) / 'stage'
            workspace.materialize(root, stage, manifest)
            self.assertEqual(sorted(item.name for item in stage.iterdir()), ['app.py'])
            self.assertEqual((stage / 'app.py').read_text(), 'print("safe")\n')

    def test_guest_snapshot_keeps_files_private_before_operator_acl(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'source'
            root.mkdir()
            source = root / 'app.py'
            source.write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            stage = pathlib.Path(tmp) / 'stage'
            workspace.materialize(root, stage, manifest, for_guest=True)
            self.assertEqual(stat.S_IMODE((stage / 'app.py').stat().st_mode), 0o600)

    def test_workspace_transfer_grants_only_operator_read_access(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            runner = FakeRunner()
            calls = []
            with patch.object(
                oc2, 'grant_snapshot_access',
                side_effect=lambda path, user: calls.append((path, user)),
                create=True,
            ):
                oc2.transfer_workspace(runner, 'oc2-dev', staged, manifest, 'sbx-poc')
            self.assertEqual(calls, [(staged, 'sbx-poc')])

    def test_snapshot_acl_is_limited_to_named_operator(self):
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(args=[], returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = pathlib.Path(tmp) / 'project'
            (snapshot / 'src').mkdir(parents=True)
            (snapshot / 'src' / 'main.py').write_text('print(1)\n')
            with patch.object(oc2.shutil, 'which', return_value='/usr/bin/setfacl'), \
                 patch.object(oc2.subprocess, 'run', return_value=result) as run:
                oc2.grant_snapshot_access(snapshot, 'sbx-poc')
            self.assertEqual(
                run.call_args_list[0].args[0],
                ['/usr/bin/setfacl', '-R', '-m', 'u:sbx-poc:r--', '--', str(snapshot)],
            )
            self.assertEqual(
                run.call_args_list[1].args[0],
                ['/usr/bin/setfacl', '-m', 'u:sbx-poc:r-x', '--',
                 str(snapshot), str(snapshot / 'src')],
            )

    def test_collection_acl_is_limited_to_private_temporary_directory(self):
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(args=[], returncode=0)
        with patch.object(oc2.shutil, 'which', return_value='/usr/bin/setfacl'), \
             patch.object(oc2.subprocess, 'run', return_value=result) as run:
            oc2.grant_collection_directory_access(
                pathlib.Path('/tmp/oc2-collect-x'), 'sbx-poc',
            )
        self.assertEqual(
            run.call_args.args[0],
            ['/usr/bin/setfacl', '-m', 'u:sbx-poc:rwx', '--',
             '/tmp/oc2-collect-x'],
        )

    def test_collection_read_acl_grants_host_user_access_only_to_returned_tree(self):
        with patch.object(oc2.shutil, 'which', side_effect=['/usr/bin/setfacl', '/usr/bin/find']), \
             patch.object(oc2, 'run_operator', return_value='') as run:
            oc2.grant_collected_workspace_access(
                pathlib.Path('/tmp/oc2-collect-x/incoming'),
                'sbx-poc',
                'test-user',
            )
        self.assertEqual(
            run.call_args_list[0].args,
            ('sbx-poc', '/usr/bin/setfacl', '-m', 'u:test-user:r-x', '--',
             '/tmp/oc2-collect-x/incoming'),
        )
        self.assertEqual(
            run.call_args_list[1].args,
            ('sbx-poc', '/usr/bin/find', '/tmp/oc2-collect-x/incoming',
             '-type', 'd', '-exec', '/usr/bin/setfacl', '-m', 'u:test-user:r-x',
             '--', '{}', '+'),
        )
        self.assertEqual(
            run.call_args_list[2].args,
            ('sbx-poc', '/usr/bin/find', '/tmp/oc2-collect-x/incoming',
             '-type', 'f', '-exec', '/usr/bin/setfacl', '-m', 'u:test-user:r--',
             '--', '{}', '+'),
        )

    def test_snapshot_acl_fails_closed_when_setfacl_is_missing(self):
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_snapshot_access(pathlib.Path('/tmp/oc2-stage/project'), 'sbx-poc')

    def test_workspace_transfer_stops_before_copy_if_private_acl_fails(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            runner = FakeRunner()
            with patch.object(oc2, 'grant_snapshot_access', side_effect=oc2.Stop('ACL denied')):
                with self.assertRaisesRegex(oc2.Stop, 'ACL denied'):
                    oc2.transfer_workspace(runner, 'oc2-dev', staged, manifest, 'sbx-poc')
            self.assertFalse(any(call[0] == 'cp' for call in runner.calls))

    def test_collection_acl_failure_stops_before_sandbox_copy(self):
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_collection_directory_access(
                    pathlib.Path('/tmp/oc2-collect-x'), 'sbx-poc',
                )

    def test_workspace_changes_apply_add_modify_and_require_delete_approval(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'keep.txt').write_text('old')
            (root / 'remove.txt').write_text('remove')
            baseline = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            workspace.materialize(root, guest, baseline)
            (guest / 'keep.txt').write_text('new')
            (guest / 'added.txt').write_text('added')
            (guest / 'remove.txt').unlink()
            with self.assertRaisesRegex(workspace.WorkspaceError, 'deletion approval'):
                workspace.apply_changes(root, guest, baseline, approved=True)
            result = workspace.apply_changes(
                root, guest, baseline, approved=True, allow_deletions=True,
            )
            self.assertEqual(result, ('added.txt', 'keep.txt', 'remove.txt'))
            self.assertEqual((root / 'keep.txt').read_text(), 'new')
            self.assertEqual((root / 'added.txt').read_text(), 'added')
            self.assertFalse((root / 'remove.txt').exists())

    def test_workspace_manifest_rejects_path_traversal(self):
        workspace = load('oc2_workspace')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'manifest path'):
            workspace.decode_manifest(
                b'{"schema":"dotfiles-ai/oc2-workspace/v1","files":'
                b'[{"path":"../outside","size":0,"sha256":"' + b'0' * 64 + b'"}]}',
                pathlib.Path('/tmp/workspace'),
            )

    def test_workspace_launcher_transfers_and_launches_in_project_directory(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("original")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            workspace.materialize(root, staged, manifest)
            runner = FakeRunner()
            with patch.object(oc2, 'grant_snapshot_access'):
                remote = oc2.transfer_workspace(
                    runner, 'oc2-dev', staged, manifest, 'sbx-poc',
                )
            self.assertEqual(remote, oc2.ROOT + '/projects/' + remote.rsplit('/', 1)[-1])
            self.assertEqual(runner.workspace_copies[0], (staged, 'oc2-dev:' + remote))
            oc2.launch(
                runner,
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], remote,
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )
            self.assertEqual(runner.calls[-1][3], remote)

    def test_destination_check_fails_closed_with_specific_reason(self):
        workspace = load('oc2_workspace')
        scenarios = (
            (subprocess.CompletedProcess([], 10, b'', b''), 'DESTINATION_EXISTS'),
            (subprocess.CompletedProcess([], 12, b'', b''), 'DESTINATION_EXISTS'),
            (subprocess.CompletedProcess([], 11, b'', b''), 'DESTINATION_CHECK_INDETERMINATE'),
            (subprocess.CompletedProcess([], 17, b'', b'private stderr'), 'DESTINATION_CHECK_COMMAND_FAILED'),
            (subprocess.CompletedProcess([], 125, b'', b''), 'DESTINATION_CHECK_COMMAND_FAILED'),
            (subprocess.CompletedProcess([], 127, b'', b''), 'DESTINATION_CHECK_COMMAND_FAILED'),
            (subprocess.TimeoutExpired('sbx', 1), 'DESTINATION_CHECK_TIMEOUT'),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('safe\n')
            manifest = workspace.snapshot(root)
            for response, expected in scenarios:
                with self.subTest(expected=expected, response=str(response)):
                    runner = oc2.Runner(oc2.getpass.getuser())
                    with (patch.object(oc2, 'execute'),
                          patch.object(oc2.subprocess, 'run', side_effect=[response]) as run):
                        with self.assertRaisesRegex(oc2.Stop, expected) as caught:
                            oc2.transfer_workspace(runner, 'oc2-dev', pathlib.Path(tmp) / 'snapshot', manifest, runner.user)
                    self.assertNotIn('private stderr', str(caught.exception))
                    self.assertEqual(run.call_count, 1)
                    self.assertFalse((pathlib.Path(tmp) / 'snapshot').exists())

    def test_oc2_help_and_version_are_local(self):
        help_result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'oc2.py'), '--help'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        version_result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'oc2.py'), '--version'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(version_result.returncode, 0)
        self.assertIn(oc2.VERSION, version_result.stdout)
        self.assertEqual(oc2.VERSION, '2.2.5')
        self.assertNotIn('--collect', help_result.stdout)

    def test_missing_sandbox(self):
        runner = FakeRunner()
        self.assertFalse(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mountless_sandbox_reused(self):
        # sbx v0.49.2 omits mount-related fields from ls --format json.
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}])
        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))
        self.assertIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_v3_shell_workload_is_compatible_for_collection(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'sbx-kit-shell'}])

        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mounted_workspace_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell', 'workspace': '/home/username/repo'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_missing_runtime_mounts_evidence_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev'})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_runtime_mounts_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev',
                            'runtime_mounts': [{'source': '/home/username'}]})
        with self.assertRaisesRegex(oc2.Stop, 'runtime mounts'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_inspect_name_mismatch_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'other-sandbox', 'runtime_mounts': []})
        with self.assertRaisesRegex(oc2.Stop, 'identity mismatch'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_invalid_runtime_mounts_type_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev', 'runtime_mounts': {}})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_list_workspace_mount_rejected_even_if_inspect_empty(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell',
                              'workspace': '/home/username/source'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')
        self.assertNotIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_wrong_agent_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'opencode', 'workspace': '-'}])
        with self.assertRaisesRegex(oc2.Stop, 'not shell'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_dry_run_no_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('must not call sbx')):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(oc2.main(['--repo-root', tmp, '--workspace', tmp,
                                               '--dry-run']), 0)
                self.assertIn('no Sandbox commands executed', out.getvalue())

    def test_invalid_sandbox_name_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            self.assertEqual(oc2.main(['--repo-root', tmp, '--sandbox', '../bad', '--dry-run']), 1)

    def test_launch_uses_standalone_no_host_env(self):
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        oc2.launch(
            runner,
            oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0],
                runtime + '/project', pathlib.Path('/tmp/opencode-v2-config.jsonc'),
            ),
        )
        command = runner.calls[-1]
        self.assertEqual(command[:3], ('exec', '-it', '-w'))
        self.assertEqual(command[3], runtime + '/project')
        self.assertEqual(command[4:7], ('oc2-dev', 'python3', '-c'))
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, command)
        self.assertEqual(command[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('OPENCODE_WATCHDOG_ENABLED=false', command)
        self.assertNotIn('bash', command)
        self.assertNotIn('--mount', command)
        self.assertFalse(any(argument.startswith('OPENCODE_CONFIG_DIR=') for argument in command))
        self.assertIn('OPENCODE_CONFIG_PROJECT_DISABLE=1', command)

    def test_launch_passes_gateway_token_placeholder_not_host_token(self):
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        cloudflare = oc2.CloudflareGatewayRuntime('a' * 32, 'gateway-1')
        with patch.dict(oc2.os.environ, {'OC_CF_API_TOKEN': 'sensitive-poison-value'}):
            oc2.launch(
                runner,
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], runtime + '/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'), cloudflare,
                ),
            )

        command = runner.calls[-1]
        self.assertIn('OC_CF_ACCOUNT_ID=' + 'a' * 32, command)
        self.assertIn('OC_CF_GATEWAY_ID=gateway-1', command)
        self.assertIn('OC_CF_API_TOKEN=proxy-managed', command)
        self.assertNotIn('sensitive-poison-value', repr(runner.calls))

    def test_launch_without_cloudflare_selection_passes_no_cloudflare_environment(self):
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        oc2.launch(
            runner,
            oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0], runtime + '/project',
                pathlib.Path('/tmp/opencode-v2-config.jsonc'),
            ),
        )

        command = runner.calls[-1]
        self.assertFalse(any(argument.startswith('OC_CF_') for argument in command))

    def test_launch_prepares_isolated_runtime_for_clone_workspace(self):
        runner = FakeRunner()
        digest = 'b' * 64
        project = '/clone/workspaces/synthetic'
        runtime = f'{oc2.ROOT}/runtime/{digest[:16]}'
        config_file = pathlib.Path('/tmp/opencode-v2-config.jsonc')
        oc2.launch(runner, oc2.SandboxLaunch('oc2-dev', digest, oc2.PINNED[0], project, config_file))
        self.assertEqual(
            runner.calls[0],
            ('exec', 'oc2-dev', 'mkdir', '-p', '-m', '700',
             runtime, *(f'{runtime}/{name}' for name in
                        ('home', 'home/.local/share', 'config', 'config/opencode',
                         'state', 'cache', 'tmp'))),
        )
        self.assertEqual(
            runner.calls[1],
            ('exec', 'oc2-dev', 'mkdir', '-p', '-m', '700',
             f'{runtime}/home/.local/share/opencode'),
        )
        self.assertEqual(
            runner.calls[2],
            ('cp', str(config_file), f'oc2-dev:{runtime}/config/opencode/opencode.jsonc'),
        )
        auth, tui = runner.calls[3:5]
        self.assertEqual(tui[3], project)
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, auth)
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, tui)
        compile(auth[-3], '<oc2-inline-helper>', 'exec')
        for variable in ('HOME=', 'XDG_DATA_HOME=', 'OPENCODE_DB=', 'XDG_CONFIG_HOME=',
                         'XDG_STATE_HOME=', 'XDG_CACHE_HOME='):
            self.assertEqual([arg for arg in auth if arg.startswith(variable)],
                             [arg for arg in tui if arg.startswith(variable)])
        self.assertIn(f'OPENCODE_DB={runtime}/home/.local/share/opencode/oc2.db', tui)
        self.assertFalse(any(arg.startswith('OPENCODE_CONFIG_DIR=') for arg in tui))
        self.assertFalse(any(arg.startswith(('HTTP_PROXY=', 'HTTPS_PROXY=', 'NO_PROXY='))
                             for arg in auth + tui))

    def test_stage_does_not_depend_on_bash_positional_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# harmless guest fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            native_sha = hashlib.sha256((SCRIPTS / 'oc2_agent_native.py').read_bytes()).hexdigest()
            identity_sha = hashlib.sha256((SCRIPTS / 'oc2_identity.py').read_bytes()).hexdigest()
            verifier_dir = (
                f'{oc2.ROOT}/scripts/oc2_guest_{script_sha[:16]}_'
                f'{native_sha[:16]}_{identity_sha[:16]}'
            )

            class StagingRunner:
                def __init__(self):
                    self.calls = []

                def destination_status(self, name, destination):
                    return 0

                def sbx(self, *args, **kwargs):
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        # No synthetic $0/$1/$2 follows the bash code.
                        assert len(args) == 5, args
                        assert '$1' not in args[4] and '$2' not in args[4]
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        digest = (
                            identity_sha if args[3].endswith('/oc2_identity.py')
                            else native_sha if args[3].endswith('/oc2_agent_native.py')
                            else script_sha
                        )
                        return digest + '  verified\n'
                    return ''

            runner = StagingRunner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script)
            self.assertIn(
                ('exec', 'oc2-dev', 'mkdir', '-p', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts', verifier_dir),
                runner.calls,
            )
            self.assertIn(
                ('exec', 'oc2-dev', 'chmod', '700', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts', verifier_dir),
                runner.calls,
            )
            self.assertIn(f'oc2-dev:{verifier_dir}/oc2_identity.py', {
                call[2] for call in runner.calls if call[0] == 'cp'
            })
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 4)

    def test_stage_rejects_unsafe_verifier_probe_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            class Runner:
                def destination_status(self, name, destination):
                    return 12

                def sbx(self, *args, **kwargs):
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return script_sha + ' verified\n'
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'unsafe guest asset verifier path'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script)

    def test_stage_selected_assets_with_bounded_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            native_sha = hashlib.sha256((SCRIPTS / 'oc2_agent_native.py').read_bytes()).hexdigest()
            identity_sha = hashlib.sha256((SCRIPTS / 'oc2_identity.py').read_bytes()).hexdigest()
            asset = root / 'oc2-assets.json'
            asset.write_text('{"fixture":true}')
            asset_sha = hashlib.sha256(asset.read_bytes()).hexdigest()

            class Runner:
                def __init__(self):
                    self.calls = []

                def destination_status(self, name, destination):
                    return 0

                def sbx(self, *args, **kwargs):
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        digest = (asset_sha if '/assets/' in args[3]
                                  else identity_sha if args[3].endswith('/oc2_identity.py')
                                  else native_sha if args[3].endswith('/oc2_agent_native.py')
                                  else script_sha)
                        return (digest
                                + '  verified\n')
                    return ''

            runner = Runner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script, asset, asset_sha)
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 5)
            start = [c for c in runner.calls if c[:3] ==
                     ('exec', 'oc2-dev', 'python3')]
            self.assertEqual(len(start), 1)
            self.assertIn('--expected-assets-sha', start[0])
            self.assertIn(asset_sha, start[0])
            self.assertIn('--assets', start[0])

    def test_stage_selected_assets_sha_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            asset = root / 'oc2-assets.json'
            asset.write_text('{}')
            expected = hashlib.sha256(asset.read_bytes()).hexdigest()
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            native_sha = hashlib.sha256((SCRIPTS / 'oc2_agent_native.py').read_bytes()).hexdigest()
            identity_sha = hashlib.sha256((SCRIPTS / 'oc2_identity.py').read_bytes()).hexdigest()

            class Runner:
                def destination_status(self, name, destination):
                    return 0

                def sbx(self, *args, **kwargs):
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        digest = ('f' * 64 if '/assets/' in args[3]
                                  else identity_sha if args[3].endswith('/oc2_identity.py')
                                  else native_sha if args[3].endswith('/oc2_agent_native.py')
                                  else script_sha)
                        return (digest
                                + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, expected)

    def test_stage_rejects_unsafe_asset_probe_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            asset = root / 'oc2-assets.json'
            asset.write_text('{}')
            asset_sha = hashlib.sha256(asset.read_bytes()).hexdigest()
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            native_sha = hashlib.sha256((SCRIPTS / 'oc2_agent_native.py').read_bytes()).hexdigest()
            identity_sha = hashlib.sha256((SCRIPTS / 'oc2_identity.py').read_bytes()).hexdigest()

            class Runner:
                def destination_status(self, name, destination):
                    return 12 if '/assets/' in destination else 0

                def sbx(self, *args, **kwargs):
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        digest = (asset_sha if '/assets/' in args[3]
                                  else identity_sha if args[3].endswith('/oc2_identity.py')
                                  else native_sha if args[3].endswith('/oc2_agent_native.py')
                                  else script_sha)
                        return (digest + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'unsafe guest asset bundle path'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, asset_sha)

    def test_cli_version_probe_uses_shell_parameter_for_binary_path(self):
        class VersionRunner:
            def __init__(self):
                self.calls = []

            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                assert args == (
                    'exec', 'oc2-dev', 'sh', '-c',
                    'if test -x "$1"; then "$1" --version; fi',
                    'oc2-version-probe', oc2.PINNED[0],
                )
                return 'opencode v2.2.5\n'

        runner = VersionRunner()
        self.assertEqual(oc2.cli_path(runner, 'oc2-dev'), oc2.PINNED[0])
        self.assertEqual(len(runner.calls), 1)

    def test_cli_path_returns_none_when_pinned_binary_is_missing(self):
        class MissingBinaryRunner:
            def __init__(self):
                self.calls = []

            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                if args[:4] == ('exec', 'oc2-dev', 'sh', '-c'):
                    return ''
                raise oc2.Stop('sbx command failed (exit 127)')

        runner = MissingBinaryRunner()
        self.assertIsNone(oc2.cli_path(runner, 'oc2-dev'))
        self.assertEqual(len(runner.calls), 1)

    def test_launch_rejects_unapproved_binary(self):
        with self.assertRaisesRegex(oc2.Stop, 'unapproved'):
            oc2.launch(
                FakeRunner(),
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, '/tmp/untrusted', '/workspace/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )

    def test_launch_rejects_invalid_digest(self):
        with self.assertRaisesRegex(oc2.Stop, 'invalid runtime digest'):
            oc2.launch(
                FakeRunner(),
                oc2.SandboxLaunch(
                    'oc2-dev', 'not-a-digest', oc2.PINNED[0], '/workspace/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )

    def test_cloudflare_gateway_runtime_is_absent_when_provider_is_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna', 'providers': {'openai': {}},
            }))
            self.assertIsNone(oc2.cloudflare_gateway_runtime(config, None, None))

    def test_cloudflare_gateway_runtime_requires_valid_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {'openai': {}, 'cloudflare-ai-gateway-custom': {}},
            }))
            for account_id, gateway_id in (
                (None, 'default'),
                ('a' * 31, 'default'),
                ('g' * 32, 'default'),
                ('a' * 32, None),
                ('a' * 32, 'invalid gateway'),
            ):
                with self.subTest(account_id=account_id, gateway_id=gateway_id):
                    with self.assertRaisesRegex(oc2.Stop, 'Cloudflare runtime identifiers') as error:
                        oc2.cloudflare_gateway_runtime(config, account_id, gateway_id)
                    self.assertNotIn(str(account_id), str(error.exception))
                    self.assertNotIn(str(gateway_id), str(error.exception))

    def test_cloudflare_gateway_runtime_is_selected_with_openai_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {'openai': {}, 'cloudflare-ai-gateway-custom': {}},
            }))
            self.assertEqual(
                oc2.cloudflare_gateway_runtime(config, 'a' * 32, 'gateway-1'),
                oc2.CloudflareGatewayRuntime('a' * 32, 'gateway-1'),
            )

    def test_unrequested_cloudflare_provider_is_removed_from_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {
                    'openai': {'models': {}},
                    'cloudflare-ai-gateway-custom': {'models': {'secret-model': {}}},
                },
                'policies': [
                    {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
                    {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
                    {
                        'action': 'provider.use',
                        'resource': 'cloudflare-ai-gateway-custom',
                        'effect': 'allow',
                    },
                ],
            }))

            selected = oc2.configure_cloudflare_provider(config, include_cloudflare=False)

            runtime_config = json.loads(config.read_text())

        self.assertFalse(selected)
        self.assertEqual(set(runtime_config['providers']), {'openai'})
        self.assertFalse(any(
            policy.get('resource') == 'cloudflare-ai-gateway-custom'
            for policy in runtime_config['policies']
        ))

    def test_explicit_cloudflare_mode_keeps_provider_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            original = {
                'model': 'openai/gpt-6-luna',
                'providers': {
                    'openai': {'models': {}},
                    'cloudflare-ai-gateway-custom': {'models': {'secret-model': {}}},
                },
                'policies': [],
            }
            config.write_text(json.dumps(original))

            selected = oc2.configure_cloudflare_provider(config, include_cloudflare=True)

            self.assertTrue(selected)
            self.assertEqual(json.loads(config.read_text()), original)

    def test_cloudflare_default_model_requires_provider_even_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'cloudflare-ai-gateway-custom/secret-model',
                'providers': {
                    'openai': {'models': {}},
                    'cloudflare-ai-gateway-custom': {'models': {'secret-model': {}}},
                },
                'policies': [],
            }))

            selected = oc2.configure_cloudflare_provider(config, include_cloudflare=False)

        self.assertTrue(selected)

    def test_cloudflare_mode_without_provider_configuration_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {'openai': {'models': {}}},
                'policies': [],
            }))

            with self.assertRaisesRegex(oc2.Stop, 'no configured provider'):
                oc2.configure_cloudflare_provider(config, include_cloudflare=True)

    def test_credential_mixin_spec_declares_proxy_bindings(self):
        spec = yaml.safe_load(oc2.credential_mixin_spec('oc2-credentials-a1b2c3'))

        self.assertTrue(oc2.credential_mixin_spec('oc2-credentials-a1b2c3').startswith(b'# syntax=docker/sandbox-kit:3\n'))
        self.assertEqual(spec['schemaVersion'], '3')
        self.assertEqual(spec['kind'], 'mixin')
        self.assertNotIn('name', spec)
        capabilities = spec['capabilities']
        credentials = [item for item in capabilities if item['type'] == 'com.docker.sandbox/credential@1']
        openai = next(item for item in credentials if item['config']['service'] == 'openai')
        self.assertEqual(openai['config']['phase'], 'runtime')
        self.assertNotIn('passthrough', openai['config'])
        self.assertEqual(
            openai['config']['oauth'],
            {
                'tokenEndpoint': {'host': 'auth.openai.com', 'path': '/oauth/token'},
                'resourceHosts': ['chatgpt.com'],
                'sentinels': {
                    'accessToken': 'oai-oat01-proxy-managed',
                    'refreshToken': 'oai-ort01-proxy-managed',
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
        )
        cloudflare = next(item for item in credentials
                          if item['config']['service'] == 'cloudflare-ai-gateway')
        self.assertTrue(cloudflare['optional'])
        self.assertEqual(cloudflare['config']['phase'], 'runtime')
        self.assertEqual(
            cloudflare['config']['apiKey'],
            {
                'name': 'OC_CF_API_TOKEN',
                'proxyManaged': True,
                'inject': [{
                    'domain': 'gateway.ai.cloudflare.com',
                    'header': 'cf-aig-authorization',
                    'format': 'Bearer %s',
                }],
            },
        )
        self.assertEqual(
            next(item for item in capabilities if item['type'] ==
                 'com.docker.sandbox/network-policy@1')['config']['runtime']['allow'],
            ['auth.openai.com', 'chatgpt.com', 'gateway.ai.cloudflare.com'],
        )
        self.assertNotIn('secret-value', str(spec))

    def test_mountless_create_args_attaches_mixin_without_workspace(self):
        args = oc2.mountless_create_args(
            'oc2-v2', pathlib.Path('/tmp/credentials'), pathlib.Path('/tmp/opencode-cli'),
        )

        self.assertEqual(
            args,
            [
                'create', '--name', 'oc2-v2',
                '--kit', '/tmp/credentials', '--kit', '/tmp/opencode-cli',
                oc2.SHELL_WORKLOAD,
            ],
        )

    def test_requires_external_inference_when_v2_provider_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna', 'providers': {'openai': {}},
            }))
            self.assertTrue(oc2.requires_external_inference(config))

    def test_requires_external_inference_is_false_for_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({'shell': 'bash', 'snapshot': True}))
            self.assertFalse(oc2.requires_external_inference(config))


class OAuthBootstrapConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = pathlib.Path(self.temp.name) / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.runtime.chmod(0o700)
        config_dir = self.runtime / 'config' / 'opencode'
        config_dir.mkdir(parents=True, mode=0o700)
        self.base_file = config_dir / 'opencode.jsonc'
        self.policies: list[dict[str, str]] = [
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
            {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
            {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
        ]
        self.config: dict[str, Any] = {
            '$schema': 'https://opencode.ai/config.json',
            'model': 'openai/gpt-6-luna',
            'providers': {'openai': {'models': {'gpt-6-luna': {}}}},
            'policies': self.policies,
        }
        self.base_bytes = json.dumps(self.config, indent=2).encode() + b'\n'
        self.base_file.write_bytes(self.base_bytes)

    def test_bootstrap_adds_only_openai_connect_exception(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        generated = json.loads((directory / 'opencode.jsonc').read_bytes())
        expected = [
            *self.policies[:2],
            self.policies[2],
            {'action': 'integration.connect', 'resource': 'openai', 'effect': 'allow'},
            *self.policies[3:],
        ]
        expected_config = {**self.config, 'policies': expected}

        self.assertEqual(generated, expected_config)
        self.assertEqual(self.base_file.read_bytes(), self.base_bytes)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((directory / 'opencode.jsonc').stat().st_mode), 0o600)
        self.assertTrue((directory / 'node_modules').is_dir())
        bootstrap.cleanup(directory, self.runtime)
        self.assertFalse(directory.exists())
        self.assertEqual(self.base_file.read_bytes(), self.base_bytes)

    def test_bootstrap_refuses_base_without_blanket_connect_deny(self):
        self.config['policies'] = [self.policies[0], self.policies[1]]
        self.base_file.write_text(json.dumps(self.config))

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())

    def test_bootstrap_refuses_preexisting_allow_policy(self):
        self.config['policies'].append(
            {'action': 'integration.connect', 'resource': 'openai', 'effect': 'allow'},
        )
        self.base_file.write_text(json.dumps(self.config))

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())

    def test_bootstrap_refuses_existing_destination(self):
        destination = self.runtime / 'oauth-bootstrap'
        destination.mkdir(mode=0o700)
        existing = destination / 'preserve.txt'
        existing.write_text('preserve')

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertEqual(existing.read_text(), 'preserve')

    def test_bootstrap_cleanup_refuses_unexpected_symlink(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        target = self.runtime / 'preserve'
        target.write_text('preserve')
        (directory / 'unexpected').symlink_to(target)

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.cleanup(directory, self.runtime)

        self.assertEqual(target.read_text(), 'preserve')
        self.assertTrue(directory.is_dir())

    def test_cleanup_refuses_unexpected_files_without_deleting_them(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        unexpected = directory / 'unexpected'
        unexpected.write_text('preserve')

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.cleanup(directory, self.runtime)

        self.assertEqual(unexpected.read_text(), 'preserve')


class OAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / 'auth.json'
        self.runtime = self.root / 'runtime'
        self.runtime_tmp = self.runtime / 'tmp'
        self.runtime_tmp.mkdir(parents=True, mode=0o700)
        self.runtime.chmod(0o700)
        self.runtime_tmp.chmod(0o700)
        config_dir = self.runtime / 'config' / 'opencode'
        config_dir.mkdir(parents=True, mode=0o700)
        self.base_config = config_dir / 'opencode.jsonc'
        self.base_config.write_text(json.dumps({
            '$schema': 'https://opencode.ai/config.json',
            'model': 'openai/gpt-6-luna',
            'providers': {'openai': {'models': {'gpt-6-luna': {}}}},
            'policies': [
                {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
                {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
                {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
                {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
                {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
            ],
        }))
        self.base_config_bytes = self.base_config.read_bytes()
        self.environment = patch.dict(os.environ, {
            'TMPDIR': str(self.runtime_tmp),
            'XDG_CONFIG_HOME': str(self.runtime / 'config'),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.last_envs = []
        self.db = self.runtime / 'home/.local/share/opencode/oc2.db'
        self.db.parent.mkdir(parents=True)
        self.db.touch()
        self.source.write_text(json.dumps({'openai': {
            'type': 'oauth', 'access': 'oai-oat01-proxy-managed',
            'refresh': 'oai-ort01-proxy-managed', 'expires': 123,
        }}))
        self.record = {'id': 'sbx-openai', 'integrationID': 'openai',
                       'label': 'Sandbox OpenAI', 'active': True,
                       'value': {'type': 'oauth', 'methodID': 'chatgpt-browser',
                                 'access': 'oai-oat01-proxy-managed',
                                 'refresh': 'oai-ort01-proxy-managed', 'expires': 123}}
        self.other = {'id': 'other', 'integrationID': 'other', 'active': True}
        self.last_calls = []

    def capture_stderr(self, stderr):
        with patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}):
            return bootstrap.capture_import_stderr(self.runtime, self.db, stderr)

    def run_sync(self, before, after, fail=None):
        calls: list[tuple[Any, Any]] = []
        self.last_calls = calls
        self.last_envs = []
        exports = iter([before, after])
        export_count = 0

        def run(args, **kwargs):
            nonlocal export_count
            calls.append((args, kwargs.get('input')))
            action = tuple(args[1:3])
            self.last_envs.append((action, kwargs.get('env')))
            if action == fail:
                return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
            if action == ('debug', 'paths'):
                output = str(self.db)
            elif action == ('auth', 'export'):
                export_count += 1
                if export_count == 2:
                    self.assertFalse((self.runtime / 'oauth-bootstrap').exists())
                output = json.dumps(next(exports))
            else:
                output = ''
            return subprocess.CompletedProcess(args, 0, output.encode(), b'')

        with patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            oauth.synchronize('opencode', self.source, self.db)
        return calls

    def test_captures_import_stderr_only_under_runtime_tmp(self):
        legacy = self.runtime_tmp / 'oc2-oauth-import.stderr'
        legacy.write_bytes(b'previous attempt')
        with patch.object(bootstrap.secrets, 'token_hex', return_value='a' * 16):
            captured = self.capture_stderr(b'sensitive CLI error')

        self.assertEqual(captured, self.runtime_tmp / f'oc2-oauth-import-{"a" * 16}.stderr')
        self.assertEqual(captured.read_bytes(), b'sensitive CLI error')
        self.assertEqual(stat.S_IMODE(captured.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.runtime_tmp.stat().st_mode), 0o700)
        self.assertEqual(captured.stat().st_nlink, 1)
        self.assertEqual(legacy.read_bytes(), b'previous attempt')

    def test_each_import_failure_gets_a_distinct_capture_path(self):
        with patch.object(bootstrap.secrets, 'token_hex', side_effect=('a' * 16, 'b' * 16)):
            first = self.capture_stderr(b'first')
            second = self.capture_stderr(b'second')

        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b'first')
        self.assertEqual(second.read_bytes(), b'second')

    def test_captures_empty_import_stderr_as_empty_file(self):
        captured = self.capture_stderr(b'')

        self.assertIsNotNone(captured)
        self.assertEqual(captured.stat().st_size, 0)

    def test_refuses_existing_import_stderr_without_overwrite(self):
        path = self.runtime_tmp / f'oc2-oauth-import-{"c" * 16}.stderr'
        path.write_bytes(b'previous evidence')

        with patch.object(bootstrap.secrets, 'token_hex', return_value='c' * 16):
            captured = self.capture_stderr(b'new secret')

        self.assertIsNone(captured)
        self.assertEqual(path.read_bytes(), b'previous evidence')

    def test_refuses_import_stderr_symlink_without_following_it(self):
        target = self.root / 'protected'
        target.write_bytes(b'protected')
        destination = self.runtime_tmp / f'oc2-oauth-import-{"d" * 16}.stderr'
        destination.symlink_to(target)

        with patch.object(bootstrap.secrets, 'token_hex', return_value='d' * 16):
            captured = self.capture_stderr(b'new secret')

        self.assertIsNone(captured)
        self.assertEqual(target.read_bytes(), b'protected')

    def test_refuses_capture_outside_runtime_directory(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir(mode=0o700)
        captured = bootstrap.capture_import_stderr(elsewhere, self.db, b'secret')

        self.assertIsNone(captured)

    def test_refuses_runtime_tmp_with_broad_permissions(self):
        self.runtime_tmp.chmod(0o755)

        captured = self.capture_stderr(b'secret')

        self.assertIsNone(captured)
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_imports_sentinel_without_changing_other_records(self):
        calls = self.run_sync([self.other], [self.other, self.record])
        imports = [payload for args, payload in calls if args[1:3] == ['auth', 'import']]
        self.assertEqual(json.loads(imports[0]), [self.record])
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_reuses_matching_record_without_import(self):
        calls = self.run_sync([self.other, self.record], [])
        self.assertFalse(any(args[1:3] == ['auth', 'import'] for args, _ in calls))

    def test_only_import_uses_bootstrap_config_and_readback_reverts(self):
        self.run_sync([self.other], [self.other, self.record])

        import_envs = [env for action, env in self.last_envs if action == ('auth', 'import')]
        export_envs = [env for action, env in self.last_envs if action == ('auth', 'export')]
        self.assertEqual(len(import_envs), 1)
        self.assertEqual(len(export_envs), 2)
        self.assertEqual(
            import_envs[0]['OPENCODE_CONFIG_DIR'],
            str(self.runtime / 'oauth-bootstrap'),
        )
        self.assertNotIn('OPENCODE_CONFIG_PROJECT_DISABLE', import_envs[0])
        self.assertEqual(export_envs, [None, None])
        self.assertEqual(self.base_config.read_bytes(), self.base_config_bytes)

    def test_bootstrap_policy_error_stops_before_import(self):
        self.base_config.write_text(json.dumps({
            'policies': [{'action': 'provider.use', 'resource': '*', 'effect': 'deny'}],
        }))
        self.last_calls = []

        def run(args, **kwargs):
            self.last_calls.append(tuple(args[1:3]))
            action = tuple(args[1:3])
            if action == ('debug', 'paths'):
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if action == ('auth', 'export'):
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            return subprocess.CompletedProcess(args, 0, b'', b'')

        with patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(bootstrap.BootstrapConfigError):
                oauth.synchronize('opencode', self.source, self.db)

        self.assertNotIn(('auth', 'import'), self.last_calls)

    def test_import_failure_cleans_bootstrap_and_exports_failure_state_once(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [self.record], fail=('auth', 'import'))

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())
        exports = [call for call in self.last_calls if call[0][1:3] == ['auth', 'export']]
        imports = [call for call in self.last_calls if call[0][1:3] == ['auth', 'import']]
        self.assertEqual(len(exports), 2)
        self.assertEqual(len(imports), 1)
        self.assertIn('OC2_OAUTH IMPORT FAIL', output.getvalue())
        self.assertIn('PRE_IMPORT_OPENAI_COUNT=0', output.getvalue())
        self.assertIn('AFTER_FAILURE_OPENAI_COUNT=1', output.getvalue())
        self.assertIn('AFTER_FAILURE_ACTIVE=true', output.getvalue())
        self.assertIn('AFTER_FAILURE_SENTINELS_MATCH=true', output.getvalue())
        self.assertIn('POST_FAILURE_DB_IDENTITY_MATCH=true', output.getvalue())
        self.assertIn('OTHER_CREDENTIALS_UNCHANGED=true', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_bootstrap_cleanup_failure_blocks_readback(self):
        calls = []
        export_count = 0

        def run(args, **kwargs):
            nonlocal export_count
            calls.append(tuple(args[1:3]))
            action = tuple(args[1:3])
            if action == ('debug', 'paths'):
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if action == ('auth', 'export'):
                export_count += 1
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            if action == ('auth', 'import'):
                config_dir = pathlib.Path(kwargs['env']['OPENCODE_CONFIG_DIR'])
                (config_dir / 'unexpected').write_text('block cleanup')
                return subprocess.CompletedProcess(args, 0, b'', b'')
            return subprocess.CompletedProcess(args, 0, b'', b'')

        output = io.StringIO()
        with contextlib.redirect_stderr(output), \
                patch.dict(os.environ, {
                    'TMPDIR': str(self.runtime_tmp),
                    'XDG_CONFIG_HOME': str(self.runtime / 'config'),
                }), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(bootstrap.BootstrapConfigError):
                oauth.synchronize('opencode', self.source, self.db)

        self.assertEqual(export_count, 1)
        self.assertEqual(calls.count(('auth', 'import')), 1)
        self.assertIn('OC2_OAUTH BOOTSTRAP_CLEANUP FAIL', output.getvalue())
        self.assertTrue((self.runtime / 'oauth-bootstrap' / 'unexpected').is_file())

    def test_rejects_invalid_sentinel_or_expiry(self):
        for key, value in [('expires', -1), ('expires', True), ('access', 'real-token')]:
            with self.subTest(key=key, value=value):
                auth = json.loads(self.source.read_text())
                auth['openai'][key] = value
                with self.assertRaises(ValueError) as error:
                    bootstrap.record_from_auth(auth)
                self.assertNotIn('real-token', str(error.exception))

    def test_conflicting_openai_record_stops(self):
        with self.assertRaises(ValueError):
            self.run_sync([{'id': 'another', 'integrationID': 'openai'}], [])

    def test_inactive_managed_record_stops_without_import(self):
        record = dict(self.record, active=False)
        with self.assertRaises(ValueError):
            self.run_sync([record], [])

    def test_rejects_database_symlink_before_commands(self):
        self.db.unlink()
        self.db.symlink_to(self.source)
        with patch.object(oauth.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                oauth.synchronize('opencode', self.source, self.db)
            run.assert_not_called()

    def test_metadata_is_mapped_from_source(self):
        auth = json.loads(self.source.read_text())
        auth['openai'].update(accountId='account', enterpriseUrl='https://example.invalid')
        record = bootstrap.record_from_auth(auth)
        self.assertEqual(record['value']['metadata'],
                         {'accountID': 'account', 'enterpriseUrl': 'https://example.invalid'})

    def test_database_path_mismatch_stops(self):
        result = subprocess.CompletedProcess([], 0, b'/different/path\n', b'')
        with patch.object(oauth.subprocess, 'run', return_value=result):
            with self.assertRaises(ValueError):
                oauth.synchronize('opencode', self.source, self.db)

    def test_readback_mismatch_stops(self):
        with self.assertRaises(ValueError):
            self.run_sync([self.other], [self.record])

    def test_export_and_import_failure_stop(self):
        for action in [('auth', 'export'), ('auth', 'import')]:
            with self.subTest(action=action), self.assertRaises(ValueError) as error:
                self.run_sync([], [], fail=action)
            self.assertNotIn('secret-value', str(error.exception))

    def test_export_failure_reports_stage_without_secret(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'export'))
        self.assertIn('OC2_OAUTH EXPORT_BEFORE FAIL', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_import_nonzero_reports_fixed_code_without_stderr(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'import'))
        self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
        self.assertIn('IMPORT_EXIT_CODE=1', output.getvalue())
        self.assertIn('IMPORT_STDERR_CAPTURED=true', output.getvalue())
        self.assertIn('IMPORT_STDERR_BYTES=12', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())
        import_calls = [call for call in self.last_calls if call[0][1:3] == ['auth', 'import']]
        self.assertEqual(len(import_calls), 1)
        capture_path = next(
            line.removeprefix('IMPORT_STDERR_PATH=')
            for line in output.getvalue().splitlines()
            if line.startswith('IMPORT_STDERR_PATH=')
        )
        capture = pathlib.Path(capture_path)
        self.assertEqual(capture.parent, self.runtime_tmp)
        self.assertEqual(capture.read_bytes(), b'secret-value')

    def test_import_stderr_capture_failure_still_fails_closed(self):
        self.runtime_tmp.chmod(0o755)
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'import'))

        self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
        self.assertIn('IMPORT_STDERR_CAPTURED=false', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_import_classifies_exact_cli_input_error_only(self):
        message = 'Pipe auth export output into stdin or pass a file to import'
        for stderr, expected in [(message + '\n', 'IMPORT_INPUT_INVALID'),
                                 (message + ' secret-value', 'IMPORT_NONZERO')]:
            with self.subTest(expected=expected):
                output = io.StringIO()
                def run(args, **kwargs):
                    if args[1:3] == ['debug', 'paths']:
                        return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
                    if args[1:3] == ['auth', 'export']:
                        return subprocess.CompletedProcess(args, 0, b'[]', b'')
                    return subprocess.CompletedProcess(args, 1, b'', stderr.encode())
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                self.assertIn('OC2_OAUTH ' + expected, output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_unrecognized_schema_and_other_errors_remain_nonzero(self):
        for stderr in ('SchemaError: secret-value', 'connection failed: secret-value'):
            with self.subTest(kind=stderr.split(':')[0]):
                output = io.StringIO()
                def run(args, **kwargs):
                    if args[1:3] == ['debug', 'paths']:
                        return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
                    if args[1:3] == ['auth', 'export']:
                        return subprocess.CompletedProcess(args, 0, b'[]', b'')
                    return subprocess.CompletedProcess(args, 1, b'', stderr.encode())
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_import_timeout_reports_fixed_code_without_exception_text(self):
        output = io.StringIO()
        def run(args, **kwargs):
            if args[1:3] == ['debug', 'paths']:
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if args[1:3] == ['auth', 'export']:
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            raise subprocess.TimeoutExpired('secret-value', 30, stderr=b'secret-value')
        with contextlib.redirect_stderr(output), \
                patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                oauth.synchronize('opencode', self.source, self.db)
        self.assertIn('OC2_OAUTH IMPORT_TIMEOUT', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_failure_stages_are_distinct_and_sanitized(self):
        cases = [
            ('SENTINEL_VALIDATE', 'sentinel'),
            ('DB_PATH_VERIFY', 'path'),
            ('EXPORT_BEFORE', 'before'),
            ('STATE_CLASSIFY', 'conflict'),
            ('IMPORT', 'import'),
            ('EXPORT_AFTER', 'after'),
            ('READBACK_VERIFY', 'readback'),
        ]
        for expected, failure in cases:
            with self.subTest(stage=expected):
                output = io.StringIO()
                export_count = 0
                def run(args, **kwargs):
                    nonlocal export_count
                    action = tuple(args[1:3])
                    if action == ('debug', 'paths'):
                        return subprocess.CompletedProcess(args, 0,
                            ('/wrong' if failure == 'path' else str(self.db)).encode(), b'')
                    if action == ('auth', 'export'):
                        export_count += 1
                        if (failure == 'before' and export_count == 1 or
                                failure == 'after' and export_count == 2):
                            return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
                        records = ([{'id': 'other-openai', 'integrationID': 'openai'}]
                                   if failure == 'conflict' else [])
                        return subprocess.CompletedProcess(args, 0, json.dumps(records).encode(), b'')
                    if failure == 'import':
                        return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
                    return subprocess.CompletedProcess(args, 0, b'', b'')
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    if failure == 'sentinel':
                        self.source.write_text('{"openai":{"access":"secret-value"}}')
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                if failure == 'sentinel':
                    self.source.write_text(json.dumps({'openai': {
                        'type': 'oauth', 'access': 'oai-oat01-proxy-managed',
                        'refresh': 'oai-ort01-proxy-managed', 'expires': 123}}))
                self.assertIn(f'OC2_OAUTH {expected} START', output.getvalue())
                self.assertIn(f'OC2_OAUTH {expected} FAIL', output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_unknown_error_reports_fixed_stage_without_exception_text(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), patch.object(
                oauth.subprocess, 'run', side_effect=RuntimeError('secret-value')):
            with self.assertRaises(RuntimeError):
                oauth.synchronize('opencode', self.source, self.db)
        self.assertIn('OC2_OAUTH DB_PATH_VERIFY FAIL', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())


class GuestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name) / 'oc2'
        self.base.mkdir()
        self.orig = guest.BASE
        guest.BASE = self.base
        self.bundle = self.base / 'bundles' / 'bundle1'
        self.bundle.mkdir(parents=True)
        self.config = {'$schema': 'https://opencode.ai/config.json', 'shell': 'bash',
                       'snapshot': True, 'plugins': [], 'mcp': {}}
        self.client = {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}
        for name, value in [('opencode.jsonc', self.config), ('cli.json', self.client)]:
            (self.bundle / name).write_text(json.dumps(value))
        hashes = {n: hashlib.sha256((self.bundle / n).read_bytes()).hexdigest()
                  for n in ('opencode.jsonc', 'cli.json')}
        self.manifest = {'schema': 'dotfiles-ai/sandbox-export/v0', 'generator': 'v0.2',
            'source': 'apm.yml', 'source_sha256': '0' * 64,
            'config_format': 'legacy-minimal',
            'opencode_version': '2.2.5', 'plugins_exported': 0,
                         'mcp_entries_exported': 0, 'artifacts_sha256': hashes}
        (self.bundle / 'export-manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        guest.BASE = self.orig
        self.tmp.cleanup()

    def test_v2_multi_provider_bundle_passes_guest_validation(self):
        source = self.base / 'source'
        source.mkdir()
        (source / 'apm.yml').write_text(
            'provider:\n'
            '  openai:\n'
            '    whitelist: [gpt-6-luna]\n'
            '  cloudflare-ai-gateway-custom:\n'
            "    npm: '@ai-sdk/openai-compatible'\n"
            '    name: Cloudflare AI Gateway Custom\n'
            '    options:\n'
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            '      headers:\n'
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            '    models:\n'
            '      custom-ollama-cloud/kimi-k2.7-code:\n'
            '        name: Kimi K2.7 Code\n'
            'opencode_v2:\n'
            '  default_model: openai/gpt-6-luna\n'
            '  deny_provider_fallback: true\n'
            '  deny_guest_auth: true\n'
            '  providers:\n'
            '    openai:\n'
            '      enabled: true\n'
            '      auth_method: docker_openai_oauth\n'
            '    cloudflare-ai-gateway-custom:\n'
            '      enabled: true\n'
            '      auth_method: docker_custom_secret\n',
            encoding='utf-8',
        )
        bundle = self.base / 'v2-bundle'
        generated = subprocess.run(
            [sys.executable, str(SCRIPTS / 'prepare_opencode_v2.py'),
             '--repo-root', str(source), '--out', str(bundle)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        digest = guest.verify(bundle)
        self.assertEqual(digest, hashlib.sha256((bundle / 'export-manifest.json').read_bytes()).hexdigest())
        server = json.loads((bundle / 'opencode.jsonc').read_text())
        self.assertEqual(set(server['providers']), {'openai', 'cloudflare-ai-gateway-custom'})

    def test_apm_native_agents_bind_export_assets_and_guest_runtime(self):
        repo = SCRIPTS.parents[1]
        output = self.base / 'native-export'
        output.parent.mkdir(parents=True, exist_ok=True)
        config_file = oc2.export_v2_config(repo, output)
        asset_raw, asset_sha = assets.build(repo)
        asset_file = self.base / 'assets.json'
        asset_file.write_bytes(asset_raw)

        config_sha = guest.verify(output)
        native_assets = guest.verify_assets(asset_file, asset_sha)
        runtime = guest.prepare(output, config_sha, native_assets, asset_sha)
        server = json.loads((config_file).read_text(encoding='utf-8'))
        client = json.loads((runtime / 'config/opencode/cli.json').read_text(encoding='utf-8'))

        self.assertEqual(set(server['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(server['agents']['oracle']['mode'], 'subagent')
        self.assertNotIn('default_agent', server)
        self.assertNotIn('mcp', server)
        self.assertEqual(server['policies'][-1],
                         {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'})
        self.assertEqual(client['theme'], {'name': 'tokyonight'})
        self.assertEqual(runtime, guest.runtime_path(config_sha, asset_sha))

    def test_materialize_idempotently(self):
        digest = guest.verify(self.bundle)
        d1 = guest.prepare(self.bundle, digest)
        d2 = guest.prepare(self.bundle, digest)
        self.assertEqual(d1, d2)
        self.assertTrue((d1 / 'config/opencode/cli.json').exists())
        self.assertTrue((d1 / 'project').is_dir())

    def test_manifest_tampering_stops(self):
        (self.bundle / 'opencode.jsonc').write_text('{"shell":"zsh"}')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            guest.verify(self.bundle)

    def test_extra_secret_file_stops(self):
        (self.bundle / '.env').write_text('SECRET=present')
        with self.assertRaisesRegex(ValueError, 'bundle'):
            guest.verify(self.bundle)

    def test_symlink_rejected(self):
        p = self.bundle / 'cli.json'
        p.unlink()
        p.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            guest.verify(self.bundle)

    def _assets(self):
        names = sorted(guest.ASSET_TARGETS)
        contents = {name: ('# selected text\n' if name != 'theme.json'
                           else '{"name":"tokyonight"}')
                    for name in names}
        contents[guest.NATIVE_ASSET_TARGET] = json.dumps(
            native.build_native_payload(native.NativeConfig('0' * 64, (), ())),
            sort_keys=True,
        )
        hashes = {name: hashlib.sha256(data.encode('utf-8')).hexdigest()
                  for name, data in contents.items()}
        payload = {'schema': guest.ASSET_SCHEMA, 'files': contents, 'sha256': hashes}
        directory = self.base / 'assets'
        directory.mkdir(exist_ok=True)
        path = directory / 'assets.json'
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_assets_materialize_and_reuse(self):
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        self.assertNotEqual(target, guest.runtime_path(cfg_sha))
        self.assertEqual(target, guest.prepare(self.bundle, cfg_sha, data, sha))
        self.assertTrue((target / 'config/opencode/AGENTS.md').is_file())
        self.assertTrue((target / 'config/opencode/skills/config-modernizer/SKILL.md').is_file())
        server = json.loads((target / 'config/opencode/opencode.jsonc').read_text())
        self.assertEqual(len(server['instructions']), 6)
        self.assertTrue(all(s.startswith(str(target)) for s in server['instructions']))
        self.assertNotIn('default_agent', server)
        self.assertNotIn('agents', server)
        self.assertNotIn('model', server)
        self.assertFalse((target / 'metadata/agent-routes.json').exists())
        tui = json.loads((target / 'config/opencode/cli.json').read_text())
        self.assertEqual(tui['theme'], {'name': 'tokyonight'})

    def test_guest_asset_manifest_requires_native_agent_config(self):
        path, sha = self._assets()
        payload = json.loads(path.read_bytes())
        payload['files'].pop(guest.NATIVE_ASSET_TARGET)
        payload['sha256'].pop(guest.NATIVE_ASSET_TARGET)
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)

        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_guest_rejects_v2_config_not_bound_to_native_asset_agents(self):
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        native_payload = native.build_native_payload(
            native.parse_apm_native((SCRIPTS.parents[1] / 'apm.yml').read_bytes())
        )
        native_payload['source_sha256'] = '0' * 64
        payload['files'][guest.NATIVE_ASSET_TARGET] = json.dumps(
            native_payload, sort_keys=True,
        )
        encoded_native = payload['files'][guest.NATIVE_ASSET_TARGET]
        payload['sha256'][guest.NATIVE_ASSET_TARGET] = hashlib.sha256(
            encoded_native.encode('utf-8'),
        ).hexdigest()
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assets_data = guest.verify_assets(path, digest)
        config_digest = guest.verify(self.bundle)

        with self.assertRaisesRegex(ValueError, 'Native Agent asset mismatch'):
            guest.prepare(self.bundle, config_digest, assets_data, digest)

    def test_guest_rejects_native_asset_from_a_different_apm_source(self):
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        native_payload = json.loads(payload['files'][guest.NATIVE_ASSET_TARGET])
        native_payload['source_sha256'] = 'f' * 64
        encoded_native = json.dumps(native_payload, sort_keys=True)
        payload['files'][guest.NATIVE_ASSET_TARGET] = encoded_native
        payload['sha256'][guest.NATIVE_ASSET_TARGET] = hashlib.sha256(
            encoded_native.encode('utf-8'),
        ).hexdigest()
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)
        assets_data = guest.verify_assets(path, hashlib.sha256(raw).hexdigest())
        config_digest = guest.verify(self.bundle)

        with self.assertRaisesRegex(ValueError, 'APM config and Native Agent asset source SHA mismatch'):
            guest.prepare(self.bundle, config_digest, assets_data,
                          hashlib.sha256(raw).hexdigest())

    def test_guest_rejects_native_agent_permission_escalation(self):
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        native_payload = native.build_native_payload(
            native.parse_apm_native((SCRIPTS.parents[1] / 'apm.yml').read_bytes())
        )
        native_payload['source_sha256'] = '0' * 64
        native_payload['agents']['oracle']['permissions'] = [
            {'action': 'edit', 'resource': '*', 'effect': 'allow'},
        ]
        encoded_native = json.dumps(native_payload, sort_keys=True)
        payload['files'][guest.NATIVE_ASSET_TARGET] = encoded_native
        payload['sha256'][guest.NATIVE_ASSET_TARGET] = hashlib.sha256(
            encoded_native.encode('utf-8'),
        ).hexdigest()
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)

        with self.assertRaisesRegex(ValueError, 'not allowlisted'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_assets_install_into_new_native_runtime_and_refuse_overwrite(self):
        path, sha = self._assets()
        runtime_id = 'c' * 64
        target = guest.install_assets(path, sha, runtime_id)
        self.assertTrue((target / 'config/opencode/rules/DOCS_STYLE.md').is_file())
        self.assertTrue((target / 'config/opencode/commands/build-skill.md').is_file())
        self.assertTrue((target / 'config/opencode/skills/agent-skill-architect/SKILL.md').is_file())
        self.assertEqual(
            json.loads((target / 'config/opencode/cli.json').read_text())['theme'],
            {'name': 'tokyonight'},
        )
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            guest.install_assets(path, sha, runtime_id)

    def test_asset_only_guest_cli_installs_without_a_config_bundle(self):
        path, sha = self._assets()
        with contextlib.redirect_stdout(io.StringIO()):
            result = guest.main([
                '--assets', str(path), '--expected-assets-sha', sha,
                '--install-assets-runtime', 'd' * 64,
            ])
        self.assertEqual(result, 0)
        self.assertTrue((self.base / 'runtime' / ('d' * 16) /
                         'config/opencode/commands/build-skill.md').is_file())

    def _assert_unapproved_asset_rejected(self, name):
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        payload['files'][name] = '{"source":"third-party"}'
        payload['sha256'][name] = hashlib.sha256(
            payload['files'][name].encode('utf-8')).hexdigest()
        rewritten = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(rewritten)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(rewritten).hexdigest())

    def test_guest_rejects_legacy_routing_asset_even_with_valid_hashes(self):
        self._assert_unapproved_asset_rejected('metadata/agent-routes.json')

    def test_guest_rejects_imported_agent_asset_even_with_valid_hashes(self):
        self._assert_unapproved_asset_rejected('config/opencode/agents/legacy.md')

    def test_assets_tampering_rejected(self):
        path, sha = self._assets()
        path.write_bytes(path.read_bytes().replace(b'tokyonight', b'othername'))
        with self.assertRaisesRegex(ValueError, 'asset SHA mismatch'):
            guest.verify_assets(path, sha)

    def test_assets_extra_path_rejected(self):
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        data['files']['../../secret'] = 'forbidden'
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_assets_symlink_rejected(self):
        path, sha = self._assets()
        real = path.parent / 'real.json'
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            guest.verify_assets(path, sha)

    def test_existing_runtime_asset_tampering_rejected(self):
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        (target / 'config/opencode/AGENTS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'runtime asset mismatch'):
            guest.prepare(self.bundle, cfg_sha, data, sha)

    def test_receipt_tampering_stops(self):
        digest = guest.verify(self.bundle)
        out = guest.prepare(self.bundle, digest)
        (out / 'receipt.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            guest.prepare(self.bundle, digest)



class AssetExporterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        for source in [*assets.SOURCE_TO_TARGET, assets.THEME_SOURCE]:
            file = self.root / source
            file.parent.mkdir(parents=True, exist_ok=True)
            if source == assets.THEME_SOURCE:
                file.write_text('{"theme":"tokyonight","plugin":["DO_NOT_IMPORT"]}')
            elif source.startswith('agent-commands/'):
                file.write_text('---\ndescription: Safe skill command\nagent: old-agent\n'
                                'model: unavailable/v1-model\n---\nBody of command\n')
            elif source.startswith('agent-skills/'):
                name = pathlib.Path(source).parent.name
                file.write_text(
                    f'---\nname: {name}\ndescription: Valid fixture skill.\n---\nInstructions\n',
                    encoding='utf-8',
                )
            else:
                file.write_text('# Reviewed content\n', encoding='utf-8')
        self._write_apm_assets(assets.SOURCE_TO_TARGET)

    def _write_apm_assets(self, sources):
        (self.root / 'apm.yml').write_text(
            'provider:\n'
            '  openai:\n'
            '    whitelist: [gpt-6-luna]\n'
            'opencode_v2:\n'
            '  default_model: openai/gpt-6-luna\n'
            '  providers:\n'
            '    openai:\n'
            '      enabled: true\n'
            '    cloudflare-ai-gateway-custom:\n'
            '      enabled: true\n'
            'x-oc2-assets:\n' + ''.join(f'  - {source}\n' for source in sources)
            + 'x-oc2-agents:\n'
            '  hephaestus:\n'
            '    mode: primary\n'
            '    model: openai/gpt-6-luna\n'
            '  oracle:\n'
            '    mode: subagent\n'
            '    model: openai/gpt-6-luna\n'
            'x-oc2-plugins:\n'
            '  enabled: false\n'
            '  allowlist: [superpowers]\n'
            'x-oc2-mcp:\n'
            '  enabled: false\n'
            '  servers: []\n',
            encoding='utf-8',
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_export_selected_assets_with_v1_command_fields_removed(self):
        raw, digest = assets.build(self.root)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        payload = json.loads(raw)
        self.assertEqual(set(payload['files']),
                         set(assets.SOURCE_TO_TARGET.values()) |
                         {assets.THEME_TARGET, assets.NATIVE_TARGET})
        self.assertNotIn('metadata/agent-routes.json', payload['files'])
        command = payload['files']['config/opencode/commands/build-skill.md']
        self.assertNotIn('agent: old-agent', command)
        self.assertNotIn('model: unavailable/', command)
        self.assertIn('description: Safe skill command', command)
        self.assertNotIn('DO_NOT_IMPORT', raw.decode('utf-8'))
        self.assertEqual(json.loads(payload['files']['theme.json']), {'name':'tokyonight'})

    def test_symlinked_source_rejected(self):
        target = self.root / 'global-rules/AGENTS.global.md'
        target.unlink()
        target.symlink_to(self.root / 'opencode/tui.jsonc')
        with self.assertRaisesRegex(assets.AssetError, 'linked'):
            assets.build(self.root)

    def test_symlinked_source_directory_rejected(self):
        rules = self.root / 'global-rules'
        linked = self.root / 'rules-link'
        rules.rename(linked)
        rules.symlink_to(linked, target_is_directory=True)
        with self.assertRaisesRegex(assets.AssetError, 'linked'):
            assets.build(self.root)

    def test_selected_asset_with_credential_signature_is_rejected(self):
        (self.root / 'global-rules/AGENTS.global.md').write_text(
            'credential: AKIA1234567890ABCDEF\n',
        )
        with self.assertRaisesRegex(assets.AssetError, 'credential material'):
            assets.build(self.root)

    def test_skill_frontmatter_name_must_match_native_discovery_directory(self):
        source = 'agent-skills/custom/config-modernizer/SKILL.md'
        (self.root / source).write_text(
            '---\nname: wrong-name\ndescription: Valid fixture skill.\n---\nInstructions\n',
            encoding='utf-8',
        )

        with self.assertRaisesRegex(assets.AssetError, 'Skill name mismatch'):
            assets.build(self.root)

    def test_unapproved_theme_rejected(self):
        (self.root / assets.THEME_SOURCE).write_text('{"theme":"../../bad"}')
        with self.assertRaisesRegex(assets.AssetError, 'unapproved TUI theme'):
            assets.build(self.root)

    def test_apm_assets_must_match_the_fixed_allowlist(self):
        self._write_apm_assets(['global-rules/UNAPPROVED.md'])
        with self.assertRaisesRegex(assets.AssetError, 'unapproved asset source'):
            assets.build(self.root)

    def test_apm_allowlist_intersection_exports_only_declared_approved_path(self):
        self._write_apm_assets(['global-rules/AGENTS.global.md'])
        raw, _ = assets.build(self.root)
        payload = json.loads(raw)
        self.assertEqual(
            set(payload['files']),
            {'config/opencode/AGENTS.md', assets.THEME_TARGET, assets.NATIVE_TARGET},
        )

    def test_native_manifest_change_changes_asset_and_runtime_identity(self):
        first_raw, first_sha = assets.build(self.root)
        apm = self.root / 'apm.yml'
        apm.write_text(apm.read_text(encoding='utf-8') + 'owner: updated\n', encoding='utf-8')
        second_raw, second_sha = assets.build(self.root)
        config_sha = 'a' * 64

        self.assertNotEqual(first_raw, second_raw)
        self.assertNotEqual(first_sha, second_sha)
        self.assertNotEqual(
            guest.runtime_path(config_sha, first_sha),
            guest.runtime_path(config_sha, second_sha),
        )

    def test_apm_assets_must_be_unique_and_traversal_free(self):
        for declaration in (
            ['global-rules/AGENTS.global.md', 'global-rules/AGENTS.global.md'],
            ['../outside.md'],
        ):
            self._write_apm_assets(declaration)
            with self.subTest(declaration=declaration), self.assertRaises(assets.AssetError):
                assets.build(self.root)

    def test_apm_assets_section_is_required_and_must_be_a_list(self):
        apm = self.root / 'apm.yml'
        for content in (
            'name: dotfiles-ai\n',
            'x-oc2-assets: [global-rules/AGENTS.global.md]\n',
            'x-oc2-assets: [global-rules/AGENTS.global.md]\nx-oc2-assets: [agent-commands/build-skill.md]\n',
        ):
            apm.write_text(content)
            with self.subTest(content=content), self.assertRaises(assets.AssetError):
                assets.build(self.root)



class NativeV2IndependenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = AssetExporterTest()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self):
        self.fixture.tearDown()

    def test_no_legacy_routing_source_required(self):
        self.assertFalse((self.root / 'opencode/omo.jsonc').exists())
        raw, digest = assets.build(self.root)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_legacy_source_ignored_even_if_malformed(self):
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('this is not valid json')
        self.assertEqual(before, assets.build(self.root))

    def test_legacy_source_symlink_ignored(self):
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to('/etc/passwd')
        self.assertEqual(before, assets.build(self.root))

    def test_unapproved_agent_directory_ignored(self):
        before = assets.build(self.root)
        agent = self.root / 'opencode/agents/old.md'
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text('model: unknown/unapproved\n')
        self.assertEqual(before, assets.build(self.root))

    def test_exported_manifest_has_no_agent_routes(self):
        raw, _ = assets.build(self.root)
        payload = json.loads(raw)
        self.assertFalse(any(p.startswith('metadata/') or
                             '/agents/' in p for p in payload['files']))


if __name__ == '__main__':
    unittest.main()
