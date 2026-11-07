#!/usr/bin/env python3
"""Build a strictly selected, credential-free OpenCode v2 asset snapshot.

Only explicitly enumerated dotfiles-ai Markdown documents and a validated
TUI theme are exported. Commands with PR/review side effects, provider/MCP
configurations, credentials and unreviewed plugins are deliberately excluded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from oc2_workspace import contains_credential_material
from oc2_native import (
    ASSET_SOURCE_TO_TARGET,
    NativeConfigError,
    build_native_payload,
    parse_apm_native,
    validate_skill_frontmatter,
)

SCHEMA = "dotfiles-ai/oc2-assets/v1"
SOURCE_TO_TARGET = ASSET_SOURCE_TO_TARGET
THEME_SOURCE = "opencode/tui.jsonc"
THEME_TARGET = "theme.json"
NATIVE_TARGET = "native/oc2-native.json"
MAX_FILE = 65536
MAX_TOTAL = 512 * 1024
MAX_APM_BYTES = 2 * 1024 * 1024


class AssetError(ValueError):
    pass


def _regular_text(repo: Path, name: str) -> str:
    # Every source name comes from the immutable allowlist, never user input.
    source = repo / name
    directory = repo
    for part in Path(name).parts[:-1]:
        directory = directory / part
        if directory.is_symlink():
            raise AssetError("linked asset path: " + name)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_FILE:
        raise AssetError("missing, linked or oversized asset: " + name)
    try:
        return source.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise AssetError("asset is not valid UTF-8: " + name) from exc


def _safe_command(text: str) -> str:
    """Drop v1-only agent/model/tool frontmatter, preserve description/body."""
    if not text.startswith("---\n"):
        raise AssetError("command frontmatter is required")
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        raise AssetError("command frontmatter is incomplete")
    metadata = parts[0].splitlines()[1:]
    description = [line for line in metadata if line.startswith("description: ")]
    if len(description) != 1 or not parts[1].strip():
        raise AssetError("command description/body missing")
    return "---\n" + description[0] + "\n---\n" + parts[1]


def build(repo: Path) -> tuple[bytes, str]:
    files: dict[str, str] = {}
    apm = repo / "apm.yml"
    if apm.is_symlink() or not apm.is_file() or apm.stat().st_size > MAX_APM_BYTES:
        raise AssetError("apm.yml is missing, linked or oversized")
    try:
        native = parse_apm_native(apm.read_bytes(), require_oc2_assets=True)
    except NativeConfigError as exc:
        raise AssetError(str(exc)) from exc
    declared_sources = native.asset_sources
    for source in declared_sources:
        target = SOURCE_TO_TARGET[source]
        data = _regular_text(repo, source)
        if source.startswith("agent-commands/"):
            data = _safe_command(data)
        elif source.startswith("agent-skills/"):
            try:
                validate_skill_frontmatter(Path(source).parent.name, data)
            except NativeConfigError as exc:
                raise AssetError(str(exc)) from exc
        if contains_credential_material(data.encode("utf-8")):
            raise AssetError("selected asset appears to contain credential material: " + source)
        files[target] = data

    theme_source = _regular_text(repo, THEME_SOURCE)
    try:
        tui = json.loads(theme_source)
    except ValueError as exc:
        raise AssetError("invalid source TUI JSON") from exc
    theme = tui.get("theme") if isinstance(tui, dict) else None
    if not isinstance(theme, str) or not theme.isascii() or not (
            1 <= len(theme) <= 40 and
            all(c.islower() or c.isdigit() or c == "-" for c in theme)):
        raise AssetError("unapproved TUI theme")
    files[THEME_TARGET] = json.dumps({"name": theme}, sort_keys=True)

    files[NATIVE_TARGET] = json.dumps(
        build_native_payload(native), ensure_ascii=False, sort_keys=True,
    )
    expected = {SOURCE_TO_TARGET[source] for source in declared_sources} | {
        THEME_TARGET, NATIVE_TARGET,
    }
    if set(files) != expected:
        raise AssetError("unexpected asset file set")
    hashes = {name: hashlib.sha256(value.encode("utf-8")).hexdigest()
              for name, value in sorted(files.items())}
    payload = {"schema": SCHEMA, "files": files, "sha256": hashes}
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    if len(raw) > MAX_TOTAL:
        raise AssetError("asset snapshot exceeds size limit")
    return raw, hashlib.sha256(raw).hexdigest()


def write_new(destination: Path, raw: bytes) -> None:
    if destination.exists() or destination.is_symlink():
        raise AssetError("asset destination already exists")
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
