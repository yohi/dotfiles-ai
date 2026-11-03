#!/usr/bin/env python3
"""Create safe workspace manifests and explicitly apply reviewed changes."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
from dataclasses import dataclass

EXCLUDED_NAMES = frozenset({
    '.git', '.hg', '.svn', '.env', '.env.local', '.env.production',
    '.ssh', '.aws', '.azure', '.config', '.opencode', '.claude', '.codex',
    'id_rsa', 'id_ed25519', 'credentials', 'secrets', 'token', 'tokens', 'node_modules',
    '.venv', '__pycache__',
})
MAX_FILE_BYTES = 64 * 1024 * 1024


class WorkspaceError(Exception):
    """A workspace operation failed closed without exposing file contents."""


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Manifest:
    root: str
    files: tuple[FileEntry, ...]

    def encode(self) -> bytes:
        """Return deterministic metadata; file contents are never included."""
        payload = {
            'schema': 'dotfiles-ai/oc2-workspace/v1',
            'files': [{'path': item.path, 'size': item.size, 'sha256': item.sha256}
                      for item in self.files],
        }
        return (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _excluded(relative: pathlib.PurePosixPath) -> bool:
    return any(part in EXCLUDED_NAMES or part.startswith('.env')
               or any(term in part.lower() for term in ('secret', 'credential', 'token'))
               or part.endswith(('.pem', '.key', '.p12', '.pfx')) for part in relative.parts)


def _safe_file(path: pathlib.Path, relative: pathlib.PurePosixPath) -> FileEntry:
    if relative.is_absolute() or '..' in relative.parts or '\\' in relative.as_posix():
        raise WorkspaceError('unsafe workspace path')
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FILE_BYTES:
        raise WorkspaceError('workspace contains a special or oversized file')
    data = path.read_bytes()
    return FileEntry(relative.as_posix(), len(data), hashlib.sha256(data).hexdigest())


def snapshot(root: pathlib.Path) -> Manifest:
    """Hash included files after rejecting symlinks and special entries."""
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError('workspace root must be a real directory')
    base = root.resolve(strict=True)
    entries: list[FileEntry] = []
    def fail_walk(error: OSError) -> None:
        raise WorkspaceError('workspace cannot be read safely') from error

    for current, directories, filenames in os.walk(base, followlinks=False, onerror=fail_walk):
        current_path = pathlib.Path(current)
        retained: list[str] = []
        for name in directories:
            candidate = current_path / name
            rel = pathlib.PurePosixPath(candidate.relative_to(base).as_posix())
            if candidate.is_symlink():
                raise WorkspaceError('workspace contains a symlink')
            if not _excluded(rel):
                retained.append(name)
        directories[:] = retained
        for name in filenames:
            candidate = current_path / name
            rel = pathlib.PurePosixPath(candidate.relative_to(base).as_posix())
            if candidate.is_symlink():
                raise WorkspaceError('workspace contains a symlink')
            if not _excluded(rel):
                entries.append(_safe_file(candidate, rel))
    entries.sort(key=lambda item: item.path)
    return Manifest(str(base), tuple(entries))


def _by_path(manifest: Manifest) -> dict[str, FileEntry]:
    return {item.path: item for item in manifest.files}


def changes(baseline: Manifest, guest: pathlib.Path) -> tuple[str, ...]:
    """Return changed guest paths relative to the transfer baseline."""
    after = _by_path(snapshot(guest))
    before = _by_path(baseline)
    return tuple(sorted(path for path in before.keys() | after.keys()
                        if before.get(path) != after.get(path)))


def apply_changes(host: pathlib.Path, guest: pathlib.Path, baseline: Manifest,
                  *, approved: bool) -> tuple[str, ...]:
    """Apply only explicitly approved guest changes when host baseline is intact."""
    if not approved:
        raise WorkspaceError('explicit --apply is required')
    original = pathlib.Path(baseline.root)
    if host.resolve(strict=True) != original:
        raise WorkspaceError('host workspace identity mismatch')
    current = snapshot(host)
    if _by_path(current) != _by_path(baseline):
        raise WorkspaceError('host workspace conflict; no files applied')
    guest_manifest = snapshot(guest)
    before = _by_path(baseline)
    after = _by_path(guest_manifest)
    changed = tuple(sorted(path for path in before.keys() | after.keys()
                           if before.get(path) != after.get(path)))
    for relative in changed:
        rel = pathlib.PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts or _excluded(rel):
            raise WorkspaceError('change contains a forbidden path')
    for relative in changed:
        target = host.joinpath(*pathlib.PurePosixPath(relative).parts)
        source = guest.joinpath(*pathlib.PurePosixPath(relative).parts)
        if relative not in after:
            if target.exists() or target.is_symlink():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in (target.parent, *target.parent.parents)
               if parent == host or parent.is_relative_to(host)):
            raise WorkspaceError('host destination contains a symlink')
        temporary = target.with_name(target.name + '.oc2-new')
        if temporary.exists() or temporary.is_symlink():
            raise WorkspaceError('temporary apply destination already exists')
        shutil.copyfile(source, temporary, follow_symlinks=False)
        os.replace(temporary, target)
    return changed
