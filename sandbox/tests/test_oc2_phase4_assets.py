from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest
from collections.abc import Mapping
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import oc2_assets  # noqa: E402
import oc2_phase4_assets  # noqa: E402
from oc2_phase4_selection import ArtifactAcquisition, Phase4ArtifactPin, Phase4Plugin  # noqa: E402


AKANE_PACKAGE = {
    'name': '@yohi/akane',
    'version': '3.0.1',
    'type': 'module',
    'main': './dist/index.js',
    'exports': {'.': './dist/index.js', './server': './dist/index.js'},
    'dependencies': {'@opencode/plugin': '2.1.4'},
    'peerDependencies': {'effect': '^4.0.1'},
}
SIBYL_PACKAGE = {
    'name': '@yohi/sibyl',
    'version': '3.0.1',
    'type': 'module',
    'exports': {
        '.': {'import': './dist/index.js'},
        './tui': {'import': './dist/tui.js'},
    },
    'dependencies': {'@babel/core': '^7.23.3'},
    'optionalDependencies': {'node-pty': '^1.1.0'},
    'peerDependencies': {
        '@opencode/plugin': '>=2.1.4 <3',
        '@opentui/core': '>=0.6.8 <1',
        '@opentui/keymap': '>=0.6.8 <1',
        '@opentui/solid': '>=0.6.8 <1',
        'solid-js': '>=1.9.0 <2',
    },
}
PHASE4_IDENTITIES = {
    'akane': ('@yohi/akane', 'yohi/akane', 'b30772082e92cf148d5d8714266f326bad27f86a'),
    'sibyl': ('@yohi/sibyl', 'yohi/sibyl', 'e0249482701159bcd5a556fe06faae11dd41f66e'),
}


