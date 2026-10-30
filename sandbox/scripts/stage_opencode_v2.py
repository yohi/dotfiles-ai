#!/usr/bin/env python3
"""Stage an exported OpenCode v2 config into a local Docker Sandbox.

Default is read-only dry-run. --apply transfers an immutable-looking, uniquely
named copy into the sandbox workspace and verifies it; it never activates config.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NAMES = frozenset({"opencode.jsonc", "cli.json", "export-manifest.json"})
MAX_BYTES = 1024 * 1024
SANDBOX_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,61}[a-zA-Z0-9]$")
REMOTE_PARENT = str(Path("/home") / "agent" / "workspace")  # guest-only mountless path


class StageError(Exception):
    """Expected failure without exposing file contents or CLI stderr."""


def _regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise StageError("missing, non-regular, or symlinked bundle file: " + path.name)
    if path.stat().st_size > MAX_BYTES:
        raise StageError("bundle file exceeds size limit: " + path.name)
    return path.read_bytes()


def verify_bundle(directory: Path) -> str:
    """Validate content and hashes, without executing any exported config."""
    if directory.is_symlink() or not directory.is_dir():
        raise StageError("bundle directory must be a regular directory")
    if {item.name for item in directory.iterdir()} != NAMES:
        raise StageError("unexpected bundle file set")
    data = {name: _regular_bytes(directory / name) for name in NAMES}
    try:
        manifest = json.loads(data["export-manifest.json"])
        server = json.loads(data["opencode.jsonc"])
        tui = json.loads(data["cli.json"])
    except (ValueError, UnicodeDecodeError) as exc:
        raise StageError("bundle is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise StageError("invalid manifest")
    expected_keys = {"schema", "generator", "source", "source_sha256", "opencode_version",
                     "plugins_exported", "mcp_entries_exported", "artifacts_sha256"}
    if set(manifest) != expected_keys:
        raise StageError("unexpected manifest fields")
    if manifest.get("generator") != "v0.1" or manifest.get("source") != "apm.yml":
        raise StageError("unexpected export generator or source")
    if manifest.get("schema") != "dotfiles-ai/sandbox-export/v0":
        raise StageError("invalid manifest schema")
    if manifest.get("opencode_version") != "2.1.4":
        raise StageError("unapproved OpenCode version")
    source_hash = manifest.get("source_sha256")
    if not isinstance(source_hash, str) or re.fullmatch(r"[a-f0-9]{64}", source_hash) is None:
        raise StageError("invalid source digest")
    expected = {
        name: hashlib.sha256(data[name]).hexdigest()
        for name in ("opencode.jsonc", "cli.json")
    }
    if manifest.get("artifacts_sha256") != expected:
        raise StageError("artifact checksum mismatch")
    if manifest.get("plugins_exported") != 0 or manifest.get("mcp_entries_exported") != 0:
        raise StageError("exported plugins or MCP entries are forbidden")
    if not isinstance(server, dict) or set(server) != {"$schema", "shell", "snapshot", "plugins", "mcp"}:
        raise StageError("unexpected server config fields")
    if server["$schema"] != "https://opencode.ai/config.json":
        raise StageError("unexpected server config schema")
    if server["shell"] not in ("bash", "sh", "zsh") or type(server["shell"]) is not str:
        raise StageError("unapproved shell")
    if type(server["snapshot"]) is not bool or server["plugins"] != [] or server["mcp"] != {}:
        raise StageError("unapproved server config values")
    if not isinstance(tui, dict) or tui != {"$schema": "https://opencode.ai/v2/cli.json", "plugins": []}:
        raise StageError("unexpected TUI config")
    return hashlib.sha256(data["export-manifest.json"]).hexdigest()


def _run(command: list[str]) -> None:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageError("sandbox command could not complete") from exc
    if proc.returncode != 0:
        raise StageError("sandbox command failed (no config activated)")


def _check_source(root: Path, bundle: Path) -> None:
    exporter = root / "sandbox" / "scripts" / "prepare_opencode_v2.py"
    if exporter.is_symlink() or not exporter.is_file():
        raise StageError("missing trusted export generator")
    try:
        result = subprocess.run(
            [sys.executable, str(exporter), "--repo-root", str(root), "--out", str(bundle), "--check"],
            capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageError("export provenance check could not complete") from exc
    if result.returncode != 0:
        raise StageError("bundle does not match the current apm.yml SSOT")


def stage(bundle: Path, repo_root: Path, sandbox: str | None, apply: bool) -> None:
    if bundle.is_symlink():
        raise StageError("bundle path must not be a symlink")
    root = repo_root.resolve(strict=True)
    digest = verify_bundle(bundle)
    _check_source(root, bundle)
    if not apply:
        print("DRY_RUN_OK: verified source and snapshot; nothing transferred")
        return
    if not sandbox or not SANDBOX_RE.fullmatch(sandbox):
        raise StageError("--apply requires a valid local sandbox name")
    if shutil.which("sbx") is None:
        raise StageError("sbx CLI was not found")
    with tempfile.TemporaryDirectory(prefix="opencode-v2-stage-") as tmp:
        folder = Path(tmp) / ("sbx-config-" + digest[:16] + "-" + os.urandom(6).hex())
        folder.mkdir(mode=0o755)
        for name in sorted(NAMES):
            shutil.copyfile(bundle / name, folder / name)
            (folder / name).chmod(0o644)  # Non-secret output; guest agent may have another UID.
        remote = REMOTE_PARENT + "/" + folder.name
        # The VM owns this path, never a host mount in the intended configuration.
        _run(["sbx", "exec", sandbox, "sh", "-c",
              'test -d "$1" && test ! -L "$1" && test ! -e "$2" && test ! -L "$2"',
              "sh", REMOTE_PARENT, remote])
        _run(["sbx", "cp", str(folder), f"{sandbox}:{remote}"])
        verifier = Path(__file__).resolve(strict=True)
        # Verifier is executed from the sandbox agent's local Python interpreter.
        # Transfer separately to avoid smuggling a script in a supposedly data-only bundle.
        _run(["sbx", "cp", str(verifier), f"{sandbox}:{remote}/verify_snapshot.py"])
        _run(["sbx", "exec", sandbox, "python3", f"{remote}/verify_snapshot.py",
              "--verify-bundle", remote])
        print("STAGED_AND_VERIFIED: " + sandbox + ":" + remote)
        print("NOT_ACTIVATED: OpenCode settings were not modified")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify-bundle", type=Path, help="verify a staged bundle (guest operation)")
    p.add_argument("--bundle", type=Path, help="existing output from prepare_opencode_v2.py")
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--sandbox", help="local Docker Sandbox name (used only with --apply)")
    p.add_argument("--apply", action="store_true", help="explicitly copy and verify; never activate")
    args = p.parse_args(argv)
    try:
        if args.verify_bundle is not None:
            digest = verify_bundle(args.verify_bundle)
            print("VERIFY_OK: " + digest)
        else:
            if args.bundle is None:
                raise StageError("--bundle is required")
            stage(args.bundle, args.repo_root, args.sandbox, args.apply)
        return 0
    except (StageError, OSError) as exc:
        msg = str(exc) if isinstance(exc, StageError) else "filesystem operation failed"
        print("ERROR: " + msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
