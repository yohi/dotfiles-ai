import importlib.util
import hashlib
from pathlib import Path
import json
import os
import sys
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

src = Path(__file__).resolve().parents[1] / "scripts" / "oc2_slice_b_git.py"
spec = importlib.util.spec_from_file_location("oc2_slice_b_git", src)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)

sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def command(repo: Path, *args: str) -> bytes:
    """Run fixture Git with isolated configuration and return stdout bytes."""
    home = repo.parent / "git-home"
    home.mkdir(mode=0o700, exist_ok=True)
    r = subprocess.run(
        ["git", "-C", str(repo), *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={
            "PATH": "/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/dev/null",
            "GIT_CONFIG_KEY_1": "commit.gpgSign", "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "false",
        }
    )
    if r.returncode:
        raise AssertionError((args, r.stderr.decode()))
    return r.stdout


class Key:
    """Minimal SessionKey fixture; production validation is exercised separately."""

    def __init__(self) -> None:
        """Create stable-format identifiers for bundle tests."""
        self.workspace_id = "a" * 32
        self.sandbox_id = str(uuid.uuid4())
        self.session_generation = str(uuid.uuid4())

    def validate(self) -> None:
        """Check only the workspace ID shape used by this test fixture."""
        if len(self.workspace_id) != 32:
            raise ValueError("invalid key")

    def __eq__(self, other: object) -> bool:
        """Compare fixture key fields."""
        return vars(self) == vars(other)


class GitAdmission(unittest.TestCase):
    def setUp(self) -> None:
        """Create and commit a clean repository used by admission tests."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        command(self.root, "init", "-b", "work")
        command(self.root, "config", "user.name", "Fixture")
        command(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "hello.txt").write_text("hello\n")
        command(self.root, "add", "hello.txt")
        command(self.root, "commit", "-m", "first")

    def _add_linked_worktree(self, name: str) -> Path:
        """Create a real linked Git worktree in the test-only repository."""
        linked = Path(self.tmp.name) / name
        command(self.root, "worktree", "add", "-qb", name, str(linked))
        return linked

    def test_accept_main_repo_with_two_live_linked_worktrees(self) -> None:
        """Valid linked worktree registrations do not block main HEAD admission."""
        self._add_linked_worktree("linked-one")
        self._add_linked_worktree("linked-two")
        baseline = mod.admit_clean_repo(self.root)
        self.assertEqual(baseline.branch_ref, "refs/heads/work")
        mod.recheck_host_baseline(baseline)

    def test_accept_linked_index_larger_than_control_file_limit(self) -> None:
        """A normal linked Index need not fit the 4 KiB metadata file bound."""
        for i in range(60):
            (self.root / ("source_%03d_" % i + "x" * 48)).write_text("content\n")
        command(self.root, "add", "-A")
        command(self.root, "commit", "-m", "large index")
        self._add_linked_worktree("linked-one")
        index = self.root / ".git" / "worktrees" / "linked-one" / "index"
        self.assertGreater(index.stat().st_size, 4096)
        self.assertEqual(mod._root_metadata(self.root)[1], 20)

    def test_reject_broken_registered_worktree_reverse_pointer(self) -> None:
        """A changed .git backlink is rejected instead of silently trusted."""
        linked = self._add_linked_worktree("linked-one")
        (linked / ".git").write_text("gitdir: /tmp/other.git\n")
        with self.assertRaisesRegex(mod.SliceBGitRejected, "reverse reference"):
            mod.admit_clean_repo(self.root)

    def test_reject_missing_linked_worktree_gitfile(self) -> None:
        """Stale registration must fail closed rather than being pruned."""
        linked = self._add_linked_worktree("linked-one")
        (linked / ".git").unlink()
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_linked_worktree_gitfile_symlink(self) -> None:
        """The backlink cannot be redirected through a symlink."""
        linked = self._add_linked_worktree("linked-one")
        backlink = linked / ".git"
        content = backlink.read_bytes()
        backlink.unlink()
        real = linked / ".git-real"
        real.write_bytes(content)
        backlink.symlink_to(real)
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_tampered_worktree_commondir(self) -> None:
        """A linked worktree pointing outside the main .git is rejected."""
        self._add_linked_worktree("linked-one")
        common = self.root / ".git" / "worktrees" / "linked-one" / "commondir"
        common.write_text("../../..\n")
        with self.assertRaisesRegex(mod.SliceBGitRejected, "common directory"):
            mod.admit_clean_repo(self.root)

    def test_reject_symlink_registration_directory(self) -> None:
        """Do not follow a symlinked .git/worktrees registry."""
        self._add_linked_worktree("linked-one")
        registry = self.root / ".git" / "worktrees"
        destination = self.root / ".git" / "registrations-real"
        registry.rename(destination)
        registry.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(mod.SliceBGitRejected, "unsafe worktree registration"):
            mod.admit_clean_repo(self.root)

    def test_reject_shallow_even_with_live_worktree(self) -> None:
        """Existing shallow-git rejection remains in force."""
        self._add_linked_worktree("linked-one")
        (self.root / ".git" / "shallow").write_text("a" * 40 + "\n")
        with self.assertRaisesRegex(mod.SliceBGitRejected, "unsupported Git object"):
            mod.admit_clean_repo(self.root)

    def test_accept_clean_branch_and_manifest_roundtrip(self) -> None:
        """A clean fixture admits and its generated manifest verifies."""
        b = mod.admit_clean_repo(self.root)
        self.assertEqual(b.branch_ref, "refs/heads/work")
        self.assertEqual(b.object_format, "sha1")
        path = Path(self.tmp.name) / "baseline.bundle"
        artifact = mod.build_verified_bundle(
            b, path, key=Key(), runtime_sha256="f" * 64
        )
        m = mod.verify_bundle_manifest(
            artifact,
            expected_key=artifact.key,
            expected_manifest_sha256=artifact.manifest_sha256,
            expected_runtime_sha256="f" * 64,
        )
        self.assertEqual(m.baseline.head_oid, b.head_oid)
        self.assertEqual(
            json.loads(artifact.manifest_path.read_text())["bundle_sha256"],
            artifact.bundle_sha256,
        )

    def test_reject_ita_and_unknown_index(self) -> None:
        """Intent-to-add entries are rejected by clean admission."""
        (self.root / "new").write_text("data")
        command(self.root, "add", "-N", "new")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_dirty(self) -> None:
        """Untracked files prevent admission."""
        (self.root / "untracked").write_text("untracked")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_secret_in_ancestor(self) -> None:
        """Secrets in reachable history prevent admission."""
        (self.root / "private").write_bytes(
            b"-----BEGIN RSA PRIVATE KEY-----\nabcdef\n"
        )
        command(self.root, "add", "private")
        command(self.root, "commit", "-m", "secret")
        (self.root / "private").unlink()
        command(self.root, "add", "-u")
        command(self.root, "commit", "-m", "remove")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_unsupported_config(self) -> None:
        """Unsupported local Git configuration prevents admission."""
        command(self.root, "config", "core.fsmonitor", "true")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_manifest_tamper(self) -> None:
        """Manifest byte changes invalidate its pinned digest."""
        b = mod.admit_clean_repo(self.root)
        art = mod.build_verified_bundle(
            b, Path(self.tmp.name) / "x.bundle", key=Key(), runtime_sha256="f" * 64
        )
        art.manifest_path.write_text(
            art.manifest_path.read_text().replace("sha1", "sha256")
        )
        with self.assertRaises(mod.SliceBGitRejected):
            mod.verify_bundle_manifest(
                art,
                expected_key=art.key,
                expected_manifest_sha256=art.manifest_sha256,
                expected_runtime_sha256="f" * 64,
            )

    def test_detect_host_divergence(self) -> None:
        """A worktree change after admission invalidates the baseline."""
        b = mod.admit_clean_repo(self.root)
        (self.root / "hello.txt").write_text("changed")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.recheck_host_baseline(b)

    def test_reject_assume_valid_index_entry(self) -> None:
        """Assume-valid flags are rejected even when status reports clean."""
        command(self.root, "update-index", "--assume-unchanged", "hello.txt")
        raw = bytearray((self.root / ".git" / "index").read_bytes())
        flags_offset = 12 + 40 + 20
        flags = int.from_bytes(raw[flags_offset:flags_offset + 2], "big") | 0x8000
        raw[flags_offset:flags_offset + 2] = flags.to_bytes(2, "big")
        checksum = hashlib.sha1(raw[:-20]).digest()
        (self.root / ".git" / "index").write_bytes(raw[:-20] + checksum)
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_worktree_change_during_history_scan(self) -> None:
        """A tracked file mutation during history scanning aborts admission."""
        scan_history = mod._scan_history

        def scan_then_change(root: Path, oid_bytes: int) -> None:
            scan_history(root, oid_bytes)
            (root / "hello.txt").write_text("changed during inspection\n")

        with patch.object(mod, "_scan_history", scan_then_change):
            with self.assertRaises(mod.SliceBGitRejected):
                mod.admit_clean_repo(self.root)

    def test_worktree_hash_ignores_non_git_permission_bits(self) -> None:
        """Baseline transfer hash normalizes host-only permission bits."""
        before = mod.admit_clean_repo(self.root)
        os.chmod(self.root / "hello.txt", 0o600)
        after = mod.admit_clean_repo(self.root)
        self.assertEqual(before.worktree_sha256, after.worktree_sha256)

    def test_reject_oversized_manifest_during_bounded_read(self) -> None:
        """Manifest verification rejects bytes beyond its read limit."""
        baseline = mod.admit_clean_repo(self.root)
        artifact = mod.build_verified_bundle(
            baseline, Path(self.tmp.name) / "bounded.bundle", key=Key(),
            runtime_sha256="f" * 64,
        )
        with artifact.manifest_path.open("ab") as stream:
            stream.write(b" " * (mod.MAX_MANIFEST + 1))
        with self.assertRaises(mod.SliceBGitRejected):
            mod.verify_bundle_manifest(
                artifact, expected_key=artifact.key,
                expected_manifest_sha256=artifact.manifest_sha256,
                expected_runtime_sha256="f" * 64,
            )

    def test_reject_oversized_bundle_during_bounded_read(self) -> None:
        """Bundle verification rejects data exceeding the capped read."""
        baseline = mod.admit_clean_repo(self.root)
        artifact = mod.build_verified_bundle(
            baseline, Path(self.tmp.name) / "bounded.bundle", key=Key(),
            runtime_sha256="f" * 64,
        )
        with artifact.bundle_path.open("ab") as stream:
            stream.write(b"x" * (mod.MAX_BUNDLE + 1))
        with self.assertRaises(mod.SliceBGitRejected):
            mod.verify_bundle_manifest(
                artifact, expected_key=artifact.key,
                expected_manifest_sha256=artifact.manifest_sha256,
                expected_runtime_sha256="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
