#!/usr/bin/env python3
"""Prepare a separate OpenCode v2 launcher inside a mountless Sandbox.

Default: validation only. --write creates a NEW isolated runtime directory;
this script does not start OpenCode or modify user-wide configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

from stage_opencode_v2 import StageError, verify_bundle

WORKSPACE = Path("/home/agent/workspace")
PLUGINS = {
    "akane": ("@yohi/akane", "3.0.0-alpha.2", "dist/index.js"),
    "sibyl": ("@yohi/sibyl", "3.0.0-alpha.1", "dist/tui.js"),
}


def guest_path(path: Path, *, existing: bool) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise StageError("absolute guest paths without traversal are required")
    workspace = WORKSPACE.resolve(strict=existing)
    result = path.resolve(strict=existing)
    if result == workspace or not result.is_relative_to(workspace):
        raise StageError("path must be inside guest workspace")
    cursor = path
    while cursor != WORKSPACE and cursor != cursor.parent:
        if cursor.is_symlink():
            raise StageError("symlink paths are not accepted")
        cursor = cursor.parent
    if existing and not path.is_dir():
        raise StageError("expected a directory")
    return result


def local_plugin(kind: str, location: Path | None) -> str | None:
    if location is None:
        return None
    path = guest_path(location, existing=True)
    name, version, entry = PLUGINS[kind]
    meta = path / "package.json"
    target = path / entry
    if (meta.is_symlink() or not meta.is_file() or meta.stat().st_size > 65536
            or (path / "dist").is_symlink()
            or target.is_symlink() or not target.is_file()):
        raise StageError("invalid local plugin package")
    try:
        package = json.loads(meta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise StageError("invalid plugin metadata") from exc
    if (not isinstance(package, dict)
            or package.get("name") != name or package.get("version") != version):
        raise StageError("plugin identity/version mismatch")
    return str(path)


def new_file(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def prepare(
    bundle: Path,
    runtime: Path,
    binary: Path,
    akane: Path | None,
    sibyl: Path | None,
    *,
    write: bool,
) -> None:
    guest_path(bundle, existing=True)
    digest = verify_bundle(bundle)
    dest = guest_path(runtime, existing=False)
    if dest.exists() or dest.is_symlink():
        raise StageError("runtime exists; overwrite is forbidden")
    if not dest.parent.is_dir():
        raise StageError("runtime parent does not exist")
    if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise StageError("OpenCode binary is not executable")

    server = json.loads((bundle / "opencode.jsonc").read_text(encoding="utf-8"))
    client = json.loads((bundle / "cli.json").read_text(encoding="utf-8"))
    server_plugin = local_plugin("akane", akane)
    tui_plugin = local_plugin("sibyl", sibyl)
    server["plugins"] = [server_plugin] if server_plugin else []
    client["plugins"] = [tui_plugin] if tui_plugin else []

    if not write:
        print("DRY_RUN_OK: no runtime files created and no commands executed")
        print(f"PLUGINS: akane={bool(server_plugin)} sibyl={bool(tui_plugin)}")
        return

    previous_umask = os.umask(0o077)
    try:
        dest.mkdir(mode=0o700)
        xdg = dest / "xdg-config"
        for folder in (xdg, xdg / "opencode", dest / "xdg-data",
                       dest / "xdg-cache", dest / "workspace"):
            folder.mkdir(mode=0o700)
        server_path = xdg / "opencode" / "opencode.jsonc"
        cli_path = xdg / "opencode" / "cli.json"
        new_file(server_path, (json.dumps(server, indent=2) + "\n").encode(), 0o600)
        new_file(cli_path, (json.dumps(client, indent=2) + "\n").encode(), 0o600)

        quote = lambda p: shlex.quote(str(p))
        launcher = (
            "#!/bin/sh\nset -eu\n"
            f"cd {quote(dest / 'workspace')}\n"
            "exec env -i"
            f" HOME={quote(Path.home())}"
            " PATH=/usr/local/bin:/usr/bin:/bin"
            f" XDG_CONFIG_HOME={quote(xdg)}"
            f" XDG_DATA_HOME={quote(dest / 'xdg-data')}"
            f" XDG_CACHE_HOME={quote(dest / 'xdg-cache')}"
            f" {quote(binary)} \"$@\"\n"
        )
        run = dest / "run-opencode.sh"
        new_file(run, launcher.encode("utf-8"), 0o700)
        os.chmod(run, 0o700)
        receipt = {
            "schema": "dotfiles-ai/sandbox-runtime/v0",
            "source_manifest_sha256": digest,
            "server_sha256": hashlib.sha256(server_path.read_bytes()).hexdigest(),
            "cli_sha256": hashlib.sha256(cli_path.read_bytes()).hexdigest(),
            "akane": PLUGINS["akane"][1] if server_plugin else None,
            "sibyl": PLUGINS["sibyl"][1] if tui_plugin else None,
            "status": "prepared-not-executed",
        }
        new_file(dest / "runtime-receipt.json",
                 (json.dumps(receipt, indent=2) + "\n").encode(), 0o600)
    finally:
        os.umask(previous_umask)
    print("PREPARED_ONLY: " + str(dest / "run-opencode.sh"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--opencode-bin", type=Path, required=True)
    parser.add_argument("--akane", type=Path)
    parser.add_argument("--sibyl", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        prepare(args.bundle, args.runtime_dir, args.opencode_bin,
                args.akane, args.sibyl, write=args.write)
        return 0
    except (StageError, OSError, ValueError) as exc:
        msg = str(exc) if isinstance(exc, StageError) else "filesystem operation failed"
        print("ERROR: " + msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
