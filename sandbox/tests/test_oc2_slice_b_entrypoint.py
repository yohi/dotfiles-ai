from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

TOP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "entrypoint", TOP / "oc2_slice_b" / "entrypoint.py"
)
assert spec is not None and spec.loader is not None
e = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = e
spec.loader.exec_module(e)
sys.path.insert(0, str(TOP / "oc2_slice_b"))
import offline_fixture as f  # noqa: E402


def git(root, *args):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if p.returncode:
        raise AssertionError(p.stderr.decode())
    return p.stdout.decode().strip()


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "sliceb")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "original").write_text("before\n")
        git(self.root, "add", "original")
        git(self.root, "commit", "-m", "base")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.line = f"OC2_SLICE_B_START {uuid.uuid4()} {self.head} refs/heads/sliceb {'a' * 64}\n"

    def test_wire_strict_validation(self):
        a = e.parse_start_line(self.line)
        self.assertEqual(a.head_oid, self.head)
        for wrong in [
            self.line.rstrip("\n"),
            self.line.replace(" ", "  ", 1),
            self.line + "x",
            self.line.replace(self.head, "f" * 40),
            self.line.replace("sliceb", "..bad"),
        ]:
            if wrong == self.line.replace(self.head, "f" * 40):
                # valid syntax but changed expected head: reject in Guest comparison
                continue
            with self.assertRaises(e.SliceBEntryRejected):
                e.parse_start_line(wrong)

    def test_tui_nonzero_never_fixtures(self):
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=5),
            patch.object(e, "_supervisor_fixture_boundary") as b,
        ):
            self.assertEqual(e.run_entrypoint(self.line), 23)
            b.assert_not_called()

    def test_missing_boundary_blocks_fixture(self):
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=0),
        ):
            self.assertEqual(e.run_entrypoint(self.line), 22)
            self.assertFalse((self.root / f.FIXTURE_NAME).exists())

    def test_fixture_exact_commit_and_preserves_other_staged(self):
        (self.root / "original").write_text("modified\n")
        git(self.root, "add", "original")
        before = git(self.root, "ls-files", "--stage", "original")
        commit = f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")
        self.assertEqual(
            git(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split(),
            [commit, self.head],
        )
        self.assertEqual(
            git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
            f.FIXTURE_NAME,
        )
        self.assertEqual((self.root / f.FIXTURE_NAME).read_bytes(), f.FIXTURE_BYTES)
        self.assertEqual(git(self.root, "ls-files", "--stage", "original"), before)
        self.assertEqual(
            git(self.root, "show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD"),
            f"{f.FIXTURE_USER}|{f.FIXTURE_EMAIL}|{f.FIXTURE_USER}|{f.FIXTURE_EMAIL}",
        )

    def test_refuse_existing_fixture(self):
        (self.root / f.FIXTURE_NAME).write_text("original")
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")
        self.assertEqual((self.root / f.FIXTURE_NAME).read_text(), "original")

    def test_refuse_different_baseline(self):
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, "f" * 40, "refs/heads/sliceb")


if __name__ == "__main__":
    unittest.main()
