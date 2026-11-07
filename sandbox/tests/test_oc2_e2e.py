from __future__ import annotations

import contextlib
import hashlib
import io
import json
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
import oc2_assets  # noqa: E402


def _oc2_extensions(*, include_agents: bool = True) -> str:
    agents = (
        'x-oc2-agents:\n'
        '  hephaestus:\n'
        '    mode: primary\n'
        '    model: openai/gpt-6-luna\n'
        '  oracle:\n'
        '    mode: subagent\n'
        '    model: openai/gpt-6-luna\n'
        if include_agents else 'x-oc2-agents: {}\n'
    )
    return (
        'x-oc2-assets:\n' + ''.join(
            f'  - {source}\n' for source in oc2_assets.SOURCE_TO_TARGET
        ) +
        agents +
        'x-oc2-mcp:\n'
        '  enabled: false\n'
        '  servers: []\n'
    )


class FakeSbx:
    def __init__(self):
        self.created = False
        self.installed = False
        self.kit_supported = True
        self.copied_config: str | None = None
        self.copied_files: dict[str, str] = {}
        self.workspace_files: dict[str, bytes] = {}
        self.workspace_destination: str | None = None
        self.remote_files: dict[str, bytes] = {}
        self.created_mixin_spec: str | None = None
        self.created_mixin_path: pathlib.Path | None = None
        self.created_runtime_mixin_spec: str | None = None
        self.created_cli_binary: bytes | None = None
        self.mixin_exists_at_launch: bool | None = None
        self.sandbox_cloudflare_secret = True
        self.global_cloudflare_secret = False
        self.secret_set_fails = False
        self.secret_set_stores = True
        self.secret_set_tty: bool | None = None
        self.secret_calls: list[tuple[str, ...]] = []
        self.calls: list[tuple[str, ...]] = []
        self.user = oc2.getpass.getuser()

    @staticmethod
    def _secret_listing(scope: str | None) -> str:
        secrets = []
        if scope is not None:
            secrets.append({
                'name': 'cloudflare-ai-gateway',
                'scope': scope,
                'secret': '(stored)',
                'type': 'service',
            })
        return json.dumps({'secrets': secrets})

    def destination_status(self, name: str, destination: str) -> int:
        self.calls.append(('destination_status', name, destination))
        return 10 if destination == self.workspace_destination or destination in self.remote_files else 0

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        self.calls.append(args)
        if args == (
            'secret', 'ls', '--sandbox', 'oc2-test', '--service',
            'cloudflare-ai-gateway', '--json',
        ):
            self.secret_calls.append(args)
            scope = 'oc2-test' if self.sandbox_cloudflare_secret else None
            return self._secret_listing(scope)
        if args == (
            'secret', 'ls', '--global', '--service', 'cloudflare-ai-gateway', '--json',
        ):
            self.secret_calls.append(args)
            scope = '(global)' if self.global_cloudflare_secret else None
            return self._secret_listing(scope)
        if args == ('secret', 'set', 'cloudflare-ai-gateway', '--sandbox', 'oc2-test'):
            self.secret_calls.append(args)
            self.secret_set_tty = tty
            if self.secret_set_fails:
                raise oc2.Stop('sbx command failed (exit 1)')
            if self.secret_set_stores:
                self.sandbox_cloudflare_secret = True
            return ''
        if args == ('version',):
            return 'sbx version v0.49.2 test\n'
        if args == ('create', '--help'):
            return '  --kit  compose a Mixin\n' if self.kit_supported else ''
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args[:1] == ('create',):
            kit_paths = [
                pathlib.Path(args[index + 1])
                for index, value in enumerate(args[:-1])
                if value == '--kit'
            ]
            if kit_paths:
                self.created_mixin_path = kit_paths[0]
                self.created_mixin_spec = (kit_paths[0] / 'spec.yaml').read_text()
            if len(kit_paths) > 1:
                self.created_runtime_mixin_spec = (
                    kit_paths[1] / 'spec.yaml'
                ).read_text()
                binary = kit_paths[1] / 'opencode'
                if binary.is_file() and not binary.is_symlink():
                    self.created_cli_binary = binary.read_bytes()
                self.installed = (
                    'opencode-cli@2.2.5' in self.created_runtime_mixin_spec
                    and self.created_cli_binary is not None
                )
            self.created = True
            return ''
        if args[:1] == ('cp',):
            source = pathlib.Path(args[1])
            destination = args[2]
            remote_destination = destination.split(':', 1)[1]
            if source.is_dir():
                self.workspace_destination = remote_destination
                for path in source.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        relative = path.relative_to(source).as_posix()
                        data = path.read_bytes()
                        self.workspace_files[relative] = data
                        self.remote_files[remote_destination + '/' + relative] = data
                return ''
            contents = source.read_text()
            self.copied_files[destination] = contents
            self.remote_files[remote_destination] = source.read_bytes()
            if destination.endswith('/config/opencode/opencode.jsonc'):
                self.copied_config = contents
            return ''
        if args[:2] == ('exec', 'oc2-test'):
            command = args[2:]
            if command[:2] == ('bash', '-c'):
                return 'missing\n'
            if command[:1] == ('sha256sum',):
                data = self.remote_files.get(command[1])
                return (hashlib.sha256(data).hexdigest() + '  ' + command[1] + '\n'
                        if data is not None else '')
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
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        self._copy_native_asset_sources()
        self._write_cloudflare_apm()
        self.project = self.root / 'synthetic'
        self.project.mkdir()
        (self.project / 'main.py').write_text('print("safe")\n')
        self.cli_artifact = self.root / 'verified-opencode'
        self.cli_artifact.write_bytes(b'offline fake CLI artifact; never executed')
        self.cli_artifact.chmod(0o600)
        self.download_patch = patch.object(
            oc2, 'download_verified_cli', return_value=self.cli_artifact,
        )
        self.download_patch.start()
        self.addCleanup(self.download_patch.stop)
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
        stdin_tty: bool | None = None,
    ) -> tuple[int, str]:
        output = io.StringIO()
        args = [
            '--repo-root', str(self.repo), '--workspace', str(self.project),
            '--sandbox', 'oc2-test',
            *extra_args,
        ]
        env = host_env or {'OC_CF_ACCOUNT_ID': 'a' * 32, 'OC_CF_GATEWAY_ID': 'gateway-1'}
        tty_context = (
            contextlib.nullcontext()
            if stdin_tty is None
            else patch.object(oc2.sys, 'stdin', FakeInput(stdin_tty))
        )
        with patch.dict(oc2.os.environ), tty_context:
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
            _oc2_extensions() +
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

    def _copy_native_asset_sources(self) -> None:
        source_root = pathlib.Path(oc2.__file__).resolve().parents[2]
        for source in (*oc2_assets.SOURCE_TO_TARGET, oc2_assets.THEME_SOURCE):
            destination = self.repo / source
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((source_root / source).read_bytes())

    def test_cloudflare_sandbox_secret_is_checked_before_workspace_and_tui(self):
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway',
        )

        self.assertEqual(status, 0, output)
        sandbox_check = (
            'secret', 'ls', '--sandbox', 'oc2-test', '--service',
            'cloudflare-ai-gateway', '--json',
        )
        self.assertIn(sandbox_check, self.fake.secret_calls)
        self.assertFalse(any(call[:2] == ('secret', 'set') for call in self.fake.secret_calls))
        check_index = self.fake.calls.index(sandbox_check)
        create_index = next(
            index for index, call in enumerate(self.fake.calls)
            if call[:2] == ('create', '--name')
        )
        workspace_copy_index = next(
            index for index, call in enumerate(self.fake.calls)
            if call[:1] == ('cp',) and ':/' in call[2]
        )
        launch_index = next(
            index for index, call in enumerate(self.fake.calls)
            if call[:2] == ('exec', '-it')
        )
        self.assertLess(create_index, check_index)
        self.assertLess(check_index, workspace_copy_index)
        self.assertLess(check_index, launch_index)

    def test_missing_cloudflare_secret_without_terminal_stops_before_transfer(self):
        self.fake.sandbox_cloudflare_secret = False
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway', stdin_tty=False,
        )

        self.assertNotEqual(status, 0)
        self.assertIn('interactive terminal', output)
        self.assertFalse(any(call[:2] == ('secret', 'set') for call in self.fake.secret_calls))
        self.assertIsNone(self.fake.workspace_destination)
        self.assertFalse(any(call[:2] == ('exec', '-it') for call in self.fake.calls))

    def test_cloudflare_default_model_requires_secret_without_mode_flag(self):
        apm = self.repo / 'apm.yml'
        apm.write_text(apm.read_text().replace(
            'default_model: openai/gpt-6-luna',
            'default_model: cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code',
        ))
        self.fake.sandbox_cloudflare_secret = False

        status, output = self._run('--allow-paid-inference', stdin_tty=False)

        self.assertNotEqual(status, 0)
        self.assertIn('interactive terminal', output)
        self.assertIn(
            ('secret', 'ls', '--sandbox', 'oc2-test', '--service',
             'cloudflare-ai-gateway', '--json'),
            self.fake.secret_calls,
        )
        self.assertIsNone(self.fake.workspace_destination)
        self.assertFalse(any(call[:2] == ('exec', '-it') for call in self.fake.calls))

    def test_missing_cloudflare_secret_is_set_in_sandbox_scope_and_verified(self):
        self.fake.sandbox_cloudflare_secret = False
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway', stdin_tty=True,
        )

        self.assertEqual(status, 0, output)
        self.assertIn(
            ('secret', 'set', 'cloudflare-ai-gateway', '--sandbox', 'oc2-test'),
            self.fake.secret_calls,
        )
        self.assertTrue(self.fake.secret_set_tty)
        self.assertEqual(
            self.fake.secret_calls[-1],
            ('secret', 'ls', '--sandbox', 'oc2-test', '--service',
             'cloudflare-ai-gateway', '--json'),
        )
        self.assertTrue(any(call[:2] == ('exec', '-it') for call in self.fake.calls))

    def test_existing_global_cloudflare_secret_is_read_only(self):
        self.fake.sandbox_cloudflare_secret = False
        self.fake.global_cloudflare_secret = True
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway', stdin_tty=False,
        )

        self.assertEqual(status, 0, output)
        self.assertIn(
            ('secret', 'ls', '--global', '--service', 'cloudflare-ai-gateway', '--json'),
            self.fake.secret_calls,
        )
        self.assertFalse(any(call[:2] == ('secret', 'set') for call in self.fake.secret_calls))

    def test_cloudflare_secret_set_failure_stops_before_workspace_transfer(self):
        self.fake.sandbox_cloudflare_secret = False
        self.fake.secret_set_fails = True
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway', stdin_tty=True,
        )

        self.assertNotEqual(status, 0)
        self.assertIsNone(self.fake.workspace_destination)
        self.assertFalse(any(call[:2] == ('exec', '-it') for call in self.fake.calls))

    def test_configuration_without_gateway_provider_skips_cloudflare_secret(self):
        (self.repo / 'apm.yml').write_text(
            _oc2_extensions(include_agents=False) +
            'shell: bash\n'
            'snapshot: true\n',
        )

        status, output = self._run()

        self.assertEqual(status, 0, output)
        self.assertFalse(self.fake.secret_calls)
        self.assertTrue(any(call[:2] == ('exec', '-it') for call in self.fake.calls))

    def test_mountless_snapshot_installs_and_launches_only_pinned_v2(self):
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--name' in call)
        self.assertEqual(create[:3], ('create', '--name', 'oc2-test'))
        self.assertIn('--kit', create)
        self.assertNotIn('--clone', create)
        self.assertNotIn(str(self.project), create)
        self.assertIsNotNone(self.fake.created_mixin_spec)
        self.assertEqual(create[-1], oc2.SHELL_WORKLOAD)
        self.assertEqual(create.count('--kit'), 2)
        self.assertIsNotNone(self.fake.created_runtime_mixin_spec)
        if self.fake.created_runtime_mixin_spec is None:
            self.fail('Pinned OpenCode CLI Mixin was not included')
        self.assertIn('opencode-cli@2.2.5', self.fake.created_runtime_mixin_spec)
        self.assertIn('COPY --chmod=0755 opencode', self.fake.created_runtime_mixin_spec)
        self.assertEqual(self.fake.created_cli_binary, self.cli_artifact.read_bytes())
        self.assertFalse(any(call[:3] == ('exec', 'oc2-test', 'npm')
                             for call in self.fake.calls))
        if self.fake.copied_config is None:
            self.fail('V2 config was not copied into the Sandbox')
        copied_config = json.loads(self.fake.copied_config)
        self.assertEqual(copied_config['model'], 'openai/gpt-6-luna')
        self.assertNotIn('cloudflare-ai-gateway-custom', copied_config['providers'])
        self.assertIn('policies', copied_config)
        self.assertEqual(len(copied_config['instructions']), 7)
        self.assertNotIn('plugin', copied_config)
        self.assertNotIn('mcp', copied_config)
        self.assertTrue(any('/assets/' in name and name.endswith('.json')
                            for name in self.fake.copied_files))
        self.assertTrue(any('--install-assets-runtime' in call for call in self.fake.calls))
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertEqual(launch[3], self.fake.workspace_destination)
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, launch)
        self.assertNotIn('-i', launch)
        self.assertIn('OPENCODE_CONFIG_PROJECT_DISABLE=1', launch)
        self.assertEqual(launch[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('opencode=v2.2.5', output)
        self.assertFalse(any('--collect' in call or '--apply' in call for call in self.fake.calls))

    def test_openai_mode_hides_cloudflare_without_secret_or_terminal(self):
        self.fake.sandbox_cloudflare_secret = False
        status, output = self._run('--allow-paid-inference', stdin_tty=False)

        self.assertEqual(status, 0, output)
        copied_config = json.loads(self.fake.copied_config)
        self.assertEqual(copied_config['model'], 'openai/gpt-6-luna')
        self.assertNotIn('cloudflare-ai-gateway-custom', copied_config['providers'])
        self.assertFalse(self.fake.secret_calls)

    def test_mountless_snapshot_excludes_env_file_before_transfer(self):
        (self.project / '.env').write_text('TOKEN=fixture-only')
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 0, output)
        self.assertTrue(self.fake.created)
        self.assertNotIn('.env', self.fake.workspace_files)

    def test_mountless_workspace_excludes_project_opencode_configuration(self):
        (self.project / 'opencode.json').write_text('{"mcp":{}}\n')
        (self.project / '.opencode').mkdir()
        (self.project / '.opencode' / 'opencode.jsonc').write_text('{"provider":"unsafe"}\n')
        status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--name' in call)
        self.assertEqual(create[:3], ('create', '--name', 'oc2-test'))
        self.assertEqual(create[-1], oc2.SHELL_WORKLOAD)
        self.assertNotIn('--clone', create)
        self.assertNotIn(str(self.project), create)
        self.assertEqual(set(self.fake.workspace_files), {'main.py'})
        self.assertFalse(any(path.startswith('.opencode/') or path in {
            'opencode.json', 'opencode.jsonc', 'cli.json', '.git/config',
        } for path in self.fake.workspace_files))

    def test_dotfiles_ai_profile_excludes_workspace_apm_but_exports_host_apm(self):
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'add', 'origin',
             'git@github.com:yohi/dotfiles-ai.git'],
            check=True,
        )
        (self.project / 'apm.yml').write_text('apiKey: ' + 'C' * 32 + '\n')

        status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 0, output)
        self.assertNotIn('apm.yml', self.fake.workspace_files)
        self.assertIsNotNone(self.fake.copied_config)
        if self.fake.copied_config is None:
            self.fail('Host APM export was not copied into the Sandbox')
        copied_config = json.loads(self.fake.copied_config)
        self.assertEqual(copied_config['model'], 'openai/gpt-6-luna')

    def test_existing_sandbox_is_not_reused_or_rebuilt(self):
        self.fake.created = True
        status, output = self._run('--allow-paid-inference')
        self.assertEqual(status, 1)
        self.assertIn('refusing to reuse or rebuild', output)
        self.assertFalse(any(call[0] == 'create' and '--name' in call for call in self.fake.calls))

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
        status, output = self._run(
            '--allow-paid-inference', '--use-cloudflare-ai-gateway',
            host_env={
                'OC_CF_ACCOUNT_ID': 'a' * 32,
                'OC_CF_GATEWAY_ID': 'gateway-1',
                'OC_CF_API_TOKEN': 'sensitive-poison-value',
            },
        )

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
            '--allow-paid-inference', '--use-cloudflare-ai-gateway',
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
        status, output = self._run(
            '--allow-paid-inference',
            host_env={
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
        self.assertNotIn('--clone', create)
        self.assertNotIn(str(self.project), create)
        self.assertIn('--kit', create)
        mixin_path = pathlib.Path(create[create.index('--kit') + 1])
        self.assertFalse(mixin_path.exists())
        self.assertIsNotNone(self.fake.created_mixin_spec)
        self.assertFalse(self.fake.mixin_exists_at_launch)
        mixin_spec = yaml.safe_load(self.fake.created_mixin_spec)
        self.assertFalse(any(
            value in self.fake.created_mixin_spec for value in poison.values()
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
        self.assertEqual(f'{xdg_data_home}/opencode/auth.json', f'{home}{credential_path[1:]}')
        self.assertNotIn('OPENAI_API_KEY', launch)
        self.assertFalse(any(value in repr(self.fake.calls) for value in poison.values()))
        self.assertNotIn('auth.json', self.fake.copied_files)

    def test_launcher_stops_when_sbx_lacks_kit_support(self):
        self.fake.kit_supported = False
        status, output = self._run('--allow-paid-inference')

        self.assertEqual(status, 1)
        self.assertIn('Mixin', output)
        self.assertFalse(any(call[:1] == ('create',) and '--name' in call
                             for call in self.fake.calls))


class FakeInput:
    def __init__(self, is_tty: bool):
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


if __name__ == '__main__':
    unittest.main()
