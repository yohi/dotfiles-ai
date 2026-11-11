from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from unittest.mock import patch

import yaml

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2  # noqa: E402


class FakeSbx:
    def __init__(self) -> None:
        self.created = False
        self.installed = False
        self.kit_supported = True
        self.copied_config: str | None = None
        self.copied_files: dict[str, str] = {}
        self.created_mixin_spec: str | None = None
        self.created_mixin_path: pathlib.Path | None = None
        self.mixin_exists_at_launch: bool | None = None
        self.clone_source: pathlib.Path | None = None
        self.clone_source_content: str | None = None
        self.clone_source_remotes: str | None = None
        self.clone_source_log_subject: str | None = None
        self.clone_source_has_http_header = False
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: list[int | None] = []

    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str:
        self.calls.append(args)
        self.timeouts.append(None if tty else timeout)
        if args == ('version',):
            return 'sbx version v0.49.2 test\n'
        if args == ('create', '--help'):
            kit_help = '  --kit  compose a Mixin\n' if self.kit_supported else ''
            return '  --clone  private in-container clone\n' + kit_help
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args[:1] == ('create',):
            if '--kit' in args:
                mixin_path = pathlib.Path(args[args.index('--kit') + 1])
                self.created_mixin_path = mixin_path
                self.created_mixin_spec = (mixin_path / 'spec.yaml').read_text()
            self.created = True
            self.clone_source = pathlib.Path(args[-1])
            self.clone_source_content = (self.clone_source / 'main.py').read_text()
            self.clone_source_remotes = subprocess.run(
                ['git', '-C', str(self.clone_source), 'remote'],
                capture_output=True, text=True, check=True,
            ).stdout
            self.clone_source_log_subject = subprocess.run(
                ['git', '-C', str(self.clone_source), 'log', '-1', '--format=%s'],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            header = subprocess.run(
                ['git', 'config', '--file', str(self.clone_source / '.git' / 'config'),
                 '--get-regexp', r'^http\..*\.extraheader$'],
                capture_output=True, text=True, check=False,
            )
            self.clone_source_has_http_header = header.returncode == 0
            return ''
        if args[:1] == ('cp',):
            contents = pathlib.Path(args[1]).read_text()
            self.copied_files[args[2]] = contents
            if args[2].endswith('/config/opencode/opencode.jsonc'):
                self.copied_config = contents
            return ''
        if args[:2] == ('exec', 'oc2-test'):
            command = args[2:]
            if (command[:2] == ('sh', '-c')
                    and command[4] == oc2.PINNED[0]):
                return 'opencode v2.2.5\n' if self.installed else ''
            if command == ('pwd',):
                return '/home/agent/workspace/synthetic\n'
            if (command[:2] == ('git', '-C')
                    and command[3:] == ('rev-parse', '--show-toplevel')):
                return command[2] + '\n'
            if command[:2] == ('npm', 'install'):
                self.installed = True
                return ''
            return ''
        if args[:2] == ('exec', '-it'):
            self.mixin_exists_at_launch = (
                self.created_mixin_path is not None
                and self.created_mixin_path.exists()
            )
            return ''
        return ''


class LauncherFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        self._write_cloudflare_apm()
        self.project = self.root / 'synthetic'
        self.project.mkdir()
        clone_root_patch = patch.object(
            oc2, 'CLONE_SOURCE_ROOT', self.root / 'oc2-state' / 'clone-sources',
        )
        clone_root_patch.start()
        self.addCleanup(clone_root_patch.stop)
        (self.project / 'main.py').write_text('print("safe")\n')
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(
            ['git', '-C', str(self.project), 'config', 'user.email', 'test@example.invalid'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'config', 'user.name', 'Test Fixture'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'add', 'origin',
             'https://example.invalid/source.git'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'config',
             'http.https://example.invalid/.extraheader',
             'AUTHORIZATION: Basic c2VjcmV0LXBsYWNlaG9sZGVy'],
            check=True,
        )
        subprocess.run(['git', '-C', str(self.project), 'add', 'main.py'], check=True)
        subprocess.run(
            ['git', '-C', str(self.project), 'commit', '-qm', 'fixture'], check=True,
        )
        self.fake = FakeSbx()

    def _run(
        self,
        *extra_args: str,
        host_env: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        output = io.StringIO()
        args = [
            '--repo-root', str(self.repo), '--workspace', str(self.project),
            '--sandbox', 'oc2-test',
            *extra_args,
        ]
        env = host_env or {'OC_CF_ACCOUNT_ID': 'a' * 32, 'OC_CF_GATEWAY_ID': 'gateway-1'}
        with patch.dict(oc2.os.environ):
            for name in ('OC_CF_ACCOUNT_ID', 'OC_CF_GATEWAY_ID', 'OC_CF_API_TOKEN'):
                oc2.os.environ.pop(name, None)
            oc2.os.environ.update(env)
            with patch.object(oc2, 'Runner', return_value=self.fake), \
                    patch.object(oc2.shutil, 'which', return_value='/fake/sbx'), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                try:
                    status = oc2.main(args)
                except SystemExit as exc:
                    status = int(exc.code) if exc.code is not None else 0
        return status, output.getvalue()

    def _write_cloudflare_apm(self) -> None:
        (self.repo / 'apm.yml').write_text(
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
            '        Authorization: ""\n'
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
        )

    def test_clone_mode_installs_and_launches_only_pinned_v2(self) -> None:
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--clone' in call)
        self.assertEqual(create[:4], ('create', '--clone', '--name', 'oc2-test'))
        self.assertIn('--kit', create)
        self.assertEqual(create[-2], 'shell')
        self.assertNotEqual(pathlib.Path(create[-1]), self.project)
        self.assertEqual(self.fake.clone_source_content, 'print("safe")\n')
        self.assertEqual(self.fake.clone_source_remotes, 'origin\n')
        self.assertEqual(self.fake.clone_source_log_subject, 'OC2 sanitized workspace snapshot')
        self.assertFalse(self.fake.clone_source_has_http_header)
        self.assertTrue(pathlib.Path(create[-1]).exists())
        self.assertIsNotNone(self.fake.created_mixin_spec)
        install = next(call for call in self.fake.calls if call[:3] == (
            'exec', 'oc2-test', 'npm',
        ))
        self.assertEqual(install[-1], '@opencode/cli@2.2.5')
        if self.fake.copied_config is None:
            self.fail('V2 config was not copied into the Sandbox')
        copied_config = json.loads(self.fake.copied_config)
        self.assertEqual(copied_config['model'], 'openai/gpt-6-luna')
        self.assertIn('policies', copied_config)
        self.assertNotIn('plugin', copied_config)
        self.assertNotIn('mcp', copied_config)
        self.assertIn(900, self.fake.timeouts)
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertEqual(launch[3], '/home/agent/workspace/synthetic')
        self.assertIn('env', launch)
        self.assertIn('-i', launch)
        self.assertEqual(launch[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('opencode=v2.2.5', output)
        self.assertFalse(any('--collect' in call or '--apply' in call for call in self.fake.calls))

    def test_clone_mode_refuses_env_file_before_creating_sandbox(self) -> None:
        (self.project / '.env').write_text('TOKEN=fixture-only')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('clone mode would expose', output)
        self.assertFalse(self.fake.created)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_clone_mode_refuses_project_opencode_configuration(self) -> None:
        (self.project / 'opencode.json').write_text('{"mcp":{}}\n')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('OpenCode project configuration', output)
        self.assertFalse(self.fake.created)

    def test_existing_sandbox_is_not_reused_or_rebuilt(self) -> None:
        self.fake.created = True
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 1)
        self.assertIn('refusing to reuse or rebuild', output)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_external_provider_requires_explicit_authorization_before_sandbox_commands(self):
        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn('--allow-paid-inference', output)
        self.assertEqual(self.fake.calls, [])

    def test_prepare_only_skips_inference_authorization_and_sandbox_commands(self):
        status, output = self._run('--prepare-only')

        self.assertEqual(status, 0, output)
        self.assertIn('OC2_PREPARED_ONLY', output)
        self.assertEqual(self.fake.calls, [])

    def test_cloudflare_end_to_end_uses_proxy_placeholder_only(self):
        self._write_cloudflare_apm()
        status, output = self._run('--allow-paid-inference', host_env={
            'OC_CF_ACCOUNT_ID': 'a' * 32,
            'OC_CF_GATEWAY_ID': 'gateway-1',
            'OC_CF_API_TOKEN': 'sensitive-poison-value',
        })

        self.assertEqual(status, 0, output)
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertIn('OC_CF_ACCOUNT_ID=' + 'a' * 32, launch)
        self.assertIn('OC_CF_GATEWAY_ID=gateway-1', launch)
        self.assertIn('OC_CF_API_TOKEN=proxy-managed', launch)
        self.assertNotIn('OC_CF_REST_API_TOKEN=proxy-managed', launch)
        self.assertNotIn('sensitive-poison-value', repr(self.fake.calls))

    def test_cloudflare_missing_identifiers_stop_before_sandbox_commands(self):
        self._write_cloudflare_apm()
        status, output = self._run(
            '--allow-paid-inference',
            host_env={'OC_CF_ACCOUNT_ID': '', 'OC_CF_GATEWAY_ID': 'gateway-1'},
        )

        self.assertEqual(status, 1)
        self.assertIn('Cloudflare runtime identifiers', output)
        self.assertEqual(self.fake.calls, [])

    def test_launch_attaches_temporary_mixin_without_host_credentials(self):
        self._write_cloudflare_apm()
        poison = {
            'OPENAI_API_KEY': 'host-api-key-poison',
            'OPENAI_ACCESS_TOKEN': 'host-access-token-poison',
            'OPENAI_REFRESH_TOKEN': 'host-refresh-token-poison',
        }
        with patch.object(oc2, 'ROOT', str(self.root / 'guest-root')):
            status, output = self._run('--allow-paid-inference', host_env={
                    'OC_CF_ACCOUNT_ID': 'a' * 32,
                    'OC_CF_GATEWAY_ID': 'gateway-1',
                    **poison,
                },
            )

        self.assertEqual(status, 0, output)
        create = next(
            call for call in self.fake.calls
            if call[:1] == ('create',) and '--kit' in call
        )
        self.assertIn('--clone', create)
        self.assertIn('--kit', create)
        mixin_path = pathlib.Path(create[create.index('--kit') + 1])
        self.assertFalse(mixin_path.exists())
        self.assertIsNotNone(self.fake.created_mixin_spec)
        self.assertFalse(self.fake.mixin_exists_at_launch)
        mixin_spec_text = self.fake.created_mixin_spec
        assert mixin_spec_text is not None
        mixin_spec = yaml.safe_load(mixin_spec_text)
        self.assertFalse(any(
            value in mixin_spec_text for value in poison.values()
        ))
        self.assertEqual(mixin_spec['kind'], 'mixin')
        self.assertEqual(mixin_spec['schemaVersion'], '3')
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        home = next(value.split('=', 1)[1] for value in launch if value.startswith('HOME='))
        xdg_data_home = next(
            value.split('=', 1)[1] for value in launch
            if value.startswith('XDG_DATA_HOME=')
        )
        credential_path = next(
            item['config']['oauth']['credentialFile']['path']
            for item in mixin_spec['capabilities']
            if item['type'] == 'com.docker.sandbox/credential@1' and 'oauth' in item['config']
        )
        self.assertEqual(credential_path, '~/.local/share/opencode/auth.json')
        self.assertEqual(xdg_data_home, f'{home}/.local/share')
        oauth_auth_path = pathlib.Path(xdg_data_home) / 'opencode/auth.json'
        self.assertEqual(oauth_auth_path, pathlib.Path(home + credential_path[1:]))
        oauth_auth_path.parent.mkdir(parents=True)
        oauth_auth_path.write_text(json.dumps({
            'openai': {
                'type': 'oauth', 'access': 'test-access',
                'refresh': 'test-refresh', 'expires': 123,
            },
        }))
        helper_namespace = {'__name__': '__main__'}
        previous_bootstrap = sys.modules.get('oc2_oauth_bootstrap')
        observed_auth = []

        def capture_auth(auth):
            observed_auth.append(auth)
            raise ValueError('credential file observed')

        helper_source = oc2.oauth_helper_source(SCRIPTS)
        helper_source = helper_source.replace(
            "if __name__ == '__main__':\n    try:",
            "if __name__ == '__main__':\n    validate_db = lambda _: None\n"
            "    record_from_auth = capture_auth\n    try:",
            1,
        )
        try:
            with patch.dict(os.environ, {
                'XDG_DATA_HOME': xdg_data_home,
                'OPENCODE_DB': str(pathlib.Path(home) / 'a/b/c/d/opencode.db'),
            }), patch.object(sys, 'argv', ['oc2_oauth.py', 'opencode']), \
                    self.assertRaises(SystemExit):
                exec(helper_source, {'__name__': '__main__', 'capture_auth': capture_auth})
        finally:
            if previous_bootstrap is None:
                sys.modules.pop('oc2_oauth_bootstrap', None)
            else:
                sys.modules['oc2_oauth_bootstrap'] = previous_bootstrap
        self.assertEqual(observed_auth[0]['openai']['access'], 'test-access')
        self.assertNotIn('OPENAI_API_KEY', launch)
        self.assertFalse(any(value in repr(self.fake.calls) for value in poison.values()))
        self.assertNotIn('auth.json', self.fake.copied_files)

    def test_launcher_stops_when_sbx_lacks_kit_support(self):
        self.fake.kit_supported = False
        status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 1)
        self.assertIn('Mixin', output)
        self.assertFalse(any(call[:1] == ('create',) and '--clone' in call
                             for call in self.fake.calls))

    def test_clone_mode_refuses_credentials_in_git_metadata_before_creation(self) -> None:
        config = self.project / '.git' / 'config'
        config.write_text(
            '[remote "origin"]\nurl = https://user:password@example.invalid/repo.git\n',
        )
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('Git metadata contains credential', output)
        self.assertFalse(self.fake.created)

    def test_clone_mode_refuses_credentials_in_remote_query_before_creation(self) -> None:
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'set-url', 'origin',
             'https://example.invalid/source.git?access_token=fixture-token-material-123456'],
            check=True,
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn('Git remote contains credential', output)
        self.assertFalse(self.fake.created)

    def test_clone_mode_refuses_signed_remote_url_before_creation(self) -> None:
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'set-url', 'origin',
             'https://example.invalid/source.git?sig=Ab12Cd34Ef56Gh78'],
            check=True,
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn('Git remote contains credential', output)
        self.assertFalse(self.fake.created)

    def test_clone_source_survives_ambiguous_sandbox_creation_failure(self) -> None:
        original_sbx = self.fake.sbx

        def fail_after_create(*args: str, capture: bool = False, tty: bool = False,
                              timeout: int | None = 180) -> str:
            result = original_sbx(*args, capture=capture, tty=tty, timeout=timeout)
            if args[0] == 'create' and '--clone' in args:
                raise oc2.Stop('simulated ambiguous create failure')
            return result

        with patch.object(self.fake, 'sbx', side_effect=fail_after_create):
            status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 1)
        self.assertIn('simulated ambiguous create failure', output)
        self.assertTrue(self.fake.created, (output, self.fake.calls))
        clone_source = self.fake.clone_source
        self.assertIsNotNone(clone_source)
        assert clone_source is not None
        self.assertTrue(clone_source.exists())

    def test_clone_mode_uses_validated_snapshot_after_host_changes(self) -> None:
        validate = oc2.validate_clone_workspace

        def validate_then_mutate(snapshot: pathlib.Path) -> None:
            validate(snapshot)
            if snapshot != self.project:
                (self.project / 'main.py').write_text('print("changed after inspection")\n')

        with patch.object(oc2, 'validate_clone_workspace', side_effect=validate_then_mutate):
            status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 0, output)
        create = next(
            call for call in self.fake.calls if call[0] == 'create' and '--clone' in call
        )
        clone_source = pathlib.Path(create[-1])
        self.assertNotEqual(clone_source, self.project)
        self.assertTrue(clone_source.exists())
        self.assertEqual(self.fake.clone_source_content, 'print("safe")\n')
        self.assertEqual(self.fake.clone_source_remotes, 'origin\n')
        self.assertEqual(self.fake.clone_source_log_subject, 'OC2 sanitized workspace snapshot')
        self.assertFalse(self.fake.clone_source_has_http_header)
        self.assertEqual((self.project / 'main.py').read_text(),
                         'print("changed after inspection")\n')


if __name__ == '__main__':
    unittest.main()
