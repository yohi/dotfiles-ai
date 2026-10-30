"""Offline regression tests for guest runtime validation (no Docker/network/LLM)."""

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
import verify_opencode_v2_runtime as validator  # noqa: E402


class ValidateRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.space = Path(temp.name) / "workspace"
        self.space.mkdir()
        mock_workspace = patch.object(validator, "WORKSPACE", self.space)
        mock_workspace.start()
        self.addCleanup(mock_workspace.stop)
        self.bundle = self.space / "sbx-config-verified"
        self.bundle.mkdir()
        self.runtime = self.space / "runtime"
        self.config_dir = self.runtime / "xdg-config" / "opencode"
        self.config_dir.mkdir(parents=True)
        (self.runtime / "workspace").mkdir()
        (self.runtime / "xdg-data").mkdir()
        (self.runtime / "xdg-cache").mkdir()
        self.server = {
            "$schema": "https://opencode.ai/config.json",
            "shell": "bash", "snapshot": True,
            "plugins": [], "mcp": {},
        }
        self.cli = {
            "$schema": "https://opencode.ai/v2/cli.json",
            "plugins": [],
        }
        for name, data in (("opencode.jsonc", self.server), ("cli.json", self.cli)):
            (self.bundle / name).write_text(json.dumps(data), encoding="utf-8")
        manifest = {
            "schema": "dotfiles-ai/sandbox-export/v0",
            "generator": "v0.1",
            "source": "apm.yml",
            "source_sha256": "0" * 64,
            "opencode_version": "2.1.4",
            "plugins_exported": 0,
            "mcp_entries_exported": 0,
            "artifacts_sha256": {
                name: self.digest(self.bundle / name)
                for name in ("opencode.jsonc", "cli.json")
            },
        }
        (self.bundle / "export-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.runtime / "run-opencode.sh").write_text(
            "#!/bin/sh\nexec env -i XDG_CONFIG_HOME=/tmp/stub /bin/true\n", encoding="utf-8"
        )
        self.write_runtime()

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_runtime(self) -> None:
        for name, data in (("opencode.jsonc", self.server), ("cli.json", self.cli)):
            (self.config_dir / name).write_text(json.dumps(data), encoding="utf-8")
        receipt = {
            "schema": "dotfiles-ai/sandbox-runtime/v0",
            "source_manifest_sha256": self.digest(self.bundle / "export-manifest.json"),
            "server_sha256": self.digest(self.config_dir / "opencode.jsonc"),
            "cli_sha256": self.digest(self.config_dir / "cli.json"),
            "akane": "3.0.0-alpha.2" if self.server["plugins"] else None,
            "sibyl": "3.0.0-alpha.1" if self.cli["plugins"] else None,
            "status": "prepared-not-executed",
        }
        (self.runtime / "runtime-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    def make_plugin(self, kind: str) -> Path:
        path = self.space / kind
        (path / "dist").mkdir(parents=True)
        name, version, artifact = validator.PLUGIN_META[kind]
        (path / "package.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8"
        )
        (path / artifact).write_text("export default {};", encoding="utf-8")
        return path

    def enable_both(self) -> None:
        self.server["plugins"] = [str(self.make_plugin("akane"))]
        self.cli["plugins"] = [str(self.make_plugin("sibyl"))]
        self.write_runtime()

    def test_static_valid_without_plugins(self) -> None:
        info = validator.verify_runtime(self.bundle, self.runtime, require_both=False)
        self.assertTrue(info["snapshot_valid"])
        self.assertFalse(info["akane_configured"])
        self.assertFalse(info["sibyl_configured"])

    def test_static_require_both_valid(self) -> None:
        self.enable_both()
        info = validator.verify_runtime(self.bundle, self.runtime, require_both=True)
        self.assertTrue(info["akane_configured"])
        self.assertTrue(info["sibyl_configured"])

    def test_require_both_rejects_missing(self) -> None:
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=True)

    def test_runtime_digest_rejects_tampering(self) -> None:
        (self.config_dir / "cli.json").write_text("{}")
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=False)

    def test_rejects_extra_plugins_even_with_matching_receipt(self) -> None:
        self.server["plugins"] = ["arbitrary"]
        self.write_runtime()
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=False)

    def test_rejects_unauthorized_mcp_even_with_matching_receipt(self) -> None:
        self.server["mcp"] = {"unauthorized": {"type": "remote", "url": "https://example.invalid"}}
        self.write_runtime()
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=False)

    def test_rejects_plugin_version_tampering(self) -> None:
        self.enable_both()
        akane = Path(self.server["plugins"][0]) / "package.json"
        akane.write_text('{"name":"@yohi/akane","version":"99.0.0"}')
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=True)

    def test_rejects_symlinked_plugin_package(self) -> None:
        self.enable_both()
        akane = Path(self.server["plugins"][0])
        (akane / "package.json").rename(akane / "original-package.json")
        (akane / "package.json").symlink_to(akane / "original-package.json")
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=True)

    def test_rejects_symlinked_xdg_config_directory(self) -> None:
        real = self.runtime / "xdg-config"
        moved = self.runtime / "real-config"
        real.rename(moved)
        real.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.runtime, require_both=False)

    def test_rejects_symlinked_runtime_cache_for_cli_probe(self) -> None:
        cache = self.runtime / "xdg-cache"
        cache.rmdir()
        cache.symlink_to(self.space, target_is_directory=True)
        with self.assertRaises(validator.StageError):
            validator.probe_cli(self.runtime, self.make_cli_stub(), {})

    def test_rejects_runtime_outside_guest_workspace(self) -> None:
        with self.assertRaises(validator.StageError):
            validator.verify_runtime(self.bundle, self.space.parent, require_both=False)

    def make_cli_stub(self, *, version: str = "opencode v2.1.4",
                      plugins: list[str] | None = None,
                      mcp: dict | None = None,
                      secret: str = "SHOULD_NOT_APPEAR") -> Path:
        stub = self.space / "fake-opencode"
        config = json.dumps({"plugins": self.server["plugins"] if plugins is None else plugins,
                             "mcp": {} if mcp is None else mcp, "token": secret})
        source = (
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then\n'
            f"  printf '%s\\n' '{version}'\n"
            'elif [ "$1" = "debug" ] && [ "$2" = "config" ]; then\n'
            f"  printf '%s\\n' '{config}'\n"
            'else exit 2; fi\n'
        )
        stub.write_text(source, encoding="utf-8")
        stub.chmod(0o700)
        return stub

    def test_explicit_cli_probe_passes_with_matching_config(self) -> None:
        self.enable_both()
        info = validator.probe_cli(self.runtime, self.make_cli_stub(), {})
        self.assertTrue(info["merged_config_match"])
        self.assertFalse(info["sidebar_render_verified"])

    def test_cli_probe_refuses_wrong_version(self) -> None:
        stub = self.make_cli_stub(version="opencode v1.19.0")
        with self.assertRaises(validator.StageError):
            validator.probe_cli(self.runtime, stub, {})

    def test_cli_probe_refuses_unauthorized_mcp_without_leaking_token(self) -> None:
        stub = self.make_cli_stub(mcp={"bad": True}, secret="SENSITIVE_NEVER_LOG")
        with self.assertRaises(validator.StageError) as caught:
            validator.probe_cli(self.runtime, stub, {})
        self.assertNotIn("SENSITIVE_NEVER_LOG", str(caught.exception))

    def test_cli_probe_refuses_unexpected_plugin(self) -> None:
        stub = self.make_cli_stub(plugins=["unknown-plugin"])
        with self.assertRaises(validator.StageError):
            validator.probe_cli(self.runtime, stub, {})


if __name__ == "__main__":
    unittest.main()
