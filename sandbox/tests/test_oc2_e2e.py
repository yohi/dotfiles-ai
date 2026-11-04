from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2  # noqa: E402


class FakeSbx:
    def __init__(self):
        self.created = False
        self.installed = False
        self.copied_config: str | None = None
        self.copied_files: dict[str, str] = {}
        self.calls: list[tuple[str, ...]] = []

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        self.calls.append(args)
        if args == ('version',):
            return 'sbx version v0.49.2 test\n'
        if args == ('create', '--help'):
            return '  --clone  private in-container clone\n'
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args[:1] == ('create',):
            self.created = True
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
            return ''
        return ''


class LauncherFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        self._write_cloudflare_apm()
        self.project = self.root / 'synthetic'
        self.project.mkdir()
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
                    status = int(exc.code)
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

    def test_clone_mode_installs_and_launches_only_pinned_v2(self):
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--clone' in call)
        self.assertEqual(
            create,
            ('create', '--clone', '--name', 'oc2-test', 'shell', str(self.project)),
        )
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
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertEqual(launch[3], '/home/agent/workspace/synthetic')
        self.assertIn('env', launch)
        self.assertIn('-i', launch)
        self.assertEqual(launch[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('opencode=v2.2.5', output)
        self.assertFalse(any('--collect' in call or '--apply' in call for call in self.fake.calls))

    def test_clone_mode_refuses_env_file_before_creating_sandbox(self):
        (self.project / '.env').write_text('TOKEN=fixture-only')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('clone mode would expose', output)
        self.assertFalse(self.fake.created)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_clone_mode_refuses_project_opencode_configuration(self):
        (self.project / 'opencode.json').write_text('{"mcp":{}}\n')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('OpenCode project configuration', output)
        self.assertFalse(self.fake.created)

    def test_existing_sandbox_is_not_reused_or_rebuilt(self):
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

    def test_launch_installs_oauth_seed_without_host_credentials(self):
        self._write_cloudflare_apm()
        poison = {
            'OPENAI_API_KEY': 'host-api-key-poison',
            'OPENAI_ACCESS_TOKEN': 'host-access-token-poison',
            'OPENAI_REFRESH_TOKEN': 'host-refresh-token-poison',
        }
        status, output = self._run(
            '--allow-paid-inference',
            host_env={
                'OC_CF_ACCOUNT_ID': 'a' * 32,
                'OC_CF_GATEWAY_ID': 'gateway-1',
                **poison,
            },
        )

        self.assertEqual(status, 0, output)
        auth_path = next(
            destination for destination in self.fake.copied_files
            if destination.endswith('/data/opencode/auth.json')
        )
        auth = json.loads(self.fake.copied_files[auth_path])
        self.assertEqual(auth['openai']['access'], 'oai-oat01-proxy-managed')
        self.assertEqual(auth['openai']['refresh'], 'oai-ort01-proxy-managed')
        self.assertEqual(auth['openai']['expires'], 0)
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertNotIn('OPENAI_API_KEY', launch)
        self.assertFalse(any(value in repr(self.fake.calls) for value in poison.values()))
        self.assertFalse(any(value in self.fake.copied_files[auth_path] for value in poison.values()))


if __name__ == '__main__':
    unittest.main()
