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


def git(root: Path, *args: str) -> str:
    """Run an isolated fixture Git command and return its decoded output."""
    home = root.parent / "git-home"
    home.mkdir(mode=0o700, exist_ok=True)
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        env={
            "PATH": "/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/dev/null",
            "GIT_CONFIG_KEY_1": "commit.gpgSign", "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "false",
        },
    )
    if p.returncode:
        raise AssertionError(p.stderr.decode())
    return p.stdout.decode().strip()


class EntryTests(unittest.TestCase):
    def setUp(self) -> None:
        """Create a clean Guest repository and capture its baseline HEAD/ref."""
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

    def test_wire_strict_validation(self) -> None:
        """Syntax validation rejects malformed frames; baseline equality is separate."""
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

    def test_tui_nonzero_never_fixtures(self) -> None:
        """A nonzero TUI exit code returns its dedicated status without fixture use."""
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=5),
            patch.object(e, "_supervisor_fixture_boundary") as b,
        ):
            self.assertEqual(e.run_entrypoint(self.line), 23)
            b.assert_not_called()

    def test_missing_boundary_blocks_fixture(self) -> None:
        """The unavailable trusted fixture boundary blocks execution after baseline checks."""
        with (
            patch.object(e, "_check_guest_baseline"),
            patch.object(e, "_run_tui", return_value=0),
        ):
            self.assertEqual(e.run_entrypoint(self.line), 22)
            self.assertFalse((self.root / f.FIXTURE_NAME).exists())

    def test_fixture_exact_commit_and_preserves_other_staged(self) -> None:
        """Fixture commit changes only its path and retains other staged state."""
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

    def test_refuse_existing_fixture(self) -> None:
        """An existing fixture path is preserved and rejected."""
        (self.root / f.FIXTURE_NAME).write_text("original")
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")
        self.assertEqual((self.root / f.FIXTURE_NAME).read_text(), "original")

    def test_refuse_different_baseline(self) -> None:
        """A mismatched expected baseline is refused before fixture creation."""
        with self.assertRaises(f.SliceBFixtureError):
            f.run_offline_fixture(self.root, "f" * 40, "refs/heads/sliceb")

    def test_reject_commit_with_unexpected_fixture_blob(self) -> None:
        """Committed fixture blob is checked independently of working file bytes."""
        def commit_wrong_blob(root: Path, *args: str) -> bytes:
            if args and args[0] == "commit":
                fixture = root / f.FIXTURE_NAME
                fixture.write_bytes(b"unexpected committed fixture\n")
                result = git(root, *args).encode()
                fixture.write_bytes(f.FIXTURE_BYTES)
                return result
            return git(root, *args).encode()

        with patch.object(f, "_git", side_effect=commit_wrong_blob):
            with self.assertRaises(f.SliceBFixtureError):
                f.run_offline_fixture(self.root, self.head, "refs/heads/sliceb")


if __name__ == "__main__":
    unittest.main()
