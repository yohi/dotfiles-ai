import importlib.util
from pathlib import Path
import json
import sys
import subprocess
import tempfile
import unittest
import uuid

src = Path(__file__).resolve().parents[1] / "scripts" / "oc2_slice_b_git.py"
spec = importlib.util.spec_from_file_location("oc2_slice_b_git", src)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)

sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def command(repo, *args):
    r = subprocess.run(
        ["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if r.returncode:
        raise AssertionError((args, r.stderr.decode()))
    return r.stdout


class Key:
    def __init__(self):
        self.workspace_id = "a" * 32
        self.sandbox_id = str(uuid.uuid4())
        self.session_generation = str(uuid.uuid4())

    def validate(self):
        if len(self.workspace_id) != 32:
            raise ValueError("invalid key")

    def __eq__(self, other):
        return vars(self) == vars(other)


class GitAdmission(unittest.TestCase):
    def setUp(self):
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

    def test_accept_clean_branch_and_manifest_roundtrip(self):
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

    def test_reject_ita_and_unknown_index(self):
        (self.root / "new").write_text("data")
        command(self.root, "add", "-N", "new")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_dirty(self):
        (self.root / "untracked").write_text("untracked")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_secret_in_ancestor(self):
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

    def test_reject_unsupported_config(self):
        command(self.root, "config", "core.fsmonitor", "true")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.admit_clean_repo(self.root)

    def test_reject_manifest_tamper(self):
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

    def test_detect_host_divergence(self):
        b = mod.admit_clean_repo(self.root)
        (self.root / "hello.txt").write_text("changed")
        with self.assertRaises(mod.SliceBGitRejected):
            mod.recheck_host_baseline(b)


if __name__ == "__main__":
    unittest.main()
