"""Offline tests for the opt-in Host OpenCode V1/V2 coexistence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "host/opencode2/opencode2"
INSTALLER = ROOT / "host/opencode2/install.sh"

FAKE_CLI = '''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] == ["--version"]:
    print("2.3.2")
else:
    keys = ["XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
        "OPENCODE_DB", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_DISABLE_AUTOUPDATE",
        "OPENCODE_DISABLE_CLAUDE_CODE"]
    print(json.dumps({"args": sys.argv[1:], "env": {k: os.environ.get(k) for k in keys}}))
'''

MOCK_NPM = '''#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == '--prefix' ]]
prefix="$2"
shift 2
[[ "$1" == 'install' ]]
mkdir -p "$prefix/node_modules/.bin"
cp "$FAKE_CLI_SOURCE" "$prefix/node_modules/.bin/opencode"
chmod 755 "$prefix/node_modules/.bin/opencode"
'''


class HostOpenCode2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.home = Path(self.dir.name) / "home"
        self.home.mkdir()
        self.bin = self.home / ".local/opt/opencode-v2-2.3.2/node_modules/.bin/opencode"
        self.fake = Path(self.dir.name) / "fake-opencode"
        self.fake.write_text(FAKE_CLI)
        self.fake.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "FAKE_CLI_SOURCE": str(self.fake)}

    def _cli(self) -> None:
        self.bin.parent.mkdir(parents=True, exist_ok=True)
        self.bin.write_text(FAKE_CLI)
        self.bin.chmod(0o755)

    def _run(self, script: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(script), *args],
            text=True, capture_output=True,
            cwd=ROOT, env=env or self.env,
            check=False,
        )

    def test_check_does_not_write(self) -> None:
        result = self._run(INSTALLER, "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("@opencode/cli@2.3.2", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_launcher_isolates_xdg_and_overrides_and_preserves_args(self) -> None:
        self._cli()
        env = {**self.env, "OPENCODE_DB": "/tmp/v1.sqlite", "OPENCODE_CONFIG": "/tmp/v1-config.json", "OPENCODE_CONFIG_DIR": "/tmp/v1", "OPENCODE_CONFIG_CONTENT": "secret"}
        result = self._run(LAUNCHER, "run", "hello world", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads(result.stdout)
        self.assertEqual(obj["args"], ["--standalone", "run", "hello world"])
        for key, suffix in (("XDG_CONFIG_HOME", ".config/opencode-v2"), ("XDG_DATA_HOME", ".local/share/opencode-v2"), ("XDG_CACHE_HOME", ".cache/opencode-v2"), ("XDG_STATE_HOME", ".local/state/opencode-v2")):
            self.assertEqual(obj["env"][key], str(self.home / suffix))
        for key in ("OPENCODE_DB", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT"):
            self.assertIsNone(obj["env"][key])
        self.assertEqual(obj["env"]["OPENCODE_DISABLE_PROJECT_CONFIG"], "1")
        self.assertEqual(obj["env"]["OPENCODE_DISABLE_CLAUDE_CODE"], "1")
        self.assertEqual(obj["env"]["OPENCODE_DISABLE_AUTOUPDATE"], "1")

    def test_project_config_requires_explicit_opt_in(self) -> None:
        self._cli()
        result = self._run(LAUNCHER, env={**self.env, "OPENCODE2_ALLOW_PROJECT_CONFIG": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["env"]["OPENCODE_DISABLE_PROJECT_CONFIG"])
        result = self._run(LAUNCHER, env={**self.env, "OPENCODE2_ALLOW_PROJECT_CONFIG": "anything"})
        self.assertEqual(result.returncode, 64)

    def test_blocks_shared_server_and_destructive_subcommands(self) -> None:
        self._cli()
        for args in (("--server", "http://localhost"), ("--server=http://localhost",), ("upgrade",), ("uninstall",), ("service", "stop"), ("--standalone",)):
            with self.subTest(args=args):
                self.assertEqual(self._run(LAUNCHER, *args).returncode, 64)

    def _mock_npm(self) -> None:
        mock_bin = Path(self.dir.name) / "mockbin"
        mock_bin.mkdir(exist_ok=True)
        npm = mock_bin / "npm"
        npm.write_text(MOCK_NPM)
        npm.chmod(0o755)
        self.env["PATH"] = f"{mock_bin}:{os.environ.get('PATH', '')}"

    def test_install_idempotent_and_leaves_v1_unchanged(self) -> None:
        self._mock_npm()
        old_v1 = self.home / ".config/opencode/opencode.json"
        old_v1.parent.mkdir(parents=True)
        old_v1.write_text("V1-sentinel")
        for _ in range(2):
            result = self._run(INSTALLER, "--install")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old_v1.read_text(), "V1-sentinel")
        self.assertEqual(self._run(self.home / ".local/bin/opencode2", "--help").returncode, 0)
        config = self.home / ".config/opencode-v2/opencode/opencode.json"
        self.assertEqual(json.loads(config.read_text())["mcp"]["servers"], {})
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_existing_nonidentical_launcher_is_rejected_before_npm(self) -> None:
        self._mock_npm()
        target = self.home / ".local/bin/opencode2"
        target.parent.mkdir(parents=True)
        target.write_text("foreign owner")
        result = self._run(INSTALLER, "--install")
        self.assertEqual(result.returncode, 73)
        self.assertEqual(target.read_text(), "foreign owner")
        self.assertFalse(self.bin.exists())

    def test_existing_config_symlink_is_rejected(self) -> None:
        self._mock_npm()
        existing_v1 = self.home / ".config/opencode/opencode.json"
        existing_v1.parent.mkdir(parents=True)
        existing_v1.write_text("V1")
        target = self.home / ".config/opencode-v2/opencode/opencode.json"
        target.parent.mkdir(parents=True)
        target.symlink_to(existing_v1)
        result = self._run(INSTALLER, "--install")
        self.assertEqual(result.returncode, 73)
        self.assertEqual(existing_v1.read_text(), "V1")
        self.assertFalse(self.bin.exists())


if __name__ == "__main__":
    unittest.main()
