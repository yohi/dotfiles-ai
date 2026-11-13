from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import oc2_guest  # noqa: E402
import oc2_identity  # noqa: E402


AKANE_SHA512 = (
    '3c42e0df8bcc595db9139ae34552cfc184521fb948d4fdb80561d44760159bad'
    'ace7057a54999857de70e14ac078be063f4fca350681b6922ee74519590fb82b'
)
SIBYL_SHA512 = (
    '4ba5594a52cd30bba6fc010b573ede46431a4819b31bfa03f3d7aeb915d7471f'
    '3a8c1b339bff541e7e3d5bb0df10b67715dce1fe16c6263fa4ef7c039f311eec'
)


def asset_bundle() -> bytes:
    raw_files = {
        'plugins/akane/package.json': json.dumps({
            'name': '@yohi/akane',
            'version': '3.0.1',
            'type': 'module',
            'main': './dist/index.js',
            'exports': {'.': './dist/index.js', './server': './dist/index.js'},
        }, sort_keys=True).encode(),
        'plugins/akane/dist/index.js': b'import { Plugin } from "@opencode/plugin";',
        'plugins/sibyl/package.json': json.dumps({
            'name': '@yohi/sibyl',
            'version': '3.0.1',
            'type': 'module',
            'main': './dist/tui.js',
            'exports': {
                '.': {'import': './dist/tui.js'},
                './tui': {'import': './dist/tui.js'},
            },
        }, sort_keys=True).encode(),
        'plugins/sibyl/dist/tui.js': b'import { Plugin } from "@opencode/plugin/tui";',
    }
    plugins = [
        {
            'id': 'akane', 'package': '@yohi/akane', 'version': '3.0.1',
            'repository': 'yohi/akane', 'commit': 'b30772082e92cf148d5d8714266f326bad27f86a',
            'acquisition': 'github-package', 'artifact_sha512': AKANE_SHA512,
            'entrypoint': 'dist/index.js', 'files': ['package.json', 'dist/index.js'],
        },
        {
            'id': 'sibyl', 'package': '@yohi/sibyl', 'version': '3.0.1',
            'repository': 'yohi/sibyl', 'commit': 'e0249482701159bcd5a556fe06faae11dd41f66e',
            'acquisition': 'source-build', 'artifact_sha512': SIBYL_SHA512,
            'entrypoint': 'dist/tui.js', 'files': ['package.json', 'dist/tui.js'],
            'build_tool': 'bun@1.4.2',
            'lock_sha256': '71c0d8e7cd1267e0973066d01045a47e266907733d043d79f6ad899043f6e8b7',
        },
    ]
    payload = {
        'schema': 'dotfiles-ai/oc2-phase4-plugin-assets/v1',
        'source_sha256': 'a' * 64,
        'selection': ['akane', 'sibyl'],
        'plugins': plugins,
        'files': {name: base64.b64encode(data).decode('ascii') for name, data in raw_files.items()},
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in raw_files.items()},
    }
    return (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()


class Phase4GuestAssetTest(unittest.TestCase):
    def test_unified_runtime_identity_includes_config_assets_plugins_and_generator(self):
        values = ('1' * 64, '2' * 64, '3' * 64, '4' * 64)
        expected = hashlib.sha256(
            b'dotfiles-ai/oc2-unified-runtime/v1\0'
            + b''.join(bytes.fromhex(value) for value in values)
        ).hexdigest()

        actual = oc2_identity.unified_runtime_identity_sha256(
            oc2_identity.Phase4RuntimeIdentity(*values),
        )

        self.assertEqual(actual, expected)

    def test_phase4_runtime_identity_includes_plugin_bundle_and_own_namespace(self):
        manifest_sha = '1' * 64
        asset_sha = '2' * 64
        plugin_sha = '3' * 64
        generator_sha = '4' * 64
        expected = hashlib.sha256(
            b'dotfiles-ai/oc2-phase4-runtime/v1\0'
            + bytes.fromhex(manifest_sha)
            + bytes.fromhex(asset_sha)
            + bytes.fromhex(plugin_sha)
            + bytes.fromhex(generator_sha)
        ).hexdigest()

        actual = oc2_identity.phase4_runtime_identity_sha256(
            oc2_identity.Phase4RuntimeIdentity(
                manifest_sha, asset_sha, plugin_sha, generator_sha,
            ),
        )

        self.assertEqual(actual, expected)

    def test_guest_accepts_verified_server_and_tui_plugin_assets(self):
        raw = asset_bundle()
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / 'phase4-plugins.json'
            source.write_bytes(raw)
            with patch.object(oc2_guest, 'BASE', pathlib.Path(temporary)):
                verified = oc2_guest.verify_phase4_plugin_assets(
                    source, hashlib.sha256(raw).hexdigest(), 'a' * 64,
                )

        self.assertEqual(verified.selection, ('akane', 'sibyl'))
        self.assertEqual(len(verified.files), 4)
        self.assertEqual(verified.plugins[0].entrypoint, 'dist/index.js')
        self.assertEqual(verified.plugins[1].entrypoint, 'dist/tui.js')

    def test_guest_rejects_plugin_asset_outer_digest_mismatch(self):
        raw = asset_bundle()
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / 'phase4-plugins.json'
            source.write_bytes(raw)
            with patch.object(oc2_guest, 'BASE', pathlib.Path(temporary)):
                with self.assertRaisesRegex(ValueError, 'Phase 4 plugin asset SHA-256 mismatch'):
                    oc2_guest.verify_phase4_plugin_assets(source, 'b' * 64, 'a' * 64)

    def test_guest_rejects_plugin_file_hash_mismatch_after_outer_rehash(self):
        payload = json.loads(asset_bundle())
        payload['files']['plugins/akane/dist/index.js'] = base64.b64encode(
            b'import { spawn } from "node:child_process";',
        ).decode('ascii')
        raw = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / 'phase4-plugins.json'
            source.write_bytes(raw)
            with patch.object(oc2_guest, 'BASE', pathlib.Path(temporary)):
                with self.assertRaisesRegex(ValueError, 'plugin asset content SHA-256 mismatch'):
                    oc2_guest.verify_phase4_plugin_assets(
                        source, hashlib.sha256(raw).hexdigest(), 'a' * 64,
                    )

    def test_guest_rejects_invalid_phase4_plugin_path(self):
        payload = json.loads(asset_bundle())
        encoded = payload['files'].pop('plugins/sibyl/dist/tui.js')
        payload['files']['plugins/sibyl/../outside.js'] = encoded
        payload['sha256'].pop('plugins/sibyl/dist/tui.js')
        payload['sha256']['plugins/sibyl/../outside.js'] = hashlib.sha256(
            base64.b64decode(encoded),
        ).hexdigest()
        raw = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / 'phase4-plugins.json'
            source.write_bytes(raw)
            with patch.object(oc2_guest, 'BASE', pathlib.Path(temporary)):
                with self.assertRaisesRegex(ValueError, 'Phase 4 plugin asset path allowlist mismatch'):
                    oc2_guest.verify_phase4_plugin_assets(
                        source, hashlib.sha256(raw).hexdigest(), 'a' * 64,
                    )


if __name__ == '__main__':
    unittest.main()
