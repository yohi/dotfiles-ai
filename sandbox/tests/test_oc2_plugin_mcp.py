from __future__ import annotations

import sys
import hashlib
import json
import os
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from typing import Callable
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import oc2_native  # noqa: E402
import oc2_assets  # noqa: E402
import oc2  # noqa: E402


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
    def test_normal_selection_is_disabled_even_when_candidates_are_declared(self) -> None:
        """Keep declared Plugin/MCP candidates disabled for normal exports."""
        parsed = oc2_native.parse_apm_native(config())
        payload = oc2_native.build_native_payload(parsed)

        self.assertEqual(payload['plugins'], {'enabled': False, 'allowlist': []})
        self.assertEqual(payload['mcp'], {'enabled': False, 'servers': []})

    def test_verification_selection_uses_only_the_declared_fixed_candidates(self) -> None:
        """Enable only the declared fixed candidates for verification exports."""
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

    def test_unknown_plugin_candidate_is_rejected(self) -> None:
        """Reject Plugin candidates outside the fixed verification allowlist."""
        with self.assertRaisesRegex(ValueError, 'unapproved plugin'):
            oc2_native.parse_apm_native(config(
                plugins='  enabled: false\n  allowlist: [other]\n',
                mcp='  enabled: false\n  servers: []\n',
            ))


class SuperpowersPluginResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.committed_skill_blob: bytes | None = None
        self.plugin_dir = Path(self.temporary.name) / 'superpowers'
        (self.plugin_dir / '.opencode' / 'plugins').mkdir(parents=True)
        (self.plugin_dir / 'lib').mkdir(parents=True)
        (self.plugin_dir / 'skills' / 'demo').mkdir(parents=True)
        (self.plugin_dir / '.git').mkdir()
        (self.plugin_dir / 'index.js').write_text(
            'export { default } from "./.opencode/plugins/superpowers.js";\n',
            encoding='utf-8',
        )
        (self.plugin_dir / '.opencode' / 'plugins' / 'superpowers.js').write_text(
            "import path from 'path';\n"
            "import fs from 'fs';\n"
            "import { fileURLToPath } from 'url';\n"
            'import "../../lib/runtime.js";\n',
            encoding='utf-8',
        )
        (self.plugin_dir / 'lib' / 'runtime.js').write_text(
            'export const runtime = true;\n', encoding='utf-8',
        )
        (self.plugin_dir / 'skills' / 'demo' / 'SKILL.md').write_text(
            '---\nname: demo\n---\n', encoding='utf-8',
        )
        (self.plugin_dir / 'package.json').write_text(
            '{"name":"superpowers","version":"6.4.2",'
            '"main":".opencode/plugins/superpowers.js"}\n',
            encoding='utf-8',
        )

    def _git_tree_fakes(
        self,
        extra_files: dict[str, bytes] | None = None,
        modes: dict[str, bytes] | None = None,
    ) -> tuple[dict[str, bytes], str, Callable[..., str], Callable[..., bytes]]:
        """Build deterministic fake Git metadata and blobs for tree export tests."""
        files = {
            relative: path.read_bytes()
            for relative in (
                '.opencode/plugins/superpowers.js', 'index.js', 'lib/runtime.js',
                'package.json', 'skills/demo/SKILL.md',
            )
            if (path := self.plugin_dir / relative).is_file()
        }
        files.update(extra_files or {})
        entry_modes = modes or {}
        blob_ids = {
            relative: hashlib.sha1(
                b'blob ' + str(len(content)).encode() + b'\0' + content,
            ).hexdigest()
            for relative, content in files.items()
        }
        tree_sha = hashlib.sha256(''.join(
            f'{relative}\0{hashlib.sha256(content).hexdigest()}\n'
            for relative, content in sorted(files.items())
        ).encode()).hexdigest()

        def git_text(_directory: Path, *args: str) -> str:
            match tuple(args):
                case ('remote', 'get-url', 'origin'):
                    return 'https://github.com/obra/superpowers.git'
                case ('rev-parse', 'HEAD'):
                    return oc2_assets.SUPERPOWERS_COMMIT
                case ('status', '--porcelain', '--untracked-files=all'):
                    return ''
                case ('ls-tree', '-r', '--name-only', 'HEAD'):
                    return '\n'.join(sorted(files))
                case _:
                    self.fail('unexpected text Git command: ' + ' '.join(args))

        def git_bytes(_directory: Path, *args: str) -> bytes:
            match tuple(args):
                case ('show', specifier) if specifier.startswith('HEAD:'):
                    return files[specifier.removeprefix('HEAD:')]
                case ('ls-tree', '-rz', '--full-tree', 'HEAD'):
                    return b''.join(
                        entry_modes.get(name, b'100644') + b' blob '
                        + blob_ids[name].encode() + b'\t'
                        + name.encode() + b'\0'
                        for name in sorted(files)
                    )
                case ('cat-file', 'blob', blob_id):
                    relative = next(name for name, oid in blob_ids.items() if oid == blob_id)
                    return files[relative]
                case _:
                    self.fail('unexpected byte Git command: ' + ' '.join(args))

        return files, tree_sha, git_text, git_bytes

    def test_export_materializes_the_complete_pinned_git_tree(self) -> None:
        """Export every committed source blob and bind it to the pinned tree digest."""
        files, tree_sha, git_text, git_bytes = self._git_tree_fakes()
        destination = Path(self.temporary.name) / 'verified-source'
        previous_umask = os.umask(0o077)
        try:
            with (
                patch.object(oc2_assets, '_git_output', side_effect=git_text),
                patch.object(oc2_assets, '_git_output_bytes', side_effect=git_bytes),
                patch.object(oc2_assets, 'parse_superpowers_lock', return_value=oc2_assets.SUPERPOWERS_COMMIT),
                patch.object(oc2_assets, 'SUPERPOWERS_FILE_COUNT', len(files)),
                patch.object(oc2_assets, 'SUPERPOWERS_TOTAL_BYTES', sum(map(len, files.values()))),
                patch.object(oc2_assets, 'SUPERPOWERS_TREE_SHA256', tree_sha),
            ):
                oc2_assets.export_superpowers_tree(REPO, self.plugin_dir, destination)
        finally:
            os.umask(previous_umask)

        self.assertEqual(
            {path.relative_to(destination).as_posix(): path.read_bytes()
             for path in destination.rglob('*') if path.is_file()},
            files,
        )
        self.assertEqual(destination.stat().st_mode & 0o777, 0o755)
        self.assertTrue(all(path.stat().st_mode & 0o777 == 0o644
                            for path in destination.rglob('*') if path.is_file()))

    def test_export_rejects_non_regular_git_tree_entries(self) -> None:
        """Reject symlink-mode entries from the Host Git tree before materialization."""
        files, tree_sha, git_text, git_bytes = self._git_tree_fakes(
            {'unreviewed-link': b'target'}, {'unreviewed-link': b'120000'},
        )
        destination = Path(self.temporary.name) / 'unsafe-source'

        with (
            patch.object(oc2_assets, '_git_output', side_effect=git_text),
            patch.object(oc2_assets, '_git_output_bytes', side_effect=git_bytes),
            patch.object(oc2_assets, 'parse_superpowers_lock', return_value=oc2_assets.SUPERPOWERS_COMMIT),
            patch.object(oc2_assets, 'SUPERPOWERS_FILE_COUNT', len(files)),
            patch.object(oc2_assets, 'SUPERPOWERS_TOTAL_BYTES', sum(map(len, files.values()))),
            patch.object(oc2_assets, 'SUPERPOWERS_TREE_SHA256', tree_sha),
            self.assertRaisesRegex(oc2_assets.AssetError, 'non-regular entry'),
        ):
            oc2_assets.export_superpowers_tree(REPO, self.plugin_dir, destination)

        self.assertFalse(destination.exists())

    def test_export_rejects_control_characters_in_git_paths(self) -> None:
        """Reject control characters in Host Git paths before materialization."""
        files, tree_sha, git_text, git_bytes = self._git_tree_fakes(
            {'untrusted\npath': b'content'},
        )
        destination = Path(self.temporary.name) / 'unsafe-path-source'

        with (
            patch.object(oc2_assets, '_git_output', side_effect=git_text),
            patch.object(oc2_assets, '_git_output_bytes', side_effect=git_bytes),
            patch.object(oc2_assets, 'parse_superpowers_lock', return_value=oc2_assets.SUPERPOWERS_COMMIT),
            patch.object(oc2_assets, 'SUPERPOWERS_FILE_COUNT', len(files)),
            patch.object(oc2_assets, 'SUPERPOWERS_TOTAL_BYTES', sum(map(len, files.values()))),
            patch.object(oc2_assets, 'SUPERPOWERS_TREE_SHA256', tree_sha),
            self.assertRaisesRegex(oc2_assets.AssetError, 'tree path is unsafe'),
        ):
            oc2_assets.export_superpowers_tree(REPO, self.plugin_dir, destination)

        self.assertFalse(destination.exists())

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
                return (
                    '.opencode/plugins/superpowers.js\nindex.js\nlib/runtime.js\n'
                    'package.json\nskills/demo/SKILL.md'
                )
            case ('show', 'HEAD:index.js'):
                return (self.plugin_dir / 'index.js').read_text(encoding='utf-8')
            case ('show', 'HEAD:.opencode/plugins/superpowers.js'):
                return (self.plugin_dir / '.opencode' / 'plugins' / 'superpowers.js').read_text(
                    encoding='utf-8',
                )
            case ('show', 'HEAD:lib/runtime.js'):
                return (self.plugin_dir / 'lib' / 'runtime.js').read_text(encoding='utf-8')
            case ('show', 'HEAD:package.json'):
                return (self.plugin_dir / 'package.json').read_text(encoding='utf-8')
            case ('show', 'HEAD:skills/demo/SKILL.md'):
                return (self.plugin_dir / 'skills' / 'demo' / 'SKILL.md').read_text(
                    encoding='utf-8',
                )
            case _:
                self.fail('unexpected local git command: ' + ' '.join(command))

    def _git_output_bytes(self, _directory: Path, *args: str) -> bytes:
        if tuple(args) == ('show', 'HEAD:skills/demo/SKILL.md'):
            if self.committed_skill_blob is not None:
                return self.committed_skill_blob
        return self._git_output(_directory, *args).encode('utf-8')

    def test_selected_skill_blob_compares_crlf_and_non_utf8_bytes_exactly(self) -> None:
        """Compare a committed binary Skill blob to its local bytes without decoding."""
        skill = self.plugin_dir / 'skills' / 'demo' / 'SKILL.md'
        committed = b'---\r\nname: demo\r\n---\r\n\xff\n'
        self.committed_skill_blob = committed
        skill.write_bytes(committed)

        with (
            patch.object(oc2_assets, '_git_output', side_effect=self._git_output),
            patch.object(oc2_assets, '_git_output_bytes', side_effect=self._git_output_bytes),
        ):
            artifact = oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

        self.assertEqual(
            next(item.content for item in artifact.files if item.path == 'skills/demo/SKILL.md'),
            committed,
        )

    def test_selected_skill_blob_rejects_changed_binary_bytes(self) -> None:
        """Reject local binary Skill content that differs from the committed blob."""
        skill = self.plugin_dir / 'skills' / 'demo' / 'SKILL.md'
        self.committed_skill_blob = b'---\r\nname: demo\r\n---\r\n\xff\n'
        skill.write_bytes(b'---\r\nname: demo\r\n---\r\n\xfe\n')

        with (
            patch.object(oc2_assets, '_git_output', side_effect=self._git_output),
            patch.object(oc2_assets, '_git_output_bytes', side_effect=self._git_output_bytes),
            self.assertRaisesRegex(oc2_assets.AssetError, 'differs from pinned commit'),
        ):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

    def test_missing_local_plugin_is_not_available(self) -> None:
        with self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE'):
            oc2_assets.resolve_superpowers_plugin(REPO, None)

    def test_pinned_checkout_allows_node_builtins_and_exports_native_skills(self) -> None:
        with (
            patch.object(oc2_assets, '_git_output', side_effect=self._git_output),
            patch.object(oc2_assets, '_git_output_bytes', side_effect=self._git_output_bytes),
        ):
            artifact = oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

        self.assertEqual(
            tuple(item.path for item in artifact.files),
            (
                '.opencode/plugins/superpowers.js',
                'index.js',
                'lib/runtime.js',
                'package.json',
                'skills/demo/SKILL.md',
            ),
        )
        self.assertEqual(
            next(item.content for item in artifact.files if item.path == 'skills/demo/SKILL.md'),
            b'---\nname: demo\n---\n',
        )
        self.assertEqual(
            artifact.source_commit,
            '8ca22dba9a94f28898bbce59f2537ff4d87c747d',
        )

    def test_unapproved_node_builtin_is_rejected(self) -> None:
        entrypoint = self.plugin_dir / '.opencode' / 'plugins' / 'superpowers.js'
        entrypoint.write_text("import fs from 'node:fs';\n", encoding='utf-8')

        with (
            patch.object(oc2_assets, '_git_output', side_effect=self._git_output),
            self.assertRaisesRegex(oc2_assets.AssetError, 'unbundled dependency'),
        ):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

    def test_unbundled_external_dependency_is_rejected(self) -> None:
        entrypoint = self.plugin_dir / '.opencode' / 'plugins' / 'superpowers.js'
        entrypoint.write_text("import helper from 'unapproved-package';\n", encoding='utf-8')

        with (
            patch.object(oc2_assets, '_git_output', side_effect=self._git_output),
            self.assertRaisesRegex(oc2_assets.AssetError, 'unbundled dependency'),
        ):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

    def test_wrong_local_commit_is_not_available(self) -> None:
        def wrong_commit(_directory: Path, *args: str) -> str:
            if tuple(args) == ('rev-parse', 'HEAD'):
                return '0' * 40
            return self._git_output(_directory, *args)

        with (patch.object(oc2_assets, '_git_output', side_effect=wrong_commit),
              self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE')):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

    def test_dirty_local_checkout_is_not_available(self) -> None:
        def dirty_checkout(_directory: Path, *args: str) -> str:
            if tuple(args) == ('status', '--porcelain', '--untracked-files=all'):
                return ' M index.js'
            return self._git_output(_directory, *args)

        with (patch.object(oc2_assets, '_git_output', side_effect=dirty_checkout),
              self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE')):
            oc2_assets.resolve_superpowers_plugin(REPO, self.plugin_dir)

class NativeMcpCandidateTest(unittest.TestCase):
    def test_unknown_mcp_server_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unapproved MCP server'):
            oc2_native.parse_apm_native(config(
                mcp='  enabled: false\n  servers: [filesystem]\n',
            ))


class VerificationAssetBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin_dir = Path('/fixture/superpowers')
        source_files = {
            'index.js': b'export { default } from "./.opencode/plugins/superpowers.js";\n',
            '.opencode/plugins/superpowers.js': b'export default { id: "superpowers" };\n',
            'package.json': (
                b'{"name":"superpowers","version":"6.4.2",'
                b'"main":".opencode/plugins/superpowers.js"}\n'
            ),
            'skills/using-superpowers/SKILL.md': b'---\nname: using-superpowers\n---\n',
            'skills/brainstorming/SKILL.md': b'---\nname: brainstorming\n---\n',
            'skills/verification-before-completion/SKILL.md': (
                b'---\nname: verification-before-completion\n---\n'
            ),
        }
        self.artifact = oc2_assets.PluginArtifact(
            source_commit=oc2_assets.SUPERPOWERS_COMMIT,
            files=tuple(
                oc2_assets.PluginFile(
                    path=relative,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
                for relative, content in sorted(source_files.items())
            ),
        )

    def test_verification_bundle_uses_native_git_plugin_and_local_mcp(self) -> None:
        with patch.object(
            oc2_assets, 'resolve_superpowers_plugin', return_value=self.artifact,
        ):
            raw, bundle_sha = oc2_assets.build(
                REPO, verification_only=True, plugin_dir=self.plugin_dir,
            )
        manifest = json.loads(raw)
        files = manifest['files']
        native = json.loads(files[oc2_assets.NATIVE_TARGET])
        plugin_source = json.loads(files['metadata/superpowers-plugin.json'])

        self.assertEqual(bundle_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(
            {name for name in files if name.startswith('plugins/superpowers/')},
            {oc2_assets.PLUGIN_PREFIX + item.path for item in self.artifact.files},
        )
        self.assertEqual(plugin_source['source'], 'obra/superpowers')
        self.assertEqual(plugin_source['commit'], '8ca22dba9a94f28898bbce59f2537ff4d87c747d')
        self.assertEqual(plugin_source['source_path'], 'verification-superpowers')
        self.assertEqual(plugin_source['entrypoint'], '.opencode/plugins/superpowers.js')
        self.assertEqual(
            set(plugin_source['plugin_files']),
            {item.path for item in self.artifact.files},
        )
        self.assertEqual(
            files['plugins/superpowers/skills/using-superpowers/SKILL.md'],
            '---\nname: using-superpowers\n---\n',
        )
        self.assertEqual(plugin_source['file_count'], 229)
        self.assertEqual(
            plugin_source['tree_sha256'],
            '19ba95fe50e96fb94d8260972cb50595ed31ada3f993e370b381a1e7718c5036',
        )
        self.assertIn('mcp/oc2_local_mcp.py', files)
        self.assertEqual(native['plugins'], {'enabled': True, 'allowlist': ['superpowers']})
        self.assertEqual(native['mcp'], {'enabled': True, 'servers': ['oc2-status']})

    def test_verification_bundle_checks_the_local_plugin_checkout(self) -> None:
        plugin_dir = Path('/fixture/superpowers')
        with patch.object(
            oc2_assets, 'resolve_superpowers_plugin', return_value=self.artifact,
        ) as resolve:
            oc2_assets.build(
                REPO, verification_only=True, plugin_dir=plugin_dir,
            )

        resolve.assert_called_once_with(REPO, plugin_dir)

    def test_verification_bundle_rejects_wrong_lock_commit(self) -> None:
        with (patch.object(oc2_assets, 'parse_superpowers_lock', return_value='0' * 40),
              self.assertRaisesRegex(oc2_assets.AssetError, 'NOT_AVAILABLE')):
            oc2_assets.build(REPO, verification_only=True)


class VerificationHostModeTest(unittest.TestCase):
    def test_verification_mode_requires_prepare_only_before_host_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'apm.yml').write_text('shell: bash\n', encoding='utf-8')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('Sandbox access forbidden')):
                result = oc2.main([
                    '--repo-root', str(REPO),
                    '--workspace', str(root),
                    '--verification-only',
                ])

        self.assertEqual(result, 1)

    def test_verification_requires_a_local_plugin_checkout(self) -> None:
        with patch.object(oc2, 'prepare_verification_runtime') as prepare:
            result = oc2.main([
                '--repo-root', str(REPO),
                '--sandbox', 'oc2-p3-verify-test',
                '--verification-only',
                '--prepare-only',
            ])

        prepare.assert_not_called()
        self.assertEqual(result, 1)

    def test_verification_passes_the_local_plugin_checkout(self) -> None:
        plugin_dir = Path('/fixture/superpowers')
        with patch.object(oc2, 'prepare_verification_runtime') as prepare:
            try:
                result = oc2.main([
                    '--repo-root', str(REPO),
                    '--sandbox', 'oc2-p3-verify-test',
                    '--verification-only',
                    '--prepare-only',
                    '--plugin-dir', str(plugin_dir),
                ])
            except SystemExit as error:
                result = error.code

        self.assertEqual(result, 0)
        prepare.assert_called_once_with(REPO, 'oc2-p3-verify-test', plugin_dir)

    def test_verification_dry_run_does_not_contact_sandbox(self) -> None:
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
                    '--prepare-only',
                    '--dry-run',
                    '--plugin-dir', '/fixture/superpowers',
                ])

        self.assertEqual(result, 0)
        self.assertIn('verification-only', output.getvalue())
        self.assertIn('no Sandbox commands executed', output.getvalue())


class NativePluginDeclarationTest(unittest.TestCase):
    def test_apm_cannot_enable_plugin_or_mcp_by_default(self) -> None:
        with self.assertRaisesRegex(ValueError, 'must remain disabled'):
            oc2_native.parse_apm_native(config(
                plugins='  enabled: true\n  allowlist: [superpowers]\n',
                mcp='  enabled: false\n  servers: []\n',
            ))

    def test_duplicate_plugin_fields_are_rejected(self) -> None:
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
