"""Offline tests for Sandbox-local OpenCode v2 config preparation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import prepare_opencode_v2_runtime as runtime  # noqa: E402


class RuntimePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.space = Path(temporary.name) / "workspace"
        self.space.mkdir()
        workspace_patch = patch.object(runtime, "WORKSPACE", self.space)
        workspace_patch.start()
        self.addCleanup(workspace_patch.stop)

        self.bundle = self.space / "sbx-config-example"
        self.bundle.mkdir()
        server = {
            "$schema": "https://opencode.ai/config.json",
            "shell": "bash", "snapshot": True,
            "plugins": [], "mcp": {},
        }
        client = {
            "$schema": "https://opencode.ai/v2/cli.json",
            "plugins": [],
        }
        for name, data in (("opencode.jsonc", server), ("cli.json", client)):
            (self.bundle / name).write_text(json.dumps(data), encoding="utf-8")
        manifest = {
            "schema": "dotfiles-ai/sandbox-export/v0",
            "generator": "v0.1",
            "source": "apm.yml",
            "source_sha256": "a" * 64,
            "opencode_version": "2.1.4",
            "plugins_exported": 0,
            "mcp_entries_exported": 0,
            "artifacts_sha256": {
                name: hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
                for name in ("opencode.jsonc", "cli.json")
            },
        }
        (self.bundle / "export-manifest.json").write_text(json.dumps(manifest))

        self.destination = self.space / "runtime"
        self.binary = self.space / "opencode-stub"
        self.binary.write_text("#!/bin/sh\nprintf 'stub-ok\\n'\n", encoding="utf-8")
        self.binary.chmod(0o700)

    def plugin(self, kind: str) -> Path:
        folder = self.space / kind
        (folder / "dist").mkdir(parents=True)
        name, version, entry = runtime.PLUGINS[kind]
        (folder / "package.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8"
        )
        (folder / entry).write_text("export default {}", encoding="utf-8")
        return folder

    def test_dry_run_does_not_write(self) -> None:
        runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=False)
        self.assertFalse(self.destination.exists())

    def test_isolated_launcher_does_not_inherit_environment(self) -> None:
        with patch.dict(os.environ, {"SENSITIVE_FAKE_KEY": "never-forwarded"}):
            runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=True)
            launcher = self.destination / "run-opencode.sh"
            self.assertIn("env -i", launcher.read_text())
            self.assertNotIn("never-forwarded", launcher.read_text())
            self.assertIn("XDG_CONFIG_HOME=", launcher.read_text())
            result = subprocess.run([str(launcher), "--version"], text=True,
                                    capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stub-ok", result.stdout)
        self.assertFalse((self.space / ".config").exists())

    def test_server_and_tui_plugins_are_separate(self) -> None:
        akane = self.plugin("akane")
        sibyl = self.plugin("sibyl")
        runtime.prepare(self.bundle, self.destination, self.binary, akane, sibyl, write=True)
        root = self.destination / "xdg-config" / "opencode"
        server = json.loads((root / "opencode.jsonc").read_text())
        cli = json.loads((root / "cli.json").read_text())
        self.assertEqual(server["plugins"], [str(akane)])
        self.assertEqual(cli["plugins"], [str(sibyl)])
        self.assertEqual(server["mcp"], {})

    def test_receipt_tracks_configuration(self) -> None:
        runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=True)
        root = self.destination / "xdg-config" / "opencode"
        receipt = json.loads((self.destination / "runtime-receipt.json").read_text())
        self.assertEqual(receipt["status"], "prepared-not-executed")
        self.assertEqual(
            receipt["server_sha256"],
            hashlib.sha256((root / "opencode.jsonc").read_bytes()).hexdigest(),
        )

    def test_wrong_package_version_refused_before_writes(self) -> None:
        akane = self.plugin("akane")
        meta = akane / "package.json"
        metadata = json.loads(meta.read_text())
        metadata["version"] = "1.0.0"
        meta.write_text(json.dumps(metadata))
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, akane, None, write=True)
        self.assertFalse(self.destination.exists())

    def test_missing_entrypoint_refused(self) -> None:
        sibyl = self.plugin("sibyl")
        (sibyl / "dist/tui.js").unlink()
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, None, sibyl, write=True)

    def test_symlinked_package_refused(self) -> None:
        akane = self.plugin("akane")
        link = self.space / "linked-akane"
        link.symlink_to(akane, target_is_directory=True)
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, link, None, write=True)

    def test_symlinked_plugin_dist_refused(self) -> None:
        akane = self.plugin("akane")
        (akane / "dist/index.js").unlink()
        (akane / "dist").rmdir()
        outside = self.space / "other-dist"
        outside.mkdir()
        (outside / "index.js").write_text("export default {}")
        (akane / "dist").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, akane, None, write=True)

    def test_existing_runtime_refused(self) -> None:
        runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=True)
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=True)

    def test_outside_workspace_refused(self) -> None:
        outside = self.space.parent / "outside"
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, outside, self.binary, None, None, write=True)

    def test_tampered_bundle_refused(self) -> None:
        (self.bundle / "cli.json").write_text("{}")
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, self.destination, self.binary, None, None, write=True)
        self.assertFalse(self.destination.exists())

    def test_symlinked_runtime_parent_refused(self) -> None:
        real = self.space / "real"
        real.mkdir()
        link = self.space / "link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(runtime.StageError):
            runtime.prepare(self.bundle, link / "runtime", self.binary, None, None, write=True)


if __name__ == "__main__":
    unittest.main()
