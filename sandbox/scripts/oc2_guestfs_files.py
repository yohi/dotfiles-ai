from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import tarfile

MAX_SESSION_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_SESSION_ARCHIVE_ENTRIES = 100_000
MAX_SESSION_FILE_BYTES = 32 * 1024 * 1024
MAX_RECEIPT_BYTES = 16_384
MAX_MANIFEST_BYTES = 64 * 1024


def extract_regular_tar(data: bytes, destination: Path) -> bool:
    if len(data) > MAX_SESSION_ARCHIVE_BYTES:
        return False
    seen_files: set[Path] = set()
    total_bytes = 0
    try:
        with tarfile.open(fileobj=BytesIO(data), mode='r:') as archive:
            for index, member in enumerate(archive):
                if index >= MAX_SESSION_ARCHIVE_ENTRIES:
                    return False
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or '..' in relative.parts:
                    return False
                parts = tuple(part for part in relative.parts if part not in {'', '.'})
                if not parts:
                    if member.isdir():
                        continue
                    return False
                target = destination.joinpath(*parts)
                if not target.is_relative_to(destination) or member.mode & 0o7000:
                    return False
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                if not member.isreg() or member.size < 0 or member.size > MAX_SESSION_FILE_BYTES:
                    return False
                total_bytes += member.size
                if total_bytes > MAX_SESSION_ARCHIVE_BYTES or target in seen_files:
                    return False
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    return False
                with source:
                    content = source.read(member.size + 1)
                if len(content) != member.size:
                    return False
                mode = 0o700 if member.mode & 0o111 else 0o600
                write_new_file(target, content, mode)
                seen_files.add(target)
    except (OSError, tarfile.TarError, ValueError):
        return False
    return True


def find_repo_root(export_root: Path) -> Path | None:
    if ordinary_git_directory(export_root / '.git'):
        return export_root
    candidates = tuple(
        child for child in export_root.iterdir()
        if child.is_dir() and ordinary_git_directory(child / '.git')
    )
    return candidates[0] if len(candidates) == 1 else None


def ordinary_git_directory(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def write_receipt_pair(
    root: Path,
    workspace_id: str,
    generation: str,
    receipt_bytes: bytes,
    manifest_bytes: bytes,
) -> Path | None:
    receipt_dir = root / 'session-state' / workspace_id / generation
    try:
        receipt_dir.mkdir(mode=0o700, parents=True)
        receipt_path = receipt_dir / 'receipt.json'
        write_new_file(receipt_path, receipt_bytes, 0o600)
        write_new_file(receipt_dir / 'bundle.manifest.json', manifest_bytes, 0o600)
    except OSError:
        return None
    return receipt_path


def write_new_file(path: Path, content: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError('short private-file write')
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
