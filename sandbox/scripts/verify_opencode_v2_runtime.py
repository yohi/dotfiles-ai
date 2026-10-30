#!/usr/bin/env python3
"""Check a prepared OpenCode v2 guest runtime without exposing raw config.

Static validation is the default. --probe-cli explicitly runs a version and
merged-config probe inside the guest; it does NOT prove plugin setup or Sidebar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from stage_opencode_v2 import StageError, verify_bundle

WORKSPACE = Path.home() / "workspace"
PLUGIN_META = {
    "akane": ("@yohi/akane", "3.0.0-alpha.2", "dist/index.js"),
    "sibyl": ("@yohi/sibyl", "3.0.0-alpha.1", "dist/tui.js"),
}
MAX_BYTES = 1024 * 1024


def within_workspace(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise StageError("an absolute guest workspace path is required")
    root = WORKSPACE.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved == root or not resolved.is_relative_to(root):
        raise StageError("path is outside guest workspace")
    cursor = path
    while cursor != WORKSPACE and cursor != cursor.parent:
        if cursor.is_symlink():
            raise StageError("symlink in guest path")
        cursor = cursor.parent
    return resolved


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise StageError("missing or invalid runtime file")
    if path.stat().st_size > MAX_BYTES:
        raise StageError("runtime file is too large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise StageError("invalid runtime JSON") from exc
    if not isinstance(value, dict):
        raise StageError("runtime JSON must be an object")
    return value


def verify_plugin(path_text: str, kind: str) -> bool:
    target = within_workspace(Path(path_text))
    name, version, entry = PLUGIN_META[kind]
    package = read_json(target / "package.json")
    artifact = target / entry
    if (package.get("name") != name or package.get("version") != version
            or (target / "dist").is_symlink()
            or artifact.is_symlink() or not artifact.is_file()):
        raise StageError("plugin version or entrypoint mismatch")
    return True


def verify_runtime(bundle: Path, runtime: Path, *, require_both: bool) -> dict:
    within_workspace(bundle)
    runtime = within_workspace(runtime)
    if not runtime.is_dir():
        raise StageError("runtime directory is missing")
    snapshot_digest = verify_bundle(bundle)
    receipt_path = runtime / "runtime-receipt.json"
    receipt = read_json(receipt_path)
    if set(receipt) != {
        "schema", "source_manifest_sha256", "server_sha256", "cli_sha256",
        "akane", "sibyl", "status",
    }:
        raise StageError("runtime receipt fields changed")
    if (receipt.get("schema") != "dotfiles-ai/sandbox-runtime/v0"
            or receipt.get("status") != "prepared-not-executed"
            or receipt.get("source_manifest_sha256") != snapshot_digest):
        raise StageError("runtime receipt does not match staged snapshot")
    config_dir = runtime / "xdg-config" / "opencode"
    for relative in ("xdg-config", "xdg-config/opencode", "xdg-data", "xdg-cache", "workspace"):
        candidate = runtime / relative
        within_workspace(candidate)
        if not candidate.is_dir():
            raise StageError("missing or invalid isolated runtime directory")
    server_path = config_dir / "opencode.jsonc"
    cli_path = config_dir / "cli.json"
    server = read_json(server_path)
    cli = read_json(cli_path)
    for filename, key in ((server_path, "server_sha256"), (cli_path, "cli_sha256")):
        digest = hashlib.sha256(filename.read_bytes()).hexdigest()
        if receipt.get(key) != digest:
            raise StageError("runtime config changed after preparation")

    expected_server = read_json(bundle / "opencode.jsonc")
    expected_cli = read_json(bundle / "cli.json")
    if set(server) != set(expected_server) or set(cli) != set(expected_cli):
        raise StageError("unexpected runtime config keys")
    if {k: v for k, v in server.items() if k != "plugins"} != {
        k: v for k, v in expected_server.items() if k != "plugins"
    }:
        raise StageError("server snapshot fields unexpectedly changed")
    if {k: v for k, v in cli.items() if k != "plugins"} != {
        k: v for k, v in expected_cli.items() if k != "plugins"
    }:
        raise StageError("TUI snapshot fields unexpectedly changed")
    if server.get("mcp") != {}:
        raise StageError("server MCP is not empty")
    status: dict[str, bool] = {}
    for kind, value, config in (
        ("akane", receipt.get("akane"), server),
        ("sibyl", receipt.get("sibyl"), cli),
    ):
        plugins = config.get("plugins")
        if not isinstance(plugins, list) or len(plugins) > 1:
            raise StageError("unapproved plugin entries")
        if value is None:
            if plugins or require_both:
                raise StageError("required plugin missing")
            status[kind] = False
        else:
            if value != PLUGIN_META[kind][1] or len(plugins) != 1 or not isinstance(plugins[0], str):
                raise StageError("plugin configuration and receipt disagree")
            status[kind] = verify_plugin(plugins[0], kind)

    launcher = runtime / "run-opencode.sh"
    within_workspace(launcher)
    if (launcher.is_symlink() or not launcher.is_file()
            or launcher.stat().st_size > MAX_BYTES):
        raise StageError("missing or unsafe launcher")
    launcher_text = launcher.read_text(encoding="utf-8")
    if "exec env -i" not in launcher_text or "XDG_CONFIG_HOME=" not in launcher_text:
        raise StageError("launcher is not isolated")
    return {"snapshot_valid": True, "runtime_integrity": True,
            "akane_configured": status["akane"], "sibyl_configured": status["sibyl"]}


def probe_cli(runtime: Path, binary: Path, expected: dict) -> dict:
    """No model prompt; never emit the potentially sensitive raw CLI output."""
    runtime = within_workspace(runtime)
    for relative in ("xdg-config", "xdg-config/opencode", "xdg-data", "xdg-cache", "workspace"):
        within_workspace(runtime / relative)
    if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise StageError("OpenCode executable is invalid")
    guest_home = str(Path.home())
    env = {
        "HOME": guest_home,
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "TERM": "xterm-256color",
        "XDG_CONFIG_HOME": str(runtime / "xdg-config"),
        "XDG_DATA_HOME": str(runtime / "xdg-data"),
        "XDG_CACHE_HOME": str(runtime / "xdg-cache"),
    }

    def invoke(args: list[str]) -> str:
        try:
            result = subprocess.run(
                [str(binary), *args], cwd=runtime / "workspace", env=env,
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StageError("CLI probe failed to finish") from exc
        if result.returncode != 0 or len(result.stdout) > MAX_BYTES:
            raise StageError("CLI probe failed; output was intentionally suppressed")
        return result.stdout

    version = invoke(["--version"]).strip()
    if not re.fullmatch(r"(?:opencode\s+)?v?2\.1\.4", version):
        raise StageError("OpenCode version mismatch")
    raw = invoke(["debug", "config"])
    try:
        merged = json.loads(raw)
    except ValueError as exc:
        raise StageError("CLI debug config is not a JSON object") from exc
    if not isinstance(merged, dict):
        raise StageError("CLI debug config is not a JSON object")
    if merged.get("mcp", {}) != {}:
        raise StageError("unexpected active MCP configuration")
    configured_server = read_json(runtime / "xdg-config/opencode/opencode.jsonc")
    expected_plugins = configured_server["plugins"]
    effective = merged.get("plugins", [])
    if not isinstance(effective, list) or effective != expected_plugins:
        raise StageError("active Server plugin list differs from isolated config")
    return {"cli_version": "2.1.4", "merged_config_match": True,
            "server_plugins_configured": len(expected_plugins),
            "tui_plugin_setup_verified": False, "sidebar_render_verified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--require-both", action="store_true")
    parser.add_argument("--probe-cli", action="store_true",
                        help="explicitly execute --version and debug config")
    parser.add_argument("--opencode-bin", type=Path, help="required with --probe-cli")
    args = parser.parse_args(argv)
    try:
        summary = verify_runtime(args.bundle, args.runtime_dir, require_both=args.require_both)
        if args.probe_cli:
            if args.opencode_bin is None:
                raise StageError("--probe-cli requires --opencode-bin")
            summary.update(probe_cli(args.runtime_dir, args.opencode_bin, summary))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, StageError, ValueError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, StageError) else "unexpected local validation error"
        print("VALIDATION_FAILED: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