def package_archive(package: Mapping[str, object], entry: str, code: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, content in (
            ('package/package.json', json.dumps(package, sort_keys=True).encode()),
            (entry, code),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def symlink_archive(package: Mapping[str, object]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        package_bytes = json.dumps(package, sort_keys=True).encode()
        package_info = tarfile.TarInfo('package/package.json')
        package_info.size = len(package_bytes)
        archive.addfile(package_info, io.BytesIO(package_bytes))
        link = tarfile.TarInfo('package/dist/index.js')
        link.type = tarfile.SYMTYPE
        link.linkname = '../../outside.js'
        archive.addfile(link)
    return buffer.getvalue()


def archive_with_members(package: Mapping[str, object], entry: str, count: int) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, content in (
            ('package/package.json', json.dumps(package).encode()),
            (entry, b'export default {};'),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for index in range(count - 2):
            info = tarfile.TarInfo(f'package/extra-{index}.txt')
            info.size = 0
            archive.addfile(info, io.BytesIO())
    return buffer.getvalue()


def apm_document(akane_sha: str, sibyl_sha: str) -> bytes:
    akane_package, akane_repo, akane_commit = PHASE4_IDENTITIES['akane']
    sibyl_package, sibyl_repo, sibyl_commit = PHASE4_IDENTITIES['sibyl']
    return f'''name: fixture
version: 1
x-oc2-assets: [global-rules/AGENTS.global.md]
x-oc2-agents: {{}}
x-oc2-plugins:
  enabled: false
  allowlist: [superpowers]
x-oc2-mcp:
  enabled: false
  servers: []
x-oc2-phase4:
  enabled: true
  allowlist: [akane, sibyl]
  artifacts:
    akane:
      package: "{akane_package}"
      version: "3.0.1"
      repository: "{akane_repo}"
      commit: {akane_commit}
      acquisition: github-package
      sha512: {akane_sha}
    sibyl:
      package: "{sibyl_package}"
      version: "3.0.1"
      repository: "{sibyl_repo}"
      commit: {sibyl_commit}
      acquisition: source-build
      sha512: {sibyl_sha}
      build_tool: bun@1.4.2
      lock_sha256: 71c0d8e7cd1267e0973066d01045a47e266907733d043d79f6ad899043f6e8b7
'''.encode()


class Phase4ArtifactExportTest(unittest.TestCase):
    def test_phase4_export_rejects_literal_credentials_in_pinned_entrypoints(self):
        akane = package_archive(
            AKANE_PACKAGE, 'package/dist/index.js',
            b'-----BEGIN PRIVATE KEY-----\nfixture-only\n',
        )
        sibyl = package_archive(
            SIBYL_PACKAGE, 'package/dist/tui.js',
            b'import { Plugin } from "@opencode/plugin/tui"; export default Plugin;',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'apm.yml').write_bytes(
                apm_document(hashlib.sha512(akane).hexdigest(), hashlib.sha512(sibyl).hexdigest()),
            )
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(akane)
            sibyl_path.write_bytes(sibyl)

            with self.assertRaisesRegex(oc2_assets.AssetError, 'credential material'):
                oc2_assets.build_phase4_plugins(
                    root, (akane_path, sibyl_path), explicit_opt_in=True,
                )
    def test_archive_members_are_processed_without_bulk_materialization(self):
        raw = package_archive(AKANE_PACKAGE, 'package/dist/index.js', b'export default {};')
        pin = Phase4ArtifactPin(
            Phase4Plugin.AKANE, AKANE_PACKAGE['name'], AKANE_PACKAGE['version'],
            'yohi/akane', PHASE4_IDENTITIES['akane'][2],
            ArtifactAcquisition.GITHUB_PACKAGE, hashlib.sha512(raw).hexdigest(),
        )

        with patch.object(tarfile.TarFile, 'getmembers', side_effect=AssertionError):
            artifact = oc2_phase4_assets.verify_plugin_artifact(raw, Phase4Plugin.AKANE, pin)

        self.assertEqual({name for name, _ in artifact.files}, {'package.json', 'dist/index.js'})

    def test_archive_member_limit_is_enforced(self):
        raw = archive_with_members(AKANE_PACKAGE, 'package/dist/index.js',
                                   oc2_phase4_assets.MAX_ARTIFACT_FILES + 1)
        pin = Phase4ArtifactPin(
            Phase4Plugin.AKANE, AKANE_PACKAGE['name'], AKANE_PACKAGE['version'],
            'yohi/akane', PHASE4_IDENTITIES['akane'][2],
            ArtifactAcquisition.GITHUB_PACKAGE, hashlib.sha512(raw).hexdigest(),
        )

        with self.assertRaisesRegex(oc2_phase4_assets.Phase4AssetError, 'file count'):
            oc2_phase4_assets.verify_plugin_artifact(raw, Phase4Plugin.AKANE, pin)

    def test_empty_archive_is_rejected_as_missing_required_files(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz'):
            pass
        raw = buffer.getvalue()
        pin = Phase4ArtifactPin(
            Phase4Plugin.AKANE, AKANE_PACKAGE['name'], AKANE_PACKAGE['version'],
            'yohi/akane', PHASE4_IDENTITIES['akane'][2],
            ArtifactAcquisition.GITHUB_PACKAGE, hashlib.sha512(raw).hexdigest(),
        )

        with self.assertRaisesRegex(oc2_phase4_assets.Phase4AssetError, 'missing its package metadata'):
            oc2_phase4_assets.verify_plugin_artifact(raw, Phase4Plugin.AKANE, pin)

    def test_phase4_export_emits_only_pinned_runtime_entrypoints(self):
        akane = package_archive(
            AKANE_PACKAGE,
            'package/dist/index.js',
            b'import { Plugin } from "@opencode/plugin"; export default Plugin.define({});',
        )
        sibyl = package_archive(
            SIBYL_PACKAGE,
            'package/dist/tui.js',
            b'import { Plugin } from "@opencode/plugin/tui"; export default Plugin.define({});',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            apm = apm_document(hashlib.sha512(akane).hexdigest(), hashlib.sha512(sibyl).hexdigest())
            (root / 'apm.yml').write_bytes(apm)
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(akane)
            sibyl_path.write_bytes(sibyl)

            raw, asset_sha = oc2_assets.build_phase4_plugins(
                root, (akane_path, sibyl_path), explicit_opt_in=True,
            )

        payload = json.loads(raw)
        self.assertEqual(asset_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(payload['selection'], ['akane', 'sibyl'])
        self.assertEqual(
            set(payload['files']),
            {
                'plugins/akane/package.json',
                'plugins/akane/dist/index.js',
                'plugins/sibyl/package.json',
                'plugins/sibyl/dist/tui.js',
            },
        )
        self.assertEqual(
            base64.b64decode(payload['files']['plugins/sibyl/dist/tui.js']),
            b'import { Plugin } from "@opencode/plugin/tui"; export default Plugin.define({});',
        )
        for plugin in ('akane', 'sibyl'):
            package = json.loads(base64.b64decode(payload['files'][f'plugins/{plugin}/package.json']))
            self.assertFalse({'dependencies', 'optionalDependencies', 'peerDependencies'} & set(package))

    def test_phase4_export_rejects_artifact_digest_mismatch(self):
        akane = package_archive(
            AKANE_PACKAGE,
            'package/dist/index.js',
            b'import { Plugin } from "@opencode/plugin";',
        )
        sibyl = package_archive(
            SIBYL_PACKAGE,
            'package/dist/tui.js',
            b'import { Plugin } from "@opencode/plugin/tui";',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'apm.yml').write_bytes(
                apm_document(hashlib.sha512(akane).hexdigest(), hashlib.sha512(sibyl).hexdigest()),
            )
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(akane + b'tampered')
            sibyl_path.write_bytes(sibyl)

            with self.assertRaisesRegex(oc2_assets.AssetError, 'artifact SHA-512 mismatch'):
                oc2_assets.build_phase4_plugins(
                    root, (akane_path, sibyl_path), explicit_opt_in=True,
                )

    def test_phase4_export_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'apm.yml').write_bytes(apm_document('a' * 128, 'b' * 128))
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(b'')
            sibyl_path.write_bytes(b'')

            with self.assertRaisesRegex(oc2_assets.AssetError, 'explicit Phase 4 opt-in'):
                oc2_assets.build_phase4_plugins(
                    root, (akane_path, sibyl_path), explicit_opt_in=False,
                )

    def test_phase4_export_rejects_unapproved_runtime_dependency(self):
        akane = package_archive(
            AKANE_PACKAGE,
            'package/dist/index.js',
            b'import { spawn } from "node:child_process";',
        )
        sibyl = package_archive(
            SIBYL_PACKAGE,
            'package/dist/tui.js',
            b'import { Plugin } from "@opencode/plugin/tui";',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'apm.yml').write_bytes(
                apm_document(hashlib.sha512(akane).hexdigest(), hashlib.sha512(sibyl).hexdigest()),
            )
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(akane)
            sibyl_path.write_bytes(sibyl)

            with self.assertRaisesRegex(oc2_assets.AssetError, 'unapproved dependency'):
                oc2_assets.build_phase4_plugins(
                    root, (akane_path, sibyl_path), explicit_opt_in=True,
                )

    def test_phase4_export_rejects_symlinked_archive_entry(self):
        akane = symlink_archive(AKANE_PACKAGE)
        sibyl = package_archive(
            SIBYL_PACKAGE,
            'package/dist/tui.js',
            b'import { Plugin } from "@opencode/plugin/tui";',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'apm.yml').write_bytes(
                apm_document(hashlib.sha512(akane).hexdigest(), hashlib.sha512(sibyl).hexdigest()),
            )
            akane_path = root / 'akane.tgz'
            sibyl_path = root / 'sibyl.tgz'
            akane_path.write_bytes(akane)
            sibyl_path.write_bytes(sibyl)

            with self.assertRaisesRegex(oc2_assets.AssetError, 'non-regular or oversized'):
                oc2_assets.build_phase4_plugins(
                    root, (akane_path, sibyl_path), explicit_opt_in=True,
                )


if __name__ == '__main__':
    unittest.main()
