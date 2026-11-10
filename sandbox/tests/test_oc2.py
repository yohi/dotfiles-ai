"""Offline tests for the host launcher and guest config materializer.

No sbx, sudo, network, package installation, or OpenCode binary is invoked.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from types import ModuleType
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str) -> ModuleType:
    """Load a sandbox script from its source path for offline testing."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    if spec is None or spec.loader is None:
        raise ImportError(f'could not load module: {name}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


oc2 = load('oc2')
guest = load('oc2_guest')
assets = load('oc2_assets')


class FakeRunner:
    def __init__(
        self,
        rows: list[Mapping[str, str]] | None = None,
        inspection: Mapping[
            str,
            str | list[Mapping[str, str]] | Mapping[str, str],
        ] | None = None,
    ) -> None:
        self.user = oc2.getpass.getuser()
        self.rows = rows or []
        self.inspection = (
            {'name': 'oc2-dev', 'runtime_mounts': []}
            if inspection is None else inspection
        )
        self.calls = []

    def sbx(self, *args: str, **kwargs: str | float | bool) -> str:
        self.calls.append(args)
        if args == ('ls', '-q'):
            return '\n'.join(row['name'] for row in self.rows)
        if args == ('ls', '--format', 'json'):
            return json.dumps(self.rows)
        if args == ('inspect', 'oc2-dev', '--json'):
            return json.dumps(self.inspection)
        if args[:2] == ('exec', 'oc2-dev') and 'sha256sum' in args:
            return '0' * 64 + ' /tmp/file\n'
        return ''


class HostTest(unittest.TestCase):
    def test_sbx_uses_requested_timeout_and_preserves_default_and_tty(self) -> None:
        runner = oc2.Runner(oc2.getpass.getuser())
        completed = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        with patch.object(oc2.subprocess, 'run', return_value=completed) as run:
            runner.sbx('list')
            runner.sbx('list', timeout=900)
            oc2.execute(runner, 'oc2-dev', 'npm', 'install', timeout=720)
            runner.sbx('exec', '-it', 'oc2-dev', tty=True, timeout=900)

        self.assertEqual(run.call_args_list[0].kwargs['timeout'], 180)
        self.assertEqual(run.call_args_list[1].kwargs['timeout'], 900)
        self.assertEqual(run.call_args_list[2].kwargs['timeout'], 720)
        self.assertIsNone(run.call_args_list[3].kwargs['timeout'])

    def test_provision_cli_uses_extended_install_timeout(self) -> None:
        runner = FakeRunner()
        with patch.object(oc2, 'cli_path', side_effect=[None, oc2.PINNED[0]]), \
             patch.object(oc2, 'seed_cli', return_value=None), \
             patch.object(oc2, 'execute') as execute:
            result = oc2.provision_cli(runner, 'oc2-dev', 'oc-v2-poc')

        self.assertEqual(result, oc2.PINNED[0])
        self.assertEqual(execute.call_args.kwargs['timeout'], 900)

    def test_missing_sandbox(self) -> None:
        runner = FakeRunner()
        self.assertFalse(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mountless_sandbox_reused(self) -> None:
        # sbx v0.49.2 omits mount-related fields from ls --format json.
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}])
        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))
        self.assertIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_mounted_workspace_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell',
                              'workspace': '/home/' + 'user/repo'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_missing_runtime_mounts_evidence_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev'})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_runtime_mounts_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev',
                                        'runtime_mounts': [{'source': '/home/' + 'user'}]})
        with self.assertRaisesRegex(oc2.Stop, 'runtime mounts'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_inspect_name_mismatch_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'other-sandbox', 'runtime_mounts': []})
        with self.assertRaisesRegex(oc2.Stop, 'identity mismatch'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_invalid_runtime_mounts_type_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev', 'runtime_mounts': {}})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_list_workspace_mount_rejected_even_if_inspect_empty(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell',
                              'workspace': '/home/' + 'user/source'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')
        self.assertNotIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_wrong_agent_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'opencode', 'workspace': '-'}])
        with self.assertRaisesRegex(oc2.Stop, 'not shell'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_dry_run_no_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('must not call sbx')):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(oc2.main(['--repo-root', tmp, '--dry-run']), 0)
                self.assertIn('mountless sandbox', out.getvalue())

    def test_invalid_sandbox_name_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            self.assertEqual(oc2.main(['--repo-root', tmp, '--sandbox', '../bad', '--dry-run']), 1)

    def test_launch_uses_standalone_no_host_env(self) -> None:
        runner = FakeRunner()
        oc2.launch(runner, 'oc2-dev', 'a' * 64, oc2.PINNED[0])
        command = runner.calls[-1]
        self.assertEqual(command[:3], ('exec', '-it', '-w'))
        self.assertEqual(command[3], oc2.ROOT + '/runtime/' + 'a' * 16 + '/project')
        self.assertEqual(command[4:7], ('oc2-dev', 'env', '-i'))
        self.assertEqual(command[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('OPENCODE_WATCHDOG_ENABLED=false', command)
        self.assertNotIn('bash', command)
        self.assertNotIn('--mount', command)

    def test_stage_does_not_depend_on_bash_positional_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# harmless guest fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()

            class StagingRunner:
                def __init__(self) -> None:
                    self.calls = []

                def sbx(self, *args: str, **kwargs: str | float | bool) -> str:
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        # No synthetic $0/$1/$2 follows the bash code.
                        assert len(args) == 5, args
                        assert '$1' not in args[4] and '$2' not in args[4]
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return script_sha + '  oc2_guest.py\n'
                    return ''

            runner = StagingRunner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script)
            self.assertIn(
                ('exec', 'oc2-dev', 'mkdir', '-p', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts'),
                runner.calls,
            )
            self.assertIn(
                ('exec', 'oc2-dev', 'chmod', '700', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts'),
                runner.calls,
            )
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 2)

    def test_stage_selected_assets_with_bounded_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            asset = root / 'oc2-assets.json'
            asset.write_text('{"fixture":true}')
            asset_sha = hashlib.sha256(asset.read_bytes()).hexdigest()

            class Runner:
                def __init__(self) -> None:
                    self.calls = []

                def sbx(self, *args: str, **kwargs: str | float | bool) -> str:
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return ((asset_sha if '/assets/' in args[3] else script_sha)
                                + '  verified\n')
                    return ''

            runner = Runner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script, asset, asset_sha)
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 3)
            start = [c for c in runner.calls if c[:3] ==
                     ('exec', 'oc2-dev', 'python3')]
            self.assertEqual(len(start), 1)
            self.assertIn('--expected-assets-sha', start[0])
            self.assertIn(asset_sha, start[0])
            self.assertIn('--assets', start[0])

    def test_stage_selected_assets_sha_mismatch_stops(self) -> None:
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

            class Runner:
                def sbx(self, *args: str, **kwargs: str | float | bool) -> str:
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return (('f' * 64 if '/assets/' in args[3] else script_sha)
                                + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, expected)

    def test_cli_version_probe_avoids_bash_positional_arguments(self) -> None:
        class VersionRunner:
            def __init__(self) -> None:
                self.calls = []

            def sbx(self, *args: str, **kwargs: str | float | bool) -> str:
                self.calls.append(args)
                assert args[:4] == ('exec', 'oc2-dev', 'bash', '-c')
                assert len(args) == 5
                assert '$1' not in args[4]
                return 'opencode v2.1.4\n'

        runner = VersionRunner()
        self.assertEqual(oc2.cli_path(runner, 'oc2-dev'), oc2.PINNED[0])
        self.assertEqual(len(runner.calls), 1)

    def test_launch_rejects_unapproved_binary(self) -> None:
        with self.assertRaisesRegex(oc2.Stop, 'unapproved'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'a' * 64, '/tmp/untrusted')

    def test_launch_rejects_invalid_digest(self) -> None:
        with self.assertRaisesRegex(oc2.Stop, 'invalid runtime digest'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'not-a-digest', oc2.PINNED[0])

    def test_seed_cli_uses_private_operator_home_staging(self) -> None:
        runner = FakeRunner()
        runner.user = oc2.getpass.getuser()
        home = pathlib.Path.home()
        staging = home / '.oc2-seed-AbCd1234'
        completed = subprocess.CompletedProcess(
            [], 0, stdout=f'{home}\n{staging}\n'
        )

        def sbx(*args: str, **kwargs: str | float | bool) -> str:
            runner.calls.append(args)
            if args[:3] == ('exec', 'oc-v2-poc', 'bash'):
                return 'opencode v2.1.4'
            return ''

        with patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
             patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]), \
             patch.object(runner, 'sbx', side_effect=sbx) as sbx_mock, \
             patch.object(oc2.subprocess, 'run', return_value=completed) as run:
            result = oc2.seed_cli(runner, 'oc2-dev', 'oc-v2-poc')

        self.assertEqual(result, oc2.PINNED[0])
        command = run.call_args_list[0].args[0]
        self.assertIn('mktemp -d "$HOME/.oc2-seed-XXXXXXXX"', command[2])
        self.assertNotIn('/tmp', ' '.join(command))
        self.assertIn(str(staging / 'node_modules'), repr(runner.calls))
        copy_calls = [call for call in sbx_mock.call_args_list
                      if call.args[0] == 'cp']
        self.assertEqual(len(copy_calls), 2)
        self.assertTrue(all(call.kwargs['timeout'] == 900 for call in copy_calls))

    def test_seed_cli_rejects_publicly_writable_staging_path(self) -> None:
        runner = FakeRunner()
        runner.user = oc2.getpass.getuser()
        completed = subprocess.CompletedProcess(
            [], 0, stdout='/tmp/oc2-seed-AbCd1234\n'
        )
        with patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
             patch.object(runner, 'sbx', return_value='opencode v2.1.4') as sbx, \
             patch.object(oc2.subprocess, 'run', return_value=completed):
            with self.assertRaisesRegex(oc2.Stop, 'unsafe seed staging path'):
                oc2.seed_cli(runner, 'oc2-dev', 'oc-v2-poc')
        self.assertFalse(any(
            call.args[0][0] == 'cp' for call in sbx.call_args_list
        ))


