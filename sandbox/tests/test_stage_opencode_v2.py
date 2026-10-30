"""Offline tests: no real sbx process, network, or OpenCode configuration writes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage_opencode_v2.py"
sys.path.insert(0, str(SCRIPT.parent))
import stage_opencode_v2 as stage  # noqa: E402
import prepare_opencode_v2 as exporter  # noqa: E402


class StageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.bundle = Path(temporary.name) / "bundle"
        self.bundle.mkdir()
        self.apm = self.root / "apm.yml"
        self.apm.write_text("shell: bash\nsnapshot: true\n", encoding="utf-8")
        server = {
            "$schema": "https://opencode.ai/config.json", "shell": "bash",
            "snapshot": True, "plugins": [], "mcp": {},
        }
        tui = {"$schema": "https://opencode.ai/v2/cli.json", "plugins": []}
        for name, value in (("opencode.jsonc", server), ("cli.json", tui)):
            (self.bundle / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
        manifest = {
            "schema": "dotfiles-ai/sandbox-export/v0",
            "generator": "v0.1", "source": "apm.yml",
            "source_sha256": hashlib.sha256(self.apm.read_bytes()).hexdigest(),
            "opencode_version": "2.1.4", "plugins_exported": 0,
            "mcp_entries_exported": 0,
            "artifacts_sha256": {
                name: hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
                for name in ("opencode.jsonc", "cli.json")
            },
        }
        (self.bundle / "export-manifest.json").write_text(json.dumps(manifest) + "\n")

    def test_guest_verify_valid_bundle(self) -> None:
        process = subprocess.run([sys.executable, str(SCRIPT), "--verify-bundle", str(self.bundle)],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("VERIFY_OK", process.stdout)

    def test_rejects_changed_config_and_extra_files(self) -> None:
        config = self.bundle / "cli.json"
        config.write_text("{}\n")
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle)
        config.unlink()
        (self.bundle / "extra.txt").write_text("unknown")
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle)

    def test_rejects_symlinked_member(self) -> None:
        member = self.bundle / "cli.json"
        member.unlink()
        member.symlink_to(self.apm)
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle)

    def test_rejects_plugin_or_mcp_config_even_with_updated_hash(self) -> None:
        manifest_file = self.bundle / "export-manifest.json"
        config_file = self.bundle / "opencode.jsonc"
        payload = json.loads(config_file.read_text())
        payload["plugins"] = ["unsafe"]
        config_file.write_text(json.dumps(payload))
        manifest = json.loads(manifest_file.read_text())
        manifest["artifacts_sha256"]["opencode.jsonc"] = hashlib.sha256(config_file.read_bytes()).hexdigest()
        manifest_file.write_text(json.dumps(manifest))
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle)

    def test_dry_run_does_not_invoke_sbx(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run") as run:
            stage.stage(self.bundle, self.root, sandbox=None, apply=False)
            run.assert_not_called()

    def test_host_provenance_failure_refuses_transfer(self) -> None:
        with patch.object(stage, "_check_source", side_effect=stage.StageError("bad source")), \
             patch.object(stage, "_run") as run:
            with self.assertRaises(stage.StageError):
                stage.stage(self.bundle, self.root, "oc-v2-poc", apply=True)
            run.assert_not_called()

    def test_apply_stages_and_verifies_without_activation(self) -> None:
        commands = []
        def capture(argv: list[str]) -> None:
            commands.append(argv)
            if argv[1] == "cp":
                self.assertTrue(Path(argv[2]).exists())
        with patch.object(stage, "_check_source"), \
             patch.object(stage.shutil, "which", return_value="/usr/bin/sbx"), \
             patch.object(stage, "_run", side_effect=capture):
            stage.stage(self.bundle, self.root, sandbox="oc-v2-poc", apply=True)
        self.assertEqual(len(commands), 4)
        self.assertEqual([command[1] for command in commands], ["exec", "cp", "cp", "exec"])
        remote = commands[-1][-1]
        self.assertTrue(remote.startswith(stage.REMOTE_PARENT + "/sbx-config-"))
        self.assertNotIn(".config/opencode", repr(commands))
        self.assertNotIn("--privileged", repr(commands))
        self.assertNotIn("-u", repr(commands))
        self.assertEqual(commands[-1][3], "python3")
        self.assertEqual(commands[2][-1], "oc-v2-poc:" + commands[-1][4])
        self.assertFalse(commands[-1][4].startswith(remote + "/"))
        self.assertEqual(commands[0][-1], commands[-1][4])

    def test_apply_requires_valid_sandbox_name(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run") as run:
            for bad in (None, "../host", "bad:name", "", "-bad"):
                with self.subTest(bad=bad), self.assertRaises(stage.StageError):
                    stage.stage(self.bundle, self.root, bad, apply=True)
            run.assert_not_called()

    def test_source_check_refuses_missing_apm_source(self) -> None:
        with self.assertRaises(stage.StageError):
            stage._check_source(self.root, self.bundle)

    def test_source_check_verifies_snapshot_without_executing_a_process(self) -> None:
        shell, snapshot, source_hash = exporter._read_apm(self.root)
        generated = exporter._build_files(shell, snapshot, source_hash)
        for name, content in generated.items():
            (self.bundle / name).write_bytes(content)
        with patch.object(stage.subprocess, "run", side_effect=AssertionError("unexpected process")):
            stage._check_source(self.root, self.bundle)

    def test_no_live_host_paths_are_written(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run"):
            stage.stage(self.bundle, self.root, None, False)
        self.assertFalse((self.root / ".config").exists())


if __name__ == "__main__":
    unittest.main()
