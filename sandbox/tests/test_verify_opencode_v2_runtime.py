"""Offline checks for the P6-5 static/runtime-version verifier.

No actual sbx, OpenCode binary, network, model prompts, or host configuration.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import prepare_opencode_v2_runtime as runtime  # noqa: E402
import verify_opencode_v2_runtime as verify  # noqa: E402


class VerifyRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.space = Path(temp.name) / "workspace"
        self.space.mkdir()
        for module in (runtime, verify):
            p = patch.object(module, "WORKSPACE", self.space)
            p.start()
            self.addCleanup(p.stop)

        self.bundle = self.space / "sbx-config-test"
        self.bundle.mkdir()
        self.server = {
            "$schema": "https://opencode.ai/config.json",
            "shell": "bash", "snapshot": True, "plugins": [], "mcp": {},
        }
        self.tui = {
            "$schema": "https://opencode.ai/v2/cli.json",
            "plugins": [],
        }
        for name, value in (("opencode.jsonc", self.server), ("cli.json", self.tui)):
            (self.bundle / name).write_text(json.dumps(value))
        manifest = {
            "schema": "dotfiles-ai/sandbox-export/v0",
            "generator": "v0.1", "source": "apm.yml",
            "source_sha256": "b" * 64,
            "opencode_version": "2.1.4",
            "plugins_exported": 0, "mcp_entries_exported": 0,
            "artifacts_sha256": {
                name: hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
                for name in ("opencode.jsonc", "cli.json")
            },
        }
        (self.bundle / "export-manifest.json").write_text(json.dumps(manifest))

        self.runtime = self.space / "isolated-runtime"
        self.bin = self.space / "opencode-stub"
        self.bin.write_text("#!/bin/sh\nprintf 'opencode v2.1.4\\n'\n")
        self.bin.chmod(0o700)
        self.akane = self._plugin("akane")
        self.sibyl = self._plugin("sibyl")

    def _plugin(self, kind: str) -> Path:
        folder = self.space / kind
        (folder / "dist").mkdir(parents=True)
        name, version, path = runtime.PLUGINS[kind]
        exports = {".": "./dist/index.js"} if kind == "akane" else {
            "./tui": {"types": "./dist/tui-v2.d.ts", "import": "./dist/tui.js"}
        }
        (folder / "package.json").write_text(
            json.dumps({"name": name, "version": version, "exports": exports})
        )
        (folder / path).write_text("export default {}")
        return folder

    def build(self, akane: bool = True, sibyl: bool = True) -> None:
        runtime.prepare(
            self.bundle, self.runtime, self.bin,
            self.akane if akane else None,
            self.sibyl if sibyl else None, write=True,
        )

    def rewrite_hash(self, name: str) -> None:
        receipt_path = self.runtime / "runtime-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        key = "server_sha256" if name == "opencode.jsonc" else "cli_sha256"
        receipt[key] = hashlib.sha256(
            (self.runtime / "xdg-config/opencode" / name).read_bytes()
        ).hexdigest()
        receipt_path.write_text(json.dumps(receipt))

    def test_valid_runtime_static_status(self) -> None:
        self.build()
        evidence = verify.verify(self.bundle, self.runtime)
        self.assertEqual(evidence["status"], "STATIC_VERIFIED_RUNTIME_UNPROVEN")
        self.assertEqual(evidence["server_registration"], "akane@3.0.0-alpha.2")
        self.assertEqual(evidence["tui_registration"], "sibyl@3.0.0-alpha.1")

    def test_version_probe_with_safe_stub(self) -> None:
        self.build()
        verify.verify(self.bundle, self.runtime)
        verify.probe_version(self.runtime)

    def test_failing_version_probe_never_echoes_stderr(self) -> None:
        self.bin.write_text("#!/bin/sh\necho pretend-secret >&2\nexit 1\n")
        self.build()
        with self.assertRaises(verify.StageError) as ctx:
            verify.probe_version(self.runtime)
        self.assertNotIn("pretend-secret", str(ctx.exception))

    def test_refuse_runtime_without_both_plugins(self) -> None:
        self.build(sibyl=False)
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_unexpected_config_even_after_resigning_receipt(self) -> None:
        self.build()
        config = self.runtime / "xdg-config/opencode/opencode.jsonc"
        data = json.loads(config.read_text())
        data["plugins"].append("unexpected-plugin")
        config.write_text(json.dumps(data))
        self.rewrite_hash("opencode.jsonc")
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_extra_mcp_even_after_resigning_receipt(self) -> None:
        self.build()
        config = self.runtime / "xdg-config/opencode/opencode.jsonc"
        data = json.loads(config.read_text())
        data["mcp"]["remote"] = {"url": "http://example.invalid"}
        config.write_text(json.dumps(data))
        self.rewrite_hash("opencode.jsonc")
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_invalid_sibyl_package_exports(self) -> None:
        self.build()
        path = self.sibyl / "package.json"
        meta = json.loads(path.read_text())
        meta["exports"] = {".": "./dist/index.js"}
        path.write_text(json.dumps(meta))
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_tampered_manifest(self) -> None:
        self.build()
        receipt = self.runtime / "runtime-receipt.json"
        contents = json.loads(receipt.read_text())
        contents["source_manifest_sha256"] = "f" * 64
        receipt.write_text(json.dumps(contents))
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_symlinked_runtime_config(self) -> None:
        self.build()
        target = self.runtime / "xdg-config/opencode/cli.json"
        safe = self.space / "other-client.json"
        safe.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(safe)
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.runtime)

    def test_refuse_workspace_escape(self) -> None:
        self.build()
        with self.assertRaises(verify.StageError):
            verify.verify(self.bundle, self.space.parent)

    def test_workspace_path_errors_do_not_disclose_existence(self) -> None:
        missing = self.space / "missing"
        outside = self.space.parent / "existing-outside-workspace"
        outside.mkdir()

        errors = []
        for path in (missing, outside):
            with self.assertRaises(verify.StageError) as ctx:
                verify._workspace_dir(path)
            errors.append(str(ctx.exception))

        self.assertEqual(errors[0], errors[1])

    def test_verification_does_not_modify_files(self) -> None:
        self.build()
        tracked = [
            self.runtime / "runtime-receipt.json",
            self.runtime / "xdg-config/opencode/opencode.jsonc",
            self.runtime / "xdg-config/opencode/cli.json",
        ]
        before = [p.read_bytes() for p in tracked]
        verify.verify(self.bundle, self.runtime)
        self.assertEqual([p.read_bytes() for p in tracked], before)


if __name__ == "__main__":
    unittest.main()
