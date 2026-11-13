from __future__ import annotations

import json
import hashlib
import pathlib
import sys
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import oc2_native  # noqa: E402
import oc2_assets  # noqa: E402


PHASE4_BLOCK = b'''\nx-oc2-phase4:
  enabled: true
  allowlist: [akane, sibyl]
  artifacts:
    akane:
      package: "@yohi/akane"
      version: "3.0.1"
      repository: "yohi/akane"
      commit: b30772082e92cf148d5d8714266f326bad27f86a
      acquisition: github-package
      sha512: 3c42e0df8bcc595db9139ae34552cfc184521fb948d4fdb80561d44760159badace7057a54999857de70e14ac078be063f4fca350681b6922ee74519590fb82b
    sibyl:
      package: "@yohi/sibyl"
      version: "3.0.1"
      repository: "yohi/sibyl"
      commit: e0249482701159bcd5a556fe06faae11dd41f66e
      acquisition: source-build
      sha512: 4ba5594a52cd30bba6fc010b573ede46431a4819b31bfa03f3d7aeb915d7471f3a8c1b339bff541e7e3d5bb0df10b67715dce1fe16c6263fa4ef7c039f311eec
      build_tool: bun@1.4.2
      lock_sha256: 71c0d8e7cd1267e0973066d01045a47e266907733d043d79f6ad899043f6e8b7
'''


def _superpowers_artifact() -> oc2_assets.PluginArtifact:
    contents = {
        'index.js': b'export default {}\n',
        'package.json': b'{"name":"superpowers","version":"6.4.2"}\n',
        '.opencode/plugins/superpowers.js': b'export default {}\n',
        'skills/demo/SKILL.md': b'---\nname: demo\n---\n',
    }
    return oc2_assets.PluginArtifact(
        source_commit=oc2_native.SUPERPOWERS_COMMIT,
        files=tuple(
            oc2_assets.PluginFile(name, data, hashlib.sha256(data).hexdigest())
            for name, data in sorted(contents.items())
        ),
        tree_files=tuple(
            (name, hashlib.sha256(data).hexdigest())
            for name, data in sorted(contents.items())
        ),
    )


def phase4_config(block: bytes = PHASE4_BLOCK) -> bytes:
    source = (REPO / 'apm.yml').read_bytes()
    return source.replace(PHASE4_BLOCK, block, 1)


class Phase4PluginSelectionTest(unittest.TestCase):
    def test_default_asset_export_does_not_include_phase4_plugins(self):
        with patch.object(
            oc2_assets, 'resolve_superpowers_plugin', return_value=_superpowers_artifact(),
        ):
            raw, _digest = oc2_assets.build(REPO, plugin_dir=pathlib.Path('/fixture/superpowers'))

        payload = json.loads(raw)

        self.assertFalse(any(name.startswith('plugins/akane/') for name in payload['files']))
        self.assertFalse(any(name.startswith('plugins/sibyl/') for name in payload['files']))

    def test_unified_apm_selects_phase4_and_verification_mode_stays_separate(self):
        raw = phase4_config()

        config = oc2_native.parse_apm_native(raw)
        verification = oc2_native.parse_apm_native(raw, verification_only=True)
        payload = oc2_native.build_native_payload(config)

        self.assertTrue(config.unified_runtime)
        self.assertTrue(config.phase4_plugins.enabled)
        self.assertEqual(
            tuple(plugin.value for plugin in config.phase4_plugins.allowlist),
            ('akane', 'sibyl'),
        )
        self.assertEqual(payload['plugins'], {
            'enabled': True, 'allowlist': ['superpowers'],
        })
        self.assertFalse(verification.unified_runtime)
        self.assertFalse(verification.phase4_plugins.enabled)

    def test_explicit_phase4_opt_in_selects_server_before_tui_plugin(self):
        raw = phase4_config()

        config = oc2_native.parse_apm_native(raw, phase4_plugins=True)

        self.assertTrue(config.phase4_plugins.enabled)
        self.assertEqual(
            tuple(plugin.value for plugin in config.phase4_plugins.allowlist),
            ('akane', 'sibyl'),
        )
        artifacts = {artifact.plugin.value: artifact for artifact in config.phase4_plugins.artifacts}
        self.assertEqual(artifacts['akane'].source_commit, 'b30772082e92cf148d5d8714266f326bad27f86a')
        self.assertEqual(artifacts['sibyl'].source_commit, 'e0249482701159bcd5a556fe06faae11dd41f66e')
        self.assertEqual(
            artifacts['sibyl'].artifact_sha512,
            '4ba5594a52cd30bba6fc010b573ede46431a4819b31bfa03f3d7aeb915d7471f3a8c1b339bff541e7e3d5bb0df10b67715dce1fe16c6263fa4ef7c039f311eec',
        )

    def test_unknown_phase4_plugin_is_rejected_even_without_runtime_opt_in(self):
        raw = phase4_config(PHASE4_BLOCK.replace(b'sibyl', b'unknown'))

        with self.assertRaisesRegex(oc2_native.NativeConfigError, 'unapproved Phase 4 plugin'):
            oc2_native.parse_apm_native(raw)

    def test_phase4_plugin_order_is_fixed(self):
        raw = phase4_config(PHASE4_BLOCK.replace(
            b'[akane, sibyl]', b'[sibyl, akane]',
        ))

        with self.assertRaisesRegex(oc2_native.NativeConfigError, 'fixed Phase 4 plugin order'):
            oc2_native.parse_apm_native(raw, phase4_plugins=True)

    def test_explicit_opt_in_fails_when_apm_phase4_gate_is_disabled(self):
        raw = phase4_config(PHASE4_BLOCK.replace(b'enabled: true', b'enabled: false'))

        with self.assertRaisesRegex(oc2_native.NativeConfigError, 'Phase 4 is disabled in APM'):
            oc2_native.parse_apm_native(raw, phase4_plugins=True)

    def test_phase4_source_commit_must_match_the_fixed_identity(self):
        raw = phase4_config(PHASE4_BLOCK.replace(
            b'e0249482701159bcd5a556fe06faae11dd41f66e', b'a' * 40,
        ))

        with self.assertRaisesRegex(oc2_native.NativeConfigError, 'source identity is not allowlisted'):
            oc2_native.parse_apm_native(raw)

    def test_phase4_artifact_sha512_must_be_validated(self):
        raw = phase4_config(PHASE4_BLOCK.replace(
            b'3c42e0df8bcc595d', b'not-a-valid-sha!',
        ))

        with self.assertRaisesRegex(oc2_native.NativeConfigError, 'artifact SHA-512 is invalid'):
            oc2_native.parse_apm_native(raw)


if __name__ == '__main__':
    unittest.main()
