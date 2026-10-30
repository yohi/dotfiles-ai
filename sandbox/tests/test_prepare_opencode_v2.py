"""Read-only and fail-closed tests for the Sandbox config snapshot generator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_opencode_v2.py"


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "dotfiles-ai"
        self.root.mkdir()
        self.out = Path(self.tmp.name) / "export"
        self.apm = self.root / "apm.yml"
        self.apm.write_text(
            "shell: bash\nsnapshot: true\n"
            "plugin:\n - private/plugin\n"
            "dependencies:\n  mcp:\n    - name: privileged\n"
            "      command: /srv/test-only/secret\n"
            "provider:\n  hidden:\n    apiKey: TOP_SECRET_DO_NOT_EXPORT\n",
            encoding="utf-8",
        )

    def run_export(self, *flags: str, output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo-root", str(self.root),
                "--out", str(output or self.out), *flags,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_whitelist_never_exports_plugins_mcp_or_secrets(self) -> None:
        before = self.apm.read_bytes()
        self.assertEqual(self.run_export().returncode, 0)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        tui = json.loads((self.out / "cli.json").read_text())
        self.assertEqual(server["plugins"], [])
        self.assertEqual(server["mcp"], {})
        self.assertEqual(server["shell"], "bash")
        self.assertIs(server["snapshot"], True)
        self.assertEqual(tui["plugins"], [])
        for output in self.out.iterdir():
            content = output.read_text()
            self.assertNotIn("TOP_SECRET_DO_NOT_EXPORT", content)
            self.assertNotIn("/srv/test-only/secret", content)
            self.assertNotIn("private/plugin", content)
        self.assertEqual(self.apm.read_bytes(), before)

    def test_manifest_hashes_are_correct(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest["source_sha256"], hashlib.sha256(self.apm.read_bytes()).hexdigest())
        self.assertEqual(manifest["opencode_version"], "2.1.4")
        self.assertEqual(manifest["mcp_entries_exported"], 0)
        for name, sha in manifest["artifacts_sha256"].items():
            self.assertEqual(sha, hashlib.sha256((self.out / name).read_bytes()).hexdigest())

    def test_check_detects_modifications_without_writing(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        self.assertEqual(self.run_export("--check").returncode, 0)
        target = self.out / "cli.json"
        target.write_text("{}\n")
        self.assertNotEqual(self.run_export("--check").returncode, 0)
        self.assertEqual(target.read_text(), "{}\n")

    def test_refuses_overwrite(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_rejects_invalid_shell_and_snapshot(self) -> None:
        self.apm.write_text("shell: 'bash; cat /etc/passwd'\n")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.apm.write_text("shell: bash\nsnapshot: 'true'\n")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse(self.out.exists())

    def test_refuses_symlinked_apm(self) -> None:
        real = self.root / "real.yml"
        real.write_bytes(self.apm.read_bytes())
        self.apm.unlink()
        self.apm.symlink_to(real)
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_refuses_output_under_repository(self) -> None:
        self.assertNotEqual(
            self.run_export(output=self.root / "sandbox-out").returncode, 0
        )

    def test_refuses_symlinked_output_parent(self) -> None:
        target = Path(self.tmp.name) / "safe"
        target.mkdir()
        link = Path(self.tmp.name) / "link"
        link.symlink_to(target, target_is_directory=True)
        self.assertNotEqual(
            self.run_export(output=link / "export").returncode, 0
        )

    def test_refuses_unexpected_file_in_check(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        (self.out / "extra").write_text("unapproved")
        self.assertNotEqual(self.run_export("--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
