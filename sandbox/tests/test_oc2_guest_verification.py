from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import oc2_agent_native
import oc2_assets
import oc2_guest
import prepare_opencode_v2


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
        plugin_content = b'export const superpowers = true;\n'
        self.artifact = oc2_assets.PluginArtifact(
            source_commit=oc2_agent_native.SUPERPOWERS_COMMIT,
            files=(oc2_assets.PluginFile(
                path='index.js',
                content=plugin_content,
                sha256=hashlib.sha256(plugin_content).hexdigest(),
            ),),
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
        with patch.object(oc2_assets, 'resolve_superpowers_plugin', return_value=self.artifact):
            raw, digest = oc2_assets.build(
                REPO,
                verification_only=verification_only,
                plugin_dir=Path('/fixture/superpowers') if verification_only else None,
            )
        path = self.base / ('verification-assets.json' if verification_only else 'normal-assets.json')
        path.write_bytes(raw)
        return path, digest

    def test_verification_materializes_only_fixed_local_plugin_and_mcp(self):
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
        policies = {
            (rule['action'], rule['resource']): rule['effect']
            for rule in server['policies']
        }
        self.assertEqual(policies[('plugin.use', '*')], 'deny')
        self.assertEqual(policies[('plugin.use', expected_plugin)], 'allow')
        self.assertEqual(policies[('mcp.use', '*')], 'deny')
        self.assertEqual(policies[('mcp.use', 'oc2-status')], 'allow')
        self.assertTrue((runtime / 'plugins/superpowers/index.js').is_file())
        self.assertTrue((runtime / 'mcp/oc2_local_mcp.py').is_file())

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