class GuestTest(unittest.TestCase):
    def setUp(self) -> None:
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
        self.manifest = {'schema': 'dotfiles-ai/sandbox-export/v0', 'generator': 'v0.1',
                         'opencode_version': '2.1.4', 'plugins_exported': 0,
                         'mcp_entries_exported': 0, 'artifacts_sha256': hashes}
        (self.bundle / 'export-manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self) -> None:
        guest.BASE = self.orig
        self.tmp.cleanup()

    def test_materialize_idempotently(self) -> None:
        digest = guest.verify(self.bundle)
        d1 = guest.prepare(self.bundle, digest)
        d2 = guest.prepare(self.bundle, digest)
        self.assertEqual(d1, d2)
        self.assertTrue((d1 / 'config/opencode/cli.json').exists())
        self.assertTrue((d1 / 'project').is_dir())

    def test_manifest_tampering_stops(self) -> None:
        (self.bundle / 'opencode.jsonc').write_text('{"shell":"zsh"}')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            guest.verify(self.bundle)

    def test_extra_secret_file_stops(self) -> None:
        (self.bundle / '.env').write_text('SECRET=present')
        with self.assertRaisesRegex(ValueError, 'bundle'):
            guest.verify(self.bundle)

    def test_symlink_rejected(self) -> None:
        p = self.bundle / 'cli.json'
        p.unlink()
        p.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            guest.verify(self.bundle)

    def _assets(self) -> tuple[pathlib.Path, str]:
        names = sorted(guest.ASSET_TARGETS)
        contents = {name: ('# selected text\n' if name != 'theme.json'
                           else '{"name":"tokyonight"}')
                    for name in names}
        hashes = {name: hashlib.sha256(data.encode('utf-8')).hexdigest()
                  for name, data in contents.items()}
        payload = {'schema': guest.ASSET_SCHEMA, 'files': contents, 'sha256': hashes}
        directory = self.base / 'assets'
        directory.mkdir(exist_ok=True)
        path = directory / 'assets.json'
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_assets_materialize_and_reuse(self) -> None:
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

    def _assert_unapproved_asset_rejected(self, name: str) -> None:
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        payload['files'][name] = '{"source":"third-party"}'
        payload['sha256'][name] = hashlib.sha256(
            payload['files'][name].encode('utf-8')).hexdigest()
        rewritten = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(rewritten)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(rewritten).hexdigest())

    def test_guest_rejects_legacy_routing_asset_even_with_valid_hashes(self) -> None:
        self._assert_unapproved_asset_rejected('metadata/agent-routes.json')

    def test_guest_rejects_imported_agent_asset_even_with_valid_hashes(self) -> None:
        self._assert_unapproved_asset_rejected('config/opencode/agents/legacy.md')

    def test_assets_tampering_rejected(self) -> None:
        path, sha = self._assets()
        path.write_bytes(path.read_bytes().replace(b'tokyonight', b'othername'))
        with self.assertRaisesRegex(ValueError, 'asset SHA mismatch'):
            guest.verify_assets(path, sha)

    def test_assets_extra_path_rejected(self) -> None:
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        data['files']['../../secret'] = 'forbidden'
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_assets_symlink_rejected(self) -> None:
        path, sha = self._assets()
        real = path.parent / 'real.json'
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            guest.verify_assets(path, sha)

    def test_existing_runtime_asset_tampering_rejected(self) -> None:
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        (target / 'config/opencode/AGENTS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'runtime asset mismatch'):
            guest.prepare(self.bundle, cfg_sha, data, sha)

    def test_receipt_tampering_stops(self) -> None:
        digest = guest.verify(self.bundle)
        out = guest.prepare(self.bundle, digest)
        (out / 'receipt.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            guest.prepare(self.bundle, digest)



class AssetExporterTest(unittest.TestCase):
    def setUp(self) -> None:
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
            else:
                file.write_text('# Reviewed content\n', encoding='utf-8')

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_export_selected_assets_with_v1_command_fields_removed(self) -> None:
        raw, digest = assets.build(self.root)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        payload = json.loads(raw)
        self.assertEqual(set(payload['files']),
                         set(assets.SOURCE_TO_TARGET.values()) |
                         {assets.THEME_TARGET})
        self.assertNotIn('metadata/agent-routes.json', payload['files'])
        command = payload['files']['config/opencode/commands/build-skill.md']
        self.assertNotIn('agent: old-agent', command)
        self.assertNotIn('model: unavailable/', command)
        self.assertIn('description: Safe skill command', command)
        self.assertNotIn('DO_NOT_IMPORT', raw.decode('utf-8'))
        self.assertEqual(json.loads(payload['files']['theme.json']), {'name':'tokyonight'})

    def test_symlinked_source_rejected(self) -> None:
        target = self.root / 'global-rules/AGENTS.global.md'
        target.unlink()
        target.symlink_to(self.root / 'opencode/tui.jsonc')
        with self.assertRaisesRegex(assets.AssetError, 'linked'):
            assets.build(self.root)

    def test_unapproved_theme_rejected(self) -> None:
        (self.root / assets.THEME_SOURCE).write_text('{"theme":"../../bad"}')
        with self.assertRaisesRegex(assets.AssetError, 'unapproved TUI theme'):
            assets.build(self.root)



class NativeV2IndependenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AssetExporterTest()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_no_legacy_routing_source_required(self) -> None:
        self.assertFalse((self.root / 'opencode/omo.jsonc').exists())
        raw, digest = assets.build(self.root)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_legacy_source_ignored_even_if_malformed(self) -> None:
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('this is not valid json')
        self.assertEqual(before, assets.build(self.root))

    def test_legacy_source_symlink_ignored(self) -> None:
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to('/etc/passwd')
        self.assertEqual(before, assets.build(self.root))

    def test_unapproved_agent_directory_ignored(self) -> None:
        before = assets.build(self.root)
        agent = self.root / 'opencode/agents/old.md'
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text('model: unknown/unapproved\n')
        self.assertEqual(before, assets.build(self.root))

    def test_exported_manifest_has_no_agent_routes(self) -> None:
        raw, _ = assets.build(self.root)
        payload = json.loads(raw)
        self.assertFalse(any(p.startswith('metadata/') or
                             '/agents/' in p for p in payload['files']))


if __name__ == '__main__':
    unittest.main()
