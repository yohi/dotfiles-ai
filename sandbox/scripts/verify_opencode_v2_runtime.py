#!/usr/bin/env python3
"""Read-only verification for a prepared OpenCode v2 Sandbox runtime.

Static validation is NOT proof that plugins loaded or Sidebar rendered.
--probe-version invokes only the generated launcher's --version command.
No credentials, plugin code, model prompts, network policy, or project sources
are intentionally read, written, or transferred by this verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from stage_opencode_v2 import StageError, verify_bundle

EXPECTED = {
    "akane": ("@yohi/akane", "3.0.0-alpha.2", "dist/index.js"),
    "sibyl": ("@yohi/sibyl", "3.0.0-alpha.1", "dist/tui.js"),
}
WORKSPACE = Path("/home/agent/workspace")


def _workspace_dir(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts or path.is_symlink():
        raise StageError("invalid workspace directory")
    try:
        workspace = WORKSPACE.resolve(strict=True)
        if not path.is_relative_to(WORKSPACE) or path == WORKSPACE:
            raise StageError("invalid workspace directory")
        canonical = path.resolve(strict=True)
        if not canonical.is_relative_to(workspace) or canonical == workspace:
            raise StageError("invalid workspace directory")
        if canonical != path or not path.is_dir():
            raise StageError("invalid workspace directory")
    except OSError as exc:
        raise StageError("invalid workspace directory") from exc
    return canonical


def _safe_file(path: Path, limit: int = 65536) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise StageError("missing, linked, or oversized runtime file")
    return path.read_bytes()


def _json_file(path: Path) -> dict:
    try:
        value = json.loads(_safe_file(path))
    except (ValueError, UnicodeError) as exc:
        raise StageError("unreadable runtime JSON") from exc
    if not isinstance(value, dict):
        raise StageError("runtime JSON must be an object")
    return value


def _pinned_plugin(entry: str, kind: str) -> bool:
    if not isinstance(entry, str):
        raise StageError("unexpected plugin registration type")
    folder = _workspace_dir(Path(entry))
    name, version, main = EXPECTED[kind]
    package = _json_file(folder / "package.json")
    if package.get("name") != name or package.get("version") != version:
        raise StageError("plugin package name/version mismatch")
    if not (folder / main).is_file() or (folder / "dist").is_symlink() or (folder / main).is_symlink():
        raise StageError("missing or linked plugin entry")
    exports = package.get("exports")
    if not isinstance(exports, dict):
        raise StageError("package exports missing")
    selected = exports.get("." if kind == "akane" else "./tui")
    if kind == "akane":
        valid = selected == "./dist/index.js" or (
            isinstance(selected, dict) and selected.get("import") == "./dist/index.js"
        )
    else:
        valid = isinstance(selected, dict) and selected.get("import") == "./dist/tui.js"
    if not valid:
        raise StageError("plugin export is not the expected entrypoint")
    return True


def verify(bundle: Path, runtime: Path) -> dict[str, object]:
    source = _workspace_dir(bundle)
    target = _workspace_dir(runtime)
    source_hash = verify_bundle(source)
    config = target / "xdg-config" / "opencode"
    _workspace_dir(config)
    server_file = config / "opencode.jsonc"
    tui_file = config / "cli.json"
    server = _json_file(server_file)
    tui = _json_file(tui_file)
    receipt = _json_file(target / "runtime-receipt.json")
    if set(receipt) != {
        "schema", "source_manifest_sha256", "server_sha256", "cli_sha256",
        "akane", "sibyl", "status",
    }:
        raise StageError("runtime receipt fields mismatch")
    if receipt.get("schema") != "dotfiles-ai/sandbox-runtime/v0":
        raise StageError("unrecognized runtime receipt")
    if receipt.get("source_manifest_sha256") != source_hash:
        raise StageError("source snapshot mismatch")
    if receipt.get("status") != "prepared-not-executed":
        raise StageError("unexpected runtime status")
    for key, path in (("server_sha256", server_file), ("cli_sha256", tui_file)):
        if receipt.get(key) != hashlib.sha256(_safe_file(path)).hexdigest():
            raise StageError("runtime config hash mismatch")
    if set(server) != {"$schema", "shell", "snapshot", "plugins", "mcp"}:
        raise StageError("unexpected server config keys")
    if set(tui) != {"$schema", "plugins"}:
        raise StageError("unexpected TUI config keys")
    if server.get("$schema") != "https://opencode.ai/config.json":
        raise StageError("unrecognized OpenCode server schema")
    if tui.get("$schema") != "https://opencode.ai/v2/cli.json":
        raise StageError("unrecognized OpenCode client schema")
    if server.get("mcp") != {} or type(server.get("snapshot")) is not bool:
        raise StageError("unsafe server settings")
    if type(server.get("shell")) is not str or server["shell"] not in {"bash", "sh", "zsh"}:
        raise StageError("unapproved shell")

    server_plugins = server.get("plugins")
    tui_plugins = tui.get("plugins")
    if not isinstance(server_plugins, list) or not isinstance(tui_plugins, list):
        raise StageError("invalid plugin lists")
    if len(server_plugins) != 1 or len(tui_plugins) != 1:
        raise StageError("both pinned plugins must be explicitly configured")
    _pinned_plugin(server_plugins[0], "akane")
    _pinned_plugin(tui_plugins[0], "sibyl")
    if receipt.get("akane") != EXPECTED["akane"][1] or receipt.get("sibyl") != EXPECTED["sibyl"][1]:
        raise StageError("receipt is missing pinned plugin versions")

    launcher = target / "run-opencode.sh"
    launch_bytes = _safe_file(launcher, limit=8192)
    launch_text = launch_bytes.decode("utf-8")
    if not launch_text.startswith("#!/bin/sh\nset -eu\n") or "exec env -i" not in launch_text:
        raise StageError("launcher is not environment-isolated")
    for marker in ("XDG_CONFIG_HOME=", "XDG_DATA_HOME=", "XDG_CACHE_HOME=", '"$@"'):
        if marker not in launch_text:
            raise StageError("launcher missing isolation controls")
    if f"XDG_CONFIG_HOME={config.parent}" not in launch_text:
        raise StageError("launcher does not reference the prepared config path")

    return {
        "status": "STATIC_VERIFIED_RUNTIME_UNPROVEN",
        "server_registration": "akane@3.0.0-alpha.2",
        "tui_registration": "sibyl@3.0.0-alpha.1",
        "source_manifest_sha256": source_hash,
        "runtime_receipt_sha256": hashlib.sha256(_safe_file(target / "runtime-receipt.json")).hexdigest(),
    }


def probe_version(runtime: Path) -> None:
    launcher = runtime / "run-opencode.sh"
    try:
        # stdout/stderr are held in memory; do not echo upstream errors or secrets.
        process = subprocess.run(
            [str(launcher), "--version"], capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageError("OpenCode --version probe did not complete") from exc
    if process.returncode != 0 or re.search(rb"\bv?2\.1\.4\b", process.stdout) is None:
        raise StageError("OpenCode did not report the pinned v2.1.4 version")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--probe-version", action="store_true", help="execute the isolated --version only")
    args = parser.parse_args(argv)
    try:
        result = verify(args.bundle, args.runtime_dir)
        if args.probe_version:
            probe_version(args.runtime_dir)
            result["version_probe"] = "OPEN_CODE_2_1_4_CONFIRMED"
        print(json.dumps(result, sort_keys=True))
        return 0
    except (StageError, OSError, UnicodeError, ValueError) as exc:
        message = str(exc) if isinstance(exc, StageError) else "runtime verification failed"
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
