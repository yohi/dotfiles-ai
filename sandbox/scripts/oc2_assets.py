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
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

from oc2_workspace import contains_credential_material
from oc2_native import (
    ASSET_SOURCE_TO_TARGET,
    NativeConfigError,
    build_native_payload,
    SUPERPOWERS_COMMIT,
    McpServerId,
    PluginId,
    parse_apm_native,
    parse_superpowers_lock,
    validate_skill_frontmatter,
)

SCHEMA = "dotfiles-ai/oc2-assets/v1"
SOURCE_TO_TARGET = ASSET_SOURCE_TO_TARGET
THEME_SOURCE = "opencode/tui.jsonc"
THEME_TARGET = "theme.json"
NATIVE_TARGET = "native/oc2-native.json"
PLUGIN_PREFIX = "plugins/superpowers/"
PLUGIN_META_TARGET = "metadata/superpowers-plugin.json"
MCP_SERVER_SOURCE = "sandbox/scripts/oc2_local_mcp.py"
MCP_SERVER_TARGET = "mcp/oc2_local_mcp.py"
MAX_FILE = 65536
MAX_TOTAL = 512 * 1024
MAX_APM_BYTES = 2 * 1024 * 1024
MAX_PLUGIN_FILES = 256
RUNTIME_IMPORTS = frozenset({'@opencode-ai/plugin', '@opencode-ai/sdk'})
IMPORT_SPECIFIER = re.compile(
    r'''(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)['"]([^'"]+)['"]''',
)


class AssetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PluginFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class PluginArtifact:
    source_commit: str
    files: tuple[PluginFile, ...]


