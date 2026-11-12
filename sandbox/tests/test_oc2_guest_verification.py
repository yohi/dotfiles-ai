from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
TESTS = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
import oc2_assets  # noqa: E402
import oc2_guest  # noqa: E402
import oc2_identity  # noqa: E402
import oc2_native  # noqa: E402
import prepare_opencode_v2  # noqa: E402
import test_oc2_phase4_guest as phase4_fixture  # noqa: E402


class VerificationGuestMaterializationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'guest'
        self.base.mkdir()
        self.base_patcher = patch.object(oc2_guest, 'BASE', self.base)
        self.base_patcher.start()
        self.addCleanup(self.base_patcher.stop)
        self.plugin_source = self.base / 'source-fixture'
        self.plugin_source.mkdir()
        files = {
            'index.js': b'export const plugin = true;\n',
            'package.json': (
                b'{"name":"superpowers","version":"6.4.2",'
                b'"main":".opencode/plugins/superpowers.js"}\n'
            ),
            '.opencode/plugins/superpowers.js': b'export const entrypoint = true;\n',
            'skills/using-superpowers/SKILL.md': b'---\nname: using-superpowers\n---\n',
            'skills/brainstorming/SKILL.md': b'---\nname: brainstorming\n---\n',
            'skills/verification-before-completion/SKILL.md':
                b'---\nname: verification-before-completion\n---\n',
        }
        for index in range(229 - len(files)):
            files[f'support/file-{index:03}.js'] = b'fixture\n'
        for relative, content in files.items():
            path = self.plugin_source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.plugin_source_files = files
        self.plugin_bytes = sum(len(content) for content in files.values())
        file_hashes = {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in files.items()
        }
        tree_content = ''.join(
            f'{relative}\0{file_hashes[relative]}\n'
            for relative in sorted(file_hashes)
        ).encode('utf-8')
        self.plugin_tree_sha = hashlib.sha256(tree_content).hexdigest()
        source = self.base / 'verification-superpowers' / self.plugin_tree_sha
        source.parent.mkdir()
        self.plugin_source.rename(source)
        self.plugin_source = source
        for module in (oc2_assets, oc2_guest):
            for name, value in (
                ('SUPERPOWERS_FILE_COUNT', len(files)),
                ('SUPERPOWERS_TOTAL_BYTES', self.plugin_bytes),
                ('SUPERPOWERS_TREE_SHA256', self.plugin_tree_sha),
                ('SUPERPOWERS_TREE_PATH', f'verification-superpowers/{self.plugin_tree_sha}'),
            ):
                patcher = patch.object(module, name, value, create=True)
                patcher.start()
                self.addCleanup(patcher.stop)

    def _selected_asset_files(self) -> dict[str, bytes]:
        return {
            'config/opencode/rules/custom.md': b'rule\n',
            'config/opencode/commands/custom.md': b'command\n',
            'config/opencode/skills/demo/SKILL.md': b'skill\n',
            'config/opencode/agents/custom.md': b'agent\n',
            'metadata/agent-routes.json': b'{}\n',
            'theme.json': b'{"name":"tokyonight"}\n',
        }

    def test_install_assets_output_counts_selected_file_keys(self) -> None:
        """Report installed asset counts from the verified files mapping."""
        files = self._selected_asset_files()
        output = io.StringIO()
        with patch.object(oc2_guest, 'verify_assets', return_value=files.copy()):
            with redirect_stdout(output):
                status = oc2_guest.main([
                    '--assets', str(self.base / 'assets.json'),
                    '--expected-assets-sha', 'b' * 64,
                    '--install-assets-runtime', 'a' * 64,
                ])

        self.assertEqual(status, 0)
        self.assertIn(
            'OC2_ASSETS_VERIFIED: rules=1 commands=1 skills=1 theme=1 custom_agents=1 routing=1',
            output.getvalue(),
        )

    def test_verification_output_counts_selected_file_keys(self) -> None:
        """Report verification asset counts from the same selected file categories."""
        output = io.StringIO()
        with (
            patch.object(oc2_guest, 'validate_location'),
            patch.object(oc2_guest, 'verify', return_value='a' * 64),
            patch.object(oc2_guest, 'verify_assets', return_value=self._selected_asset_files()),
            patch.object(oc2_guest, 'prepare', return_value=self.base / 'runtime'),
            redirect_stdout(output),
        ):
            status = oc2_guest.main([
                '--bundle', str(self.base / 'bundle'), '--expected-sha', 'a' * 64,
                '--assets', str(self.base / 'assets.json'), '--expected-assets-sha', 'b' * 64,
            ])

        self.assertEqual(status, 0)
        self.assertIn(
            'OC2_ASSETS_VERIFIED: rules=1 commands=1 skills=1 theme=1 custom_agents=1 routing=1',
            output.getvalue(),
        )

    def _provider_bundle(self, verification_only: bool) -> Path:
        apm = prepare_opencode_v2._read_apm_source(
            REPO, verification_only=verification_only,
        )
        generated = prepare_opencode_v2._build_files(
            apm.shell, apm.snapshot, apm.source_sha256, apm.v2_config,
            verification_only=verification_only,
        )
        bundle = self.root / ('verification' if verification_only else 'normal')
        bundle.mkdir()
        for name, contents in generated.items():
            (bundle / name).write_bytes(contents)
        return bundle

    def _asset_file(self, verification_only: bool) -> tuple[Path, str]:
        if verification_only:
            plugin_paths = {
                'index.js',
                'package.json',
                '.opencode/plugins/superpowers.js',
                *(
                    name for name in self.plugin_source_files
                    if name.startswith('skills/') and name.endswith('/SKILL.md')
                ),
            }
            artifact = oc2_assets.PluginArtifact(
                source_commit=oc2_native.SUPERPOWERS_COMMIT,
                files=tuple(
                    oc2_assets.PluginFile(
                        path=relative,
                        content=self.plugin_source_files[relative],
                        sha256=hashlib.sha256(self.plugin_source_files[relative]).hexdigest(),
                    )
                    for relative in sorted(plugin_paths)
                ),
            )
            with patch.object(
                oc2_assets, 'resolve_superpowers_plugin', return_value=artifact,
            ):
                raw, digest = oc2_assets.build(
                    REPO,
                    verification_only=True,
                    plugin_dir=Path('/fixture/superpowers'),
                )
        else:
            raw, digest = oc2_assets.build(REPO, verification_only=False)
        path = self.base / ('verification-assets.json' if verification_only else 'normal-assets.json')
        path.write_bytes(raw)
        return path, digest

    def test_verification_registers_local_plugin_with_native_skills_and_mcp(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        config_sha = oc2_guest.verify(bundle)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)

        runtime = oc2_guest.prepare(bundle, config_sha, assets, assets_sha)

        server = json.loads((runtime / 'config/opencode/opencode.jsonc').read_text())
        expected_plugin = str(runtime / 'plugins/superpowers')
        expected_mcp = str(runtime / 'mcp/oc2_local_mcp.py')
        self.assertEqual(server['plugins'], [expected_plugin])
        self.assertEqual(server['mcp']['servers']['oc2-status'], {
            'type': 'local',
            'enabled': True,
            'command': ['python3', '-I', expected_mcp],
        })
        self.assertNotIn('model', server)
        self.assertNotIn('providers', server)
        self.assertEqual(server['policies'][0], {
            'action': 'provider.use', 'resource': '*', 'effect': 'deny',
        })
        self.assertEqual(server['policies'][1], {
            'action': 'integration.connect', 'resource': '*', 'effect': 'deny',
        })
        policies = {
            (rule['action'], rule['resource']): rule['effect']
            for rule in server['policies']
        }
        self.assertEqual(policies[('plugin.use', '*')], 'deny')
        self.assertEqual(policies[('plugin.use', expected_plugin)], 'allow')
        self.assertNotIn(('plugin.use', 'superpowers'), policies)
        self.assertEqual(policies[('mcp.use', '*')], 'deny')
        self.assertEqual(policies[('mcp.use', 'oc2-status')], 'allow')
        self.assertTrue((runtime / 'plugins/superpowers/index.js').is_file())
        self.assertTrue(
            (runtime / 'plugins/superpowers/skills/using-superpowers/SKILL.md').is_file(),
        )
        self.assertTrue((runtime / 'mcp/oc2_local_mcp.py').is_file())
        receipt = json.loads((runtime / 'receipt.json').read_text())
        self.assertEqual(
            receipt['generator_sha256'],
            oc2_identity.verification_generator_fingerprint(
                Path(oc2_guest.__file__),
                Path(oc2_guest.__file__).with_name('oc2_agent_native.py'),
                Path(oc2_guest.__file__).with_name('oc2_identity.py'),
            ),
        )

    def test_phase4_registers_server_and_tui_plugins_in_separate_configs(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        config_sha = oc2_guest.verify(bundle)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        phase4_payload = json.loads(phase4_fixture.asset_bundle())
        native = oc2_guest.validate_native_asset(assets[oc2_guest.NATIVE_ASSET_TARGET])
        phase4_payload['source_sha256'] = native['source_sha256']
        phase4_raw = (json.dumps(phase4_payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
        phase4_path = self.base / 'phase4-plugins.json'
        phase4_path.write_bytes(phase4_raw)
        phase4_plugins = oc2_guest.verify_phase4_plugin_assets(
            phase4_path,
            hashlib.sha256(phase4_raw).hexdigest(),
            native['source_sha256'],
        )
        shutil.rmtree(self.plugin_source)

        runtime = oc2_guest.prepare(
            bundle, config_sha, assets, assets_sha, phase4_plugins=phase4_plugins,
        )

        server = json.loads((runtime / 'config/opencode/opencode.jsonc').read_text())
        client = json.loads((runtime / 'config/opencode/cli.json').read_text())
        self.assertEqual(server['plugins'], [
            str(runtime / 'plugins/superpowers'),
            {'package': str(runtime / 'plugins/akane'), 'options': {
                'enabled': True,
                'stage1Ms': 2147483647,
                'stage2Ms': 2147483647,
                'maxPings': 1,
                'maxToolGateCycles': 1,
                'notifierType': 'tmux',
                'notifyWaiting': False,
                'agents': {'include': ['__oc2_phase4_fixture__']},
            }},
        ])
        self.assertEqual(client['plugins'], [{
            'package': str(runtime / 'plugins/sibyl'),
            'options': {'observer': {
                'enabled': True,
                'maxVisibleSubagents': 8,
                'showModel': False,
                'showProvider': False,
                'showLatestText': False,
                'showReasoningSummary': False,
            }},
        }])
        self.assertTrue((runtime / 'plugins/akane/dist/index.js').is_file())
        self.assertTrue((runtime / 'plugins/sibyl/dist/tui.js').is_file())
        self.assertEqual(server['mcp']['servers']['oc2-status']['enabled'], True)
        self.assertNotIn('model', server)
        self.assertEqual(
            runtime.name,
            oc2_identity.phase4_runtime_identity_sha256(oc2_identity.Phase4RuntimeIdentity(
                config_sha,
                assets_sha,
                phase4_plugins.bundle_sha256,
                oc2_identity.phase4_generator_fingerprint((
                    Path(oc2_guest.__file__),
                    Path(oc2_guest.__file__).with_name('oc2_agent_native.py'),
                    Path(oc2_guest.__file__).with_name('oc2_identity.py'),
                    Path(oc2_guest.__file__).with_name('oc2_phase4_policy.py'),
                )),
            ))[:16],
        )

    def test_verification_runtime_identity_tracks_generator_fingerprint(self):
        manifest_sha = 'a' * 64
        assets_sha = 'b' * 64
        original_generator = 'c' * 64
        revised_generator = 'd' * 64

        original = oc2_guest.runtime_path(
            manifest_sha, assets_sha, generator_fingerprint=original_generator,
        )
        repeated = oc2_guest.runtime_path(
            manifest_sha, assets_sha, generator_fingerprint=original_generator,
        )
        revised = oc2_guest.runtime_path(
            manifest_sha, assets_sha, generator_fingerprint=revised_generator,
        )
        normal = oc2_guest.runtime_path(manifest_sha, assets_sha)
        expected_normal = hashlib.sha256(
            bytes.fromhex(manifest_sha) + bytes.fromhex(assets_sha),
        ).hexdigest()[:16]

        self.assertEqual(original, repeated)
        self.assertNotEqual(original, revised)
        self.assertEqual(normal.name, expected_normal)

    def test_verification_generator_fingerprint_tracks_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guest_script = root / 'oc2_guest.py'
            native_helper = root / 'oc2_agent_native.py'
            identity_helper = root / 'oc2_identity.py'
            guest_script.write_bytes(b'guest one')
            native_helper.write_bytes(b'helper one')
            identity_helper.write_bytes(b'identity one')
            initial = oc2_identity.verification_generator_fingerprint(
                guest_script, native_helper, identity_helper,
            )
            repeated = oc2_identity.verification_generator_fingerprint(
                guest_script, native_helper, identity_helper,
            )
            guest_script.write_bytes(b'guest two')
            changed_guest = oc2_identity.verification_generator_fingerprint(
                guest_script, native_helper, identity_helper,
            )
            native_helper.write_bytes(b'helper two')
            changed_helper = oc2_identity.verification_generator_fingerprint(
                guest_script, native_helper, identity_helper,
            )
            identity_helper.write_bytes(b'identity two')
            changed_identity_helper = oc2_identity.verification_generator_fingerprint(
                guest_script, native_helper, identity_helper,
            )

        self.assertEqual(initial, repeated)
        self.assertNotEqual(initial, changed_guest)
        self.assertNotEqual(changed_guest, changed_helper)
        self.assertNotEqual(changed_helper, changed_identity_helper)

    def test_verification_refuses_to_reuse_existing_runtime_identity(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        config_sha = oc2_guest.verify(bundle)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        oc2_guest.prepare(bundle, config_sha, assets, assets_sha)

        with self.assertRaisesRegex(ValueError, 'identity already exists'):
            oc2_guest.prepare(bundle, config_sha, assets, assets_sha)

    def test_verification_rejects_plugin_source_tree_hash_mismatch(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        (self.plugin_source / 'index.js').write_text(
            'export const plugin = nope;\n', encoding='utf-8',
        )

        with self.assertRaisesRegex(ValueError, 'tree SHA-256'):
            oc2_guest.prepare(bundle, oc2_guest.verify(bundle), assets, assets_sha)

    def test_verification_rejects_missing_pinned_plugin_source(self) -> None:
        """Stop verification when the pinned source tree was not staged."""
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        shutil.rmtree(self.plugin_source)

        with self.assertRaisesRegex(ValueError, 'source directory is missing'):
            oc2_guest.prepare(bundle, oc2_guest.verify(bundle), assets, assets_sha)

    def test_verification_rejects_plugin_source_file_count_mismatch(self) -> None:
        """Stop verification when the staged tree omits a pinned file."""
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        (self.plugin_source / 'support' / 'file-000.js').unlink()

        with self.assertRaisesRegex(ValueError, 'file count mismatch'):
            oc2_guest.prepare(bundle, oc2_guest.verify(bundle), assets, assets_sha)

    def test_verification_rejects_plugin_source_symlink(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=True)
        assets = oc2_guest.verify_assets(assets_path, assets_sha)
        entrypoint = self.plugin_source / 'index.js'
        entrypoint.unlink()
        entrypoint.symlink_to(self.root / 'outside.js')
        (self.root / 'outside.js').write_text('outside\n', encoding='utf-8')

        with self.assertRaisesRegex(ValueError, 'symlink'):
            oc2_guest.prepare(bundle, oc2_guest.verify(bundle), assets, assets_sha)

    def test_normal_and_verification_modes_use_distinct_runtime_storage(self):
        normal_bundle = self._provider_bundle(verification_only=False)
        verification_bundle = self._provider_bundle(verification_only=True)
        normal_assets, normal_sha = self._asset_file(verification_only=False)
        verification_assets, verification_sha = self._asset_file(verification_only=True)
        normal = oc2_guest.prepare(
            normal_bundle,
            oc2_guest.verify(normal_bundle),
            oc2_guest.verify_assets(normal_assets, normal_sha),
            normal_sha,
        )
        verification = oc2_guest.prepare(
            verification_bundle,
            oc2_guest.verify(verification_bundle),
            oc2_guest.verify_assets(verification_assets, verification_sha),
            verification_sha,
        )

        self.assertNotEqual(normal, verification)
        normal_config = json.loads((normal / 'config/opencode/opencode.jsonc').read_text())
        self.assertEqual(normal_config.get('plugins', []), [])
        self.assertEqual(normal_config.get('mcp', {}), {})

    def test_verification_config_rejects_nonverification_asset_selection(self):
        bundle = self._provider_bundle(verification_only=True)
        assets_path, assets_sha = self._asset_file(verification_only=False)
        verified_assets = oc2_guest.verify_assets(assets_path, assets_sha)

        with self.assertRaisesRegex(ValueError, 'verification mode'):
            oc2_guest.prepare(bundle, oc2_guest.verify(bundle), verified_assets, assets_sha)


if __name__ == '__main__':
    unittest.main()
