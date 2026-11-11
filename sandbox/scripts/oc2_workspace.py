#!/usr/bin/env python3
"""Create safe workspace manifests and explicitly apply reviewed changes."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
from dataclasses import dataclass
from typing import NoReturn

EXCLUDED_NAMES = frozenset({
    '.git', '.hg', '.svn', '.env', '.env.local', '.env.production',
    '.ssh', '.aws', '.azure', '.gnupg', '.docker', '.kube', '.config',
    '.opencode', '.claude', '.codex', '.npmrc', '.pypirc', '.netrc',
    'id_rsa', 'id_ed25519', 'credentials', 'secrets', 'token', 'tokens', 'node_modules',
    '.venv', '__pycache__',
})
MAX_FILE_BYTES = 64 * 1024 * 1024
SECRET_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rb'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
    rb'\bAKIA[0-9A-Z]{16}\b',
    rb'\bgh[pousr]_[A-Za-z0-9]{20,}\b',
    rb'\bsk-[A-Za-z0-9]{24,}\b',
    rb'(?i)\b(?:api[_-]?key|access[_-]?key|secret|password|token)\s*[:=]\s*["\']?[A-Za-z0-9_./+=-]{16,}',
))
SECRET_PLACEHOLDERS = (b'DO_NOT_EXPORT', b'EXAMPLE', b'PLACEHOLDER', b'DUMMY', b'FIXTURE')


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
    data = _read_regular(path)
    if _contains_credential(data):
        raise WorkspaceError('workspace file appears to contain credential material')
    return FileEntry(relative.as_posix(), len(data), hashlib.sha256(data).hexdigest())


def _contains_credential(data: bytes) -> bool:
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(data):
            value = match.group(0).upper()
            if not any(placeholder in value for placeholder in SECRET_PLACEHOLDERS):
                return True
    return False


def _read_regular(path: pathlib.Path) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise WorkspaceError('workspace file cannot be safely opened') from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise WorkspaceError('workspace contains a special or oversized file')
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise WorkspaceError('workspace file exceeds size limit')
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise WorkspaceError('workspace file changed while being read')
        return b''.join(chunks)
    finally:
        os.close(descriptor)


def _fail(message: str) -> NoReturn:
    raise WorkspaceError(message)


def _validate_relative(value: object) -> str:
    if not isinstance(value, str) or not value or '\x00' in value or '\\' in value:
        _fail('manifest path is invalid')
    relative = pathlib.PurePosixPath(value)
    if (relative.is_absolute() or any(part in ('', '.', '..') for part in value.split('/'))
            or relative.as_posix() != value or _excluded(relative)):
        _fail('manifest path is unsafe or excluded')
    return value


def decode_manifest(raw: bytes, root: pathlib.Path) -> Manifest:
    try:
        parsed: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError('workspace manifest is invalid') from exc
    payload = _string_mapping(parsed)
    if set(payload) != {'schema', 'files'} or \
            payload.get('schema') != 'dotfiles-ai/oc2-workspace/v1':
        _fail('workspace manifest schema is invalid')
    raw_entries = payload.get('files')
    if not isinstance(raw_entries, list):
        _fail('workspace manifest schema is invalid')
    entries: list[FileEntry] = []
    seen: set[str] = set()
    for raw_item in raw_entries:
        item = _string_mapping(raw_item)
        if set(item) != {'path', 'size', 'sha256'}:
            _fail('workspace manifest entry is invalid')
        relative = _validate_relative(item.get('path'))
        size = item.get('size')
        if relative in seen or type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
            _fail('workspace manifest entry is invalid')
        digest = item.get('sha256')
        if not isinstance(digest, str) or len(digest) != 64 or any(
                char not in '0123456789abcdef' for char in digest):
            _fail('workspace manifest digest is invalid')
        seen.add(relative)
        entries.append(FileEntry(relative, size, digest))
    if entries != sorted(entries, key=lambda entry: entry.path):
        _fail('workspace manifest entries are not ordered')
    return Manifest(str(root.resolve(strict=True)), tuple(entries))


def _string_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail('workspace manifest mapping is invalid')
    result: dict[str, object] = {}
    for key in value:
        if not isinstance(key, str):
            _fail('workspace manifest mapping key is invalid')
        result[key] = value[key]
    return result


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


from oc2_workspace_ops import apply_changes, changes, materialize  # noqa: E402, F401
