from __future__ import annotations

import sys
import hashlib
import json
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import oc2_native
import oc2_assets
import oc2


def config(*, plugins: str = '  enabled: false\n  allowlist: [superpowers]\n',
           mcp: str = '  enabled: false\n  servers: [oc2-status]\n') -> bytes:
    return (
        'name: fixture\n'
        'provider:\n'
        '  openai:\n'
        '    whitelist: [gpt-6-luna]\n'
        'opencode_v2:\n'
        '  providers:\n'
        '    openai:\n'
        '      enabled: true\n'
        'x-oc2-assets:\n'
        '  - global-rules/AGENTS.global.md\n'
        'x-oc2-agents: {}\n'
        'x-oc2-plugins:\n'
        + plugins
        + 'x-oc2-mcp:\n'
        + mcp
    ).encode('utf-8')


class NativePluginMcpSelectionTest(unittest.TestCase):
    def test_normal_selection_is_disabled_even_when_candidates_are_declared(self):
        parsed = oc2_native.parse_apm_native(config())
        payload = oc2_native.build_native_payload(parsed)

        self.assertEqual(payload['plugins'], {'enabled': False, 'allowlist': []})
        self.assertEqual(payload['mcp'], {'enabled': False, 'servers': []})

    def test_verification_selection_uses_only_the_declared_fixed_candidates(self):
        parsed = oc2_native.parse_apm_native(config(), verification_only=True)
        payload = oc2_native.build_native_payload(parsed)

        self.assertEqual(payload['plugins'], {
            'enabled': True,
            'allowlist': ['superpowers'],
        })
        self.assertEqual(payload['mcp'], {
            'enabled': True,
            'servers': ['oc2-status'],
        })

    def test_unknown_plugin_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unapproved plugin'):
            oc2_native.parse_apm_native(config(
                plugins='  enabled: false\n  allowlist: [other]\n',
                mcp='  enabled: false\n  servers: []\n',
            ))


class SuperpowersPluginResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.plugin_dir = Path(self.temporary.name) / 'superpowers'
        (self.plugin_dir / 'lib').mkdir(parents=True)
        (self.plugin_dir / '.git').mkdir()
        (self.plugin_dir / 'index.js').write_text(
            'import "./lib/runtime.js";\n', encoding='utf-8',
        )
        (self.plugin_dir / 'lib' / 'runtime.js').write_text(
            'export const runtime = true;\n', encoding='utf-8',
        )
        (self.plugin_dir / 'package.json').write_text(
            '{"name":"superpowers","version":"6.4.2"}\n', encoding='utf-8',
        )

    def _git_output(self, _directory: Path, *args: str) -> str:
        command = tuple(args)
        match command:
            case ('remote', 'get-url', 'origin'):
                return 'https://github.com/obra/superpowers.git'
            case ('rev-parse', 'HEAD'):
                return '8ca22dba9a94f28898bbce59f2537ff4d87c747d'
            case ('status', '--porcelain', '--untracked-files=all'):
                return ''
            case ('ls-tree', '-r', '--name-only', 'HEAD'):
                return 'index.js\nlib/runtime.js\npackage.json'
            case ('show', 'HEAD:index.js'):
                return (self.plugin_dir / 'index.js').read_text(encoding='utf-8')
            case ('show', 'HEAD:lib/runtime.js'):
                return (self.plugin_dir / 'lib' / 'runtime.js').read_text(encoding='utf-8')
            case ('show', 'HEAD:package.json'):
                return (self.plugin_dir / 'package.json').read_text(encoding='utf-8')
            case _:
                self.fail('unexpected local git command: ' + ' '.join(command))

    def test_missing_local_plugin_is_not_available(self):
        with self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE'):
            oc2_assets.resolve_superpowers_plugin(REPO, None)

    def test_pinned_local_checkout_exports_root_and_relative_dependency(self):
        with patch.object(oc2_assets, '_git_output', side_effect=self._git_output):
            artifact = oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

        self.assertEqual(
            tuple(item.path for item in artifact.files),
            ('index.js', 'lib/runtime.js', 'package.json'),
        )
        self.assertEqual(
            artifact.source_commit,
            '8ca22dba9a94f28898bbce59f2537ff4d87c747d',
        )

    def test_wrong_local_commit_is_not_available(self):
        def wrong_commit(_directory: Path, *args: str) -> str:
            if tuple(args) == ('rev-parse', 'HEAD'):
                return '0' * 40
            return self._git_output(_directory, *args)

        with (patch.object(oc2_assets, '_git_output', side_effect=wrong_commit),
              self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE')):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

    def test_dirty_local_checkout_is_not_available(self):
        def dirty_checkout(_directory: Path, *args: str) -> str:
            if tuple(args) == ('status', '--porcelain', '--untracked-files=all'):
                return ' M index.js'
            return self._git_output(_directory, *args)

        with (patch.object(oc2_assets, '_git_output', side_effect=dirty_checkout),
              self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE')):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

class NativeMcpCandidateTest(unittest.TestCase):
    def test_unknown_mcp_server_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unapproved MCP server'):
            oc2_native.parse_apm_native(config(
                mcp='  enabled: false\n  servers: [filesystem]\n',
            ))


class VerificationAssetBundleTest(unittest.TestCase):
    def test_verification_bundle_hashes_only_selected_plugin_and_local_mcp(self):
        plugin_content = b'export const plugin = true;\n'
        artifact = oc2_assets.PluginArtifact(
            source_commit='8ca22dba9a94f28898bbce59f2537ff4d87c747d',
            files=(oc2_assets.PluginFile(
                path='index.js',
                content=plugin_content,
                sha256=hashlib.sha256(plugin_content).hexdigest(),
            ),),
        )
        with patch.object(oc2_assets, 'resolve_superpowers_plugin', return_value=artifact):
            raw, bundle_sha = oc2_assets.build(
                REPO, verification_only=True, plugin_dir=Path('/fixture/superpowers'),
            )
        manifest = json.loads(raw)
        files = manifest['files']
        native = json.loads(files[oc2_assets.NATIVE_TARGET])

        self.assertEqual(bundle_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(files['plugins/superpowers/index.js'], plugin_content.decode())
        self.assertIn('mcp/oc2_local_mcp.py', files)
        self.assertEqual(native['plugins'], {'enabled': True, 'allowlist': ['superpowers']})
        self.assertEqual(native['mcp'], {'enabled': True, 'servers': ['oc2-status']})
        self.assertEqual(
            manifest['sha256']['plugins/superpowers/index.js'],
            hashlib.sha256(plugin_content).hexdigest(),
        )

    def test_verification_bundle_requires_explicit_local_plugin_path(self):
        with self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE'):
            oc2_assets.build(REPO, verification_only=True)


class VerificationHostModeTest(unittest.TestCase):
    def test_verification_mode_requires_prepare_only_before_host_operations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'apm.yml').write_text('shell: bash\n', encoding='utf-8')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('Sandbox access forbidden')):
                result = oc2.main([
                    '--repo-root', str(REPO),
                    '--workspace', str(root),
                    '--verification-only',
                    '--plugin-dir', str(root / 'superpowers'),
                ])

        self.assertEqual(result, 1)

    def test_verification_dry_run_does_not_contact_sandbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'apm.yml').write_text('shell: bash\n', encoding='utf-8')
            output = io.StringIO()
            with (patch.object(oc2, 'Runner', side_effect=AssertionError('Sandbox access forbidden')),
                  contextlib.redirect_stdout(output)):
                result = oc2.main([
                    '--repo-root', str(REPO),
                    '--workspace', str(root),
                    '--verification-only',
                    '--plugin-dir', str(root / 'superpowers'),
                    '--prepare-only',
                    '--dry-run',
                ])

        self.assertEqual(result, 0)
        self.assertIn('verification-only', output.getvalue())
        self.assertIn('no Sandbox commands executed', output.getvalue())


class NativePluginDeclarationTest(unittest.TestCase):
    def test_apm_cannot_enable_plugin_or_mcp_by_default(self):
        with self.assertRaisesRegex(ValueError, 'must remain disabled'):
            oc2_native.parse_apm_native(config(
                plugins='  enabled: true\n  allowlist: [superpowers]\n',
                mcp='  enabled: false\n  servers: []\n',
            ))

    def test_duplicate_plugin_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            oc2_native.parse_apm_native(config(
                plugins=(
                    '  enabled: false\n'
                    '  allowlist: [superpowers]\n'
                    '  allowlist: [other]\n'
                ),
                mcp='  enabled: false\n  servers: []\n',
            ))


if __name__ == '__main__':
    unittest.main()
