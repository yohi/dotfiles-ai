from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oc2_workspace  # noqa: E402


class WorkspaceSnapshotExclusionTests(unittest.TestCase):
    def test_r1_manifest_created_before_basedpyright_exclusion_remains_decodable(self):
        profile = oc2_workspace.profile_by_id('dotfiles-ai/workspace-safe-transfer/r1')
        self.assertIsNotNone(profile)
        content = b'legacy cache'
        manifest = {
            'schema': 'dotfiles-ai/oc2-workspace/v1',
            'profile': 'dotfiles-ai/workspace-safe-transfer/r1',
            'files': [{
                'path': '.basedpyright/cache.bin',
                'size': len(content),
                'sha256': hashlib.sha256(content).hexdigest(),
            }],
        }

        with tempfile.TemporaryDirectory() as temporary:
            decoded = oc2_workspace.decode_manifest(
                json.dumps(manifest).encode(), pathlib.Path(temporary),
            )

        self.assertEqual([entry.path for entry in decoded.files], ['.basedpyright/cache.bin'])

    def test_snapshot_excludes_local_justice_state(self):
        profile = oc2_workspace.profile_by_id('dotfiles-ai/workspace-safe-transfer/r2')
        self.assertIsNotNone(profile)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            state = root / '.justice/state.json'
            state.parent.mkdir(parents=True)
            state.write_text('{"status":"active"}\n')
            event = root / '.justice/events/unknown/session.jsonl'
            event.parent.mkdir(parents=True)
            event.write_text('{"event":"turn"}\n')

            manifest = oc2_workspace.snapshot(root, profile=profile)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])

    def test_snapshot_excludes_local_tool_caches_from_r2(self):
        profile = oc2_workspace.profile_by_id('dotfiles-ai/workspace-safe-transfer/r2')
        self.assertIsNotNone(profile)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            for directory in ('.ruff_cache', '.mypy_cache', '.pytest_cache', '.basedpyright'):
                cache_file = root / directory / 'cache.bin'
                cache_file.parent.mkdir(parents=True)
                cache_file.write_bytes(b'local tool cache')

            manifest = oc2_workspace.snapshot(root, profile=profile)

            self.assertEqual([entry.path for entry in manifest.files], ['main.py'])
