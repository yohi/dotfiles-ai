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
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


oc2 = load('oc2')
guest = load('oc2_guest')
assets = load('oc2_assets')
route_module = load('oc2_agent_routes')


class FakeRunner:
    def __init__(self, rows=None, inspection=None):
        self.rows = rows or []
        self.inspection = (
            {'name': 'oc2-dev', 'runtime_mounts': []}
            if inspection is None else inspection
        )
        self.calls = []

    def sbx(self, *args, **kwargs):
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
    def test_missing_sandbox(self):
        runner = FakeRunner()
        self.assertFalse(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mountless_sandbox_reused(self):
        # sbx v0.49.2 omits mount-related fields from ls --format json.
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}])
        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))
        self.assertIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_mounted_workspace_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell', 'workspace': '/home/user/repo'}])
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
                                        'runtime_mounts': [{'source': '/home/user'}]})
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
                              'workspace': '/home/user/source'}])
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
                    self.assertEqual(oc2.main(['--repo-root', tmp, '--dry-run']), 0)
                self.assertIn('mountless sandbox', out.getvalue())

    def test_invalid_sandbox_name_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            self.assertEqual(oc2.main(['--repo-root', tmp, '--sandbox', '../bad', '--dry-run']), 1)

    def test_launch_uses_standalone_no_host_env(self):
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

    def test_stage_does_not_depend_on_bash_positional_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# harmless guest fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()

            class StagingRunner:
                def __init__(self):
                    self.calls = []

                def sbx(self, *args, **kwargs):
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

    def test_stage_selected_assets_with_bounded_paths(self):
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
                def __init__(self):
                    self.calls = []

                def sbx(self, *args, **kwargs):
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

            class Runner:
                def sbx(self, *args, **kwargs):
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return (('f' * 64 if '/assets/' in args[3] else script_sha)
                                + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, expected)

    def test_cli_version_probe_avoids_bash_positional_arguments(self):
        class VersionRunner:
            def __init__(self):
                self.calls = []

            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                assert args[:4] == ('exec', 'oc2-dev', 'bash', '-c')
                assert len(args) == 5
                assert '$1' not in args[4]
                return 'opencode v2.1.4\n'

        runner = VersionRunner()
        self.assertEqual(oc2.cli_path(runner, 'oc2-dev'), oc2.PINNED[0])
        self.assertEqual(len(runner.calls), 1)

    def test_launch_rejects_unapproved_binary(self):
        with self.assertRaisesRegex(oc2.Stop, 'unapproved'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'a' * 64, '/tmp/untrusted')

    def test_launch_rejects_invalid_digest(self):
        with self.assertRaisesRegex(oc2.Stop, 'invalid runtime digest'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'not-a-digest', oc2.PINNED[0])


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
        self.manifest = {'schema': 'dotfiles-ai/sandbox-export/v0', 'generator': 'v0.1',
                         'opencode_version': '2.1.4', 'plugins_exported': 0,
                         'mcp_entries_exported': 0, 'artifacts_sha256': hashes}
        (self.bundle / 'export-manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        guest.BASE = self.orig
        self.tmp.cleanup()

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
        native = {}
        for role, (mode, description) in route_module.ROLES.items():
            value = {'description': description, 'mode': mode}
            if role in route_module.READ_ONLY:
                value['permissions'] = [
                    {'action': 'edit', 'resource': '*', 'effect': 'deny'},
                    {'action': 'shell', 'resource': '*', 'effect': 'deny'},
                    {'action': 'subagent', 'resource': '*', 'effect': 'deny'},
                ]
            native[role] = value
        metadata = {
            'schema': route_module.SCHEMA,
            'routing_activation': 'disabled-no-provider-broker',
            'default_agent': 'sisyphus',
            'native_agents': native,
            'routes': {'personal': {}, 'work': {}},
        }
        contents = {name: ('# selected text\n' if name != 'theme.json'
                           else '{"name":"tokyonight"}')
                    for name in names}
        contents['metadata/agent-routes.json'] = json.dumps(metadata, sort_keys=True)
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
        self.assertEqual(server['default_agent'], 'sisyphus')
        self.assertEqual(set(server['agents']), set(route_module.ROLES))
        self.assertNotIn('model', server['agents']['sisyphus'])
        self.assertTrue((target / 'metadata/agent-routes.json').is_file())
        tui = json.loads((target / 'config/opencode/cli.json').read_text())
        self.assertEqual(tui['theme'], {'name': 'tokyonight'})

    def test_guest_rejects_agent_model_pin_even_with_valid_hashes(self):
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        key = 'metadata/agent-routes.json'
        metadata = json.loads(data['files'][key])
        metadata['native_agents']['sisyphus']['model'] = 'openai/unapproved'
        data['files'][key] = json.dumps(metadata, sort_keys=True)
        data['sha256'][key] = hashlib.sha256(
            data['files'][key].encode('utf-8')
        ).hexdigest()
        rewritten = (json.dumps(data, sort_keys=True) + '\n').encode()
        path.write_bytes(rewritten)
        with self.assertRaisesRegex(ValueError, 'unsafe native agent config'):
            guest.verify_assets(path, hashlib.sha256(rewritten).hexdigest())

    def test_guest_rejects_review_agent_write_or_delegation(self):
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        key = 'metadata/agent-routes.json'
        metadata = json.loads(data['files'][key])
        metadata['native_agents']['oracle']['permissions'].pop()
        data['files'][key] = json.dumps(metadata, sort_keys=True)
        data['sha256'][key] = hashlib.sha256(
            data['files'][key].encode('utf-8')
        ).hexdigest()
        rewritten = (json.dumps(data, sort_keys=True) + '\n').encode()
        path.write_bytes(rewritten)
        with self.assertRaisesRegex(ValueError, 'must be read-only'):
            guest.verify_assets(path, hashlib.sha256(rewritten).hexdigest())

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
            else:
                file.write_text('# Reviewed content\n', encoding='utf-8')

        omo_file = self.root / route_module.SOURCE
        omo_file.parent.mkdir(parents=True, exist_ok=True)
        personal = {
            name: {'model': 'cloudflare-ai-gateway-custom/kimi-k2.7-code'}
            for name in route_module.ROLES
        }
        work = {
            name: {'model': 'amazon-bedrock/global.anthropic.claude-sonnet-5-5'}
            for name in route_module.ROLES
        }
        fixture = {
            '[opencode]': {
                'agents': personal,
                'categories': {'quick': {'model': 'openai/gpt-6-luna'}},
            },
            'profiles': {
                'personal': {},
                'work': {'[opencode]': {
                    'agents': work,
                    'categories': {'quick': {
                        'model': 'amazon-bedrock/global.anthropic.claude-haiku-4-5'
                    }},
                }},
            },
        }
        omo_file.write_text(json.dumps(fixture), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_export_selected_assets_with_v1_command_fields_removed(self):
        raw, digest = assets.build(self.root)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        payload = json.loads(raw)
        self.assertEqual(set(payload['files']),
                         set(assets.SOURCE_TO_TARGET.values()) |
                         {assets.THEME_TARGET, assets.AGENT_ROUTE_TARGET})
        self.assertEqual(json.loads(payload['files'][assets.AGENT_ROUTE_TARGET])
                         ['routing_activation'], 'disabled-no-provider-broker')
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

    def test_unapproved_theme_rejected(self):
        (self.root / assets.THEME_SOURCE).write_text('{"theme":"../../bad"}')
        with self.assertRaisesRegex(assets.AssetError, 'unapproved TUI theme'):
            assets.build(self.root)



class AgentRouteTest(unittest.TestCase):
    def setUp(self):
        self.fixture = AssetExporterTest()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self):
        self.fixture.tearDown()

    def test_routes_are_advisory_and_v2_agents_have_no_models(self):
        payload, digest = route_module.build(self.root)
        self.assertRegex(digest, '^[a-f0-9]{64}$')
        self.assertEqual(payload['routing_activation'], 'disabled-no-provider-broker')
        self.assertEqual(payload['default_agent'], 'sisyphus')
        self.assertEqual(len(payload['native_agents']), len(route_module.ROLES))
        self.assertTrue(all('model' not in item for item in
                            payload['native_agents'].values()))
        work = payload['routes']['work']['agents']
        self.assertTrue(all(row['primary']['model'].startswith('amazon-bedrock/')
                            for row in work.values()))

    def test_jsonc_preserves_quoted_comment_and_trailing_comma(self):
        data = route_module._jsonc(
            '{"url":"https://example.com//a,b", // comment\n'
            '"list":["one",],"text":"/*literal*/",}'
        )
        self.assertEqual(data['url'], 'https://example.com//a,b')
        self.assertEqual(data['list'], ['one'])
        self.assertEqual(data['text'], '/*literal*/')

    def test_work_provider_escape_rejected(self):
        path = self.root / route_module.SOURCE
        data = json.loads(path.read_text())
        data['profiles']['work']['[opencode]']['agents']['sisyphus']['model'] = \
            'cloudflare-ai-gateway-custom/kimi-k2.7-code'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(route_module.RouteError, 'Bedrock-only'):
            route_module.build(self.root)

    def test_work_ultrawork_provider_escape_rejected(self):
        path = self.root / route_module.SOURCE
        data = json.loads(path.read_text())
        data['profiles']['work']['[opencode]']['agents']['sisyphus']['ultrawork'] = {
            'model': 'cloudflare-ai-gateway-custom/kimi-k2.7-code'
        }
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(route_module.RouteError, 'Bedrock-only'):
            route_module.build(self.root)

    def test_missing_work_role_rejected(self):
        path = self.root / route_module.SOURCE
        data = json.loads(path.read_text())
        del data['profiles']['work']['[opencode]']['agents']['sisyphus']
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(route_module.RouteError, 'work agent routes incomplete'):
            route_module.build(self.root)

    def test_omo_source_symlink_rejected(self):
        path = self.root / route_module.SOURCE
        original = path.parent / 'original.jsonc'
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaisesRegex(route_module.RouteError, 'linked'):
            route_module.build(self.root)



if __name__ == '__main__':
    unittest.main()
