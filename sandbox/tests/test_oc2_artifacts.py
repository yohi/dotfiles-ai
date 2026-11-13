from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from sandbox.scripts import oc2_artifacts  # noqa: E402


class ArtifactLocationTest(unittest.TestCase):
    def test_unified_artifacts_use_a_stable_private_cache_location(self):
        cache_home = pathlib.Path('/tmp/oc2-cache-fixture')

        paths = oc2_artifacts.artifact_paths(cache_home)

        self.assertEqual(paths.root, cache_home / 'dotfiles-ai/oc2/artifacts-v1')
        self.assertEqual(paths.superpowers, paths.root / 'superpowers')
        self.assertEqual(paths.akane, paths.root / 'akane.tgz')
        self.assertEqual(paths.sibyl, paths.root / 'sibyl.tgz')

    def test_unpinned_sources_fail_before_creating_the_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'apm.yml').write_text('name: fixture\n', encoding='utf-8')
            paths = oc2_artifacts.artifact_paths(root / 'cache')

            with self.assertRaisesRegex(oc2_artifacts.ArtifactError, 'source artifacts'):
                oc2_artifacts.provision_artifacts(oc2_artifacts.ProvisionInputs(
                    repo=repo,
                    superpowers=root / 'untrusted-superpowers',
                    akane=root / 'untrusted-akane.tgz',
                    sibyl=root / 'untrusted-sibyl.tgz',
                    cache_home=root / 'cache',
                ))

            self.assertFalse(paths.root.exists())

    def test_relative_xdg_cache_path_is_rejected(self):
        with patch.dict('os.environ', {'XDG_CACHE_HOME': 'relative-cache'}):
            with self.assertRaisesRegex(oc2_artifacts.ArtifactError, 'must be absolute'):
                oc2_artifacts.artifact_paths()

    def test_verified_artifacts_are_cached_once_and_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'apm.yml').write_text('name: fixture\n', encoding='utf-8')
            source = root / 'source'
            source.mkdir()
            akane = root / 'akane.tgz'
            sibyl = root / 'sibyl.tgz'
            akane.write_bytes(b'fixed-akane')
            sibyl.write_bytes(b'fixed-sibyl')
            inputs = oc2_artifacts.ProvisionInputs(
                repo, source, akane, sibyl, root / 'cache',
            )

            with (
                patch.object(oc2_artifacts, 'resolve_superpowers_plugin'),
                patch.object(oc2_artifacts, 'build_phase4_plugins'),
            ):
                paths = oc2_artifacts.provision_artifacts(inputs)
                akane.write_bytes(b'changed-source')
                reused = oc2_artifacts.provision_artifacts(inputs)

            self.assertEqual(paths, reused)
            self.assertEqual(paths.akane.read_bytes(), b'fixed-akane')
            self.assertEqual(paths.sibyl.read_bytes(), b'fixed-sibyl')
            self.assertEqual(paths.root.stat().st_mode & 0o777, 0o700)