def _git_output(directory: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ['git', '-C', str(directory), *arguments],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssetError('NOT_AVAILABLE: local Plugin checkout cannot be verified') from exc
    if result.returncode != 0:
        raise AssetError('NOT_AVAILABLE: local Plugin checkout cannot be verified')
    return result.stdout


def _safe_plugin_path(source: Path) -> None:
    path = source.absolute()
    while path != path.parent:
        if path.is_symlink():
            raise AssetError('NOT_AVAILABLE: local Plugin checkout is symlinked')
        path = path.parent
    if not source.is_dir() or (source / '.git').is_symlink() or not (source / '.git').is_dir():
        raise AssetError('NOT_AVAILABLE: local Plugin Git checkout is missing')


def _resolve_plugin_import(importer: str, specifier: str, tracked: set[str]) -> str:
    base = PurePosixPath(importer).parent
    requested = PurePosixPath(os.path.normpath(str(base / specifier)))
    if requested.is_absolute() or '..' in requested.parts:
        raise AssetError('NOT_AVAILABLE: local Plugin import escapes its checkout')
    candidates = [str(requested)]
    if not requested.suffix:
        candidates.extend(str(requested) + ext for ext in ('.js', '.mjs', '.cjs', '.json'))
        candidates.append(str(requested / 'index.js'))
    for candidate in candidates:
        if candidate in tracked:
            return candidate
    raise AssetError('NOT_AVAILABLE: local Plugin dependency is missing')


def resolve_superpowers_plugin(repo: Path, source: Path | None) -> PluginArtifact:
    """Verify and collect the fixed Superpowers OpenCode Plugin from local Git."""
    if source is None:
        raise AssetError('NOT_AVAILABLE: local Superpowers Plugin checkout is absent')
    lock_path = repo / 'apm.lock.yaml'
    if (lock_path.is_symlink() or not lock_path.is_file()
            or lock_path.stat().st_size > MAX_APM_BYTES):
        raise AssetError('NOT_AVAILABLE: APM Plugin lock is unavailable')
    try:
        lock_commit = parse_superpowers_lock(lock_path.read_bytes())
    except (OSError, NativeConfigError) as exc:
        raise AssetError('NOT_AVAILABLE: APM Plugin lock does not match the pin') from exc
    if lock_commit != SUPERPOWERS_COMMIT:
        raise AssetError('NOT_AVAILABLE: APM Plugin lock does not match the pin')

    _safe_plugin_path(source)
    origin = _git_output(source, 'remote', 'get-url', 'origin').strip()
    if origin not in {
        'https://github.com/obra/superpowers',
        'https://github.com/obra/superpowers.git',
        'git@github.com:obra/superpowers',
        'git@github.com:obra/superpowers.git',
    }:
        raise AssetError('NOT_AVAILABLE: local Plugin repository origin is not allowlisted')
    if _git_output(source, 'rev-parse', 'HEAD').strip() != lock_commit:
        raise AssetError('NOT_AVAILABLE: local Plugin commit does not match APM lock')
    if _git_output(source, 'status', '--porcelain', '--untracked-files=all').strip():
        raise AssetError('NOT_AVAILABLE: local Plugin checkout is not clean')
    tracked = set(_git_output(source, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines())
    if (not tracked or len(tracked) > MAX_PLUGIN_FILES or 'index.js' not in tracked
            or any(not path or '\\' in path or path.startswith('/') or '..' in path.split('/')
                   for path in tracked)):
        raise AssetError('NOT_AVAILABLE: local Plugin tracked file set is invalid')

    required = {'index.js'}
    if 'package.json' in tracked:
        required.add('package.json')
    pending = ['index.js']
    while pending:
        current = pending.pop()
        local_file = source / current
        if local_file.is_symlink() or not local_file.is_file() or local_file.stat().st_size > MAX_FILE:
            raise AssetError('NOT_AVAILABLE: required local Plugin file is invalid')
        try:
            text = local_file.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            raise AssetError('NOT_AVAILABLE: required local Plugin file is unreadable') from exc
        for specifier in IMPORT_SPECIFIER.findall(text):
            if specifier.startswith('./') or specifier.startswith('../'):
                resolved = _resolve_plugin_import(current, specifier, tracked)
                if resolved not in required:
                    required.add(resolved)
                    pending.append(resolved)
            elif specifier.startswith('node:') or specifier in RUNTIME_IMPORTS:
                continue
            else:
                raise AssetError('NOT_AVAILABLE: local Plugin has an unbundled dependency')

    if len(required) > MAX_PLUGIN_FILES:
        raise AssetError('NOT_AVAILABLE: local Plugin dependency set is oversized')
    files: list[PluginFile] = []
    for relative in sorted(required):
        local_file = source / relative
        if local_file.is_symlink() or not local_file.is_file() or local_file.stat().st_size > MAX_FILE:
            raise AssetError('NOT_AVAILABLE: required local Plugin file is invalid')
        local_bytes = local_file.read_bytes()
        committed_text = _git_output(source, 'show', 'HEAD:' + relative)
        committed_bytes = committed_text.encode('utf-8')
        if local_bytes != committed_bytes:
            raise AssetError('NOT_AVAILABLE: local Plugin file differs from pinned commit')
        files.append(PluginFile(relative, local_bytes, hashlib.sha256(local_bytes).hexdigest()))
    return PluginArtifact(lock_commit, tuple(files))


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


def build(
    repo: Path,
    *,
    verification_only: bool = False,
    plugin_dir: Path | None = None,
) -> tuple[bytes, str]:
    files: dict[str, str] = {}
    apm = repo / "apm.yml"
    if apm.is_symlink() or not apm.is_file() or apm.stat().st_size > MAX_APM_BYTES:
        raise AssetError("apm.yml is missing, linked or oversized")
    try:
        native = parse_apm_native(
            apm.read_bytes(),
            require_oc2_assets=True,
            verification_only=verification_only,
        )
    except NativeConfigError as exc:
        raise AssetError(str(exc)) from exc
    if plugin_dir is not None and not verification_only:
        raise AssetError("Plugin source is accepted only in verification mode")
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

    artifact: PluginArtifact | None = None
    if verification_only:
        artifact = resolve_superpowers_plugin(repo, plugin_dir)
        plugin_hashes: dict[str, str] = {}
        for item in artifact.files:
            target = PLUGIN_PREFIX + item.path
            try:
                text = item.content.decode("utf-8")
            except UnicodeError as exc:
                raise AssetError("NOT_AVAILABLE: local Plugin file is not UTF-8") from exc
            files[target] = text
            plugin_hashes[target] = item.sha256
        mcp_source = _regular_text(repo, MCP_SERVER_SOURCE)
        if contains_credential_material(mcp_source.encode("utf-8")):
            raise AssetError("local MCP source appears to contain credential material")
        files[MCP_SERVER_TARGET] = mcp_source
        files[PLUGIN_META_TARGET] = json.dumps({
            "schema": "dotfiles-ai/oc2-plugin/v1",
            "source": "obra/superpowers",
            "commit": artifact.source_commit,
            "entrypoint": PLUGIN_PREFIX + "index.js",
            "files": plugin_hashes,
        }, ensure_ascii=False, sort_keys=True)

    files[NATIVE_TARGET] = json.dumps(
        build_native_payload(native), ensure_ascii=False, sort_keys=True,
    )
    expected = {SOURCE_TO_TARGET[source] for source in declared_sources} | {
        THEME_TARGET, NATIVE_TARGET,
    }
    if verification_only and artifact is not None:
        expected |= {MCP_SERVER_TARGET, PLUGIN_META_TARGET}
        expected |= {PLUGIN_PREFIX + item.path for item in artifact.files}
    elif verification_only:
        raise AssetError('NOT_AVAILABLE: local Superpowers Plugin artifact is absent')
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
