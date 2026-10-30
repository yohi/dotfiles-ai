#!/usr/bin/env python3
"""Prepare a minimal OpenCode v2 config snapshot from the dotfiles-ai SSOT.

No sandbox provisioning, secrets export, network access, or host config writes.
Only the explicitly allowed scalar fields are read from apm.yml. No plugin,
provider, agent, MCP, environment, command, or credential objects are copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml


VERSION = "v0.1"
MAX_APM_BYTES = 2 * 1024 * 1024
FILES = ("opencode.jsonc", "cli.json", "export-manifest.json")


class ExportError(Exception):
    """A safe, non-sensitive export failure."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _read_apm(root: Path) -> tuple[str, bool, str]:
    source = root / "apm.yml"
    if source.is_symlink() or not source.is_file():
        raise ExportError("apm.yml must be a regular, non-symlink file")
    if source.stat().st_size > MAX_APM_BYTES:
        raise ExportError("apm.yml exceeds the input size limit")
    raw = source.read_bytes()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ExportError("apm.yml is not valid YAML") from exc
    if not isinstance(data, dict):
        raise ExportError("apm.yml must contain a mapping")
    shell = data.get("shell", "bash")
    snapshot = data.get("snapshot", True)
    if type(shell) is not str or shell not in {"bash", "sh", "zsh"}:
        raise ExportError("apm.yml shell is not approved")
    if type(snapshot) is not bool:
        raise ExportError("apm.yml snapshot must be a boolean")
    return shell, snapshot, hashlib.sha256(raw).hexdigest()


def _build_files(shell: str, snapshot: bool, apm_sha: str) -> dict[str, bytes]:
    # Strict positive selection: none of the other apm.yml values is serialized.
    server = {
        "$schema": "https://opencode.ai/config.json",
        "shell": shell,
        "snapshot": snapshot,
        "plugins": [],
        "mcp": {},
    }
    tui = {
        "$schema": "https://opencode.ai/v2/cli.json",
        "plugins": [],
    }
    generated = {
        "opencode.jsonc": _json_bytes(server),
        "cli.json": _json_bytes(tui),
    }
    manifest = {
        "schema": "dotfiles-ai/sandbox-export/v0",
        "generator": VERSION,
        "source": "apm.yml",
        "source_sha256": apm_sha,
        "opencode_version": "2.1.4",
        "plugins_enabled": False,
        "mcp_enabled": False,
        "artifacts_sha256": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(generated.items())
        },
    }
    generated["export-manifest.json"] = _json_bytes(manifest)
    return generated


def _validate_destination(root: Path, output: Path) -> None:
    # Refuse accidental writes into the source checkout or the user's live
    # OpenCode configuration. The destination is an independent staging area.
    if output.is_symlink():
        raise ExportError("output directory must not be a symlink")
    for candidate in (output, *output.parents):
        if candidate.is_symlink():
            raise ExportError("output path contains a symlink")
    actual = output.resolve()
    if actual == root or actual.is_relative_to(root):
        raise ExportError("output must be outside the source repository")
    home = Path.home().resolve()
    if actual == home / ".config" or actual.is_relative_to(home / ".config"):
        raise ExportError("output must not be under ~/.config")
    if actual == home / ".local" / "share" / "opencode" or actual.is_relative_to(
        home / ".local" / "share" / "opencode"
    ):
        raise ExportError("output must not be under OpenCode runtime data")


def _check(output: Path, generated: dict[str, bytes]) -> None:
    if not output.is_dir() or output.is_symlink():
        raise ExportError("check output directory is missing or unsafe")
    entries = {entry.name for entry in output.iterdir()}
    if entries != set(FILES):
        raise ExportError("output file set does not match expected manifest")
    for name, expected in generated.items():
        file = output / name
        if file.is_symlink() or not file.is_file() or file.read_bytes() != expected:
            raise ExportError("export mismatch: " + name)


def _create(output: Path, generated: dict[str, bytes]) -> None:
    if output.exists() or output.is_symlink():
        raise ExportError("output already exists (overwrite is prohibited)")
    if not output.parent.is_dir():
        raise ExportError("output parent directory must already exist")
    output.mkdir(mode=0o700)
    for name, data in generated.items():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(output / name, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="verify existing snapshot, never write")
    args = parser.parse_args(argv)

    try:
        if args.repo_root.is_symlink():
            raise ExportError("repository root must not be a symlink")
        root = args.repo_root.resolve(strict=True)
        _validate_destination(root, args.out)
        shell, snapshot, apm_sha = _read_apm(root)
        generated = _build_files(shell, snapshot, apm_sha)
        if args.check:
            _check(args.out, generated)
            print("CHECK_OK")
        else:
            _create(args.out, generated)
            print("EXPORT_OK: " + str(args.out))
        return 0
    except (OSError, ExportError) as exc:
        # Do not echo source YAML text or any unselected values.
        message = str(exc) if isinstance(exc, ExportError) else "filesystem operation failed"
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
