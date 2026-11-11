from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import stat

from oc2_workspace import (
    Manifest,
    WorkspaceError,
    _by_path,
    _read_regular,
    _validate_relative,
    snapshot,
)


def materialize(source: pathlib.Path, destination: pathlib.Path, manifest: Manifest,
                *, for_guest: bool = False) -> None:
    """Copy manifest-verified files into a new private snapshot directory."""
    if source.resolve(strict=True) != pathlib.Path(manifest.root):
        raise WorkspaceError('workspace manifest root mismatch')
    if _by_path(snapshot(source)) != _by_path(manifest):
        raise WorkspaceError('workspace changed after snapshot')
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise WorkspaceError('snapshot destination is not new and safe')
    directory_mode = 0o711 if for_guest else 0o700
    file_mode = 0o600
    destination.mkdir(mode=directory_mode)
    try:
        for entry in manifest.files:
            relative = _validate_relative(entry.path)
            data = _read_regular(source.joinpath(*relative.split('/')))
            if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
                raise WorkspaceError('workspace changed while snapshot was copied')
            target = destination.joinpath(*relative.split('/'))
            target.parent.mkdir(mode=directory_mode, parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  getattr(os, 'O_NOFOLLOW', 0), file_mode)
            with os.fdopen(descriptor, 'wb') as stream:
                _ = stream.write(data)
    except (OSError, WorkspaceError):
        shutil.rmtree(destination, ignore_errors=True)
        raise


def changes(baseline: Manifest, guest: pathlib.Path) -> tuple[str, ...]:
    """Return sorted paths whose guest content differs from the baseline."""
    after = _by_path(snapshot(guest))
    before = _by_path(baseline)
    return tuple(sorted(path for path in before.keys() | after.keys()
                        if before.get(path) != after.get(path)))


def apply_changes(host: pathlib.Path, guest: pathlib.Path, baseline: Manifest,
                  *, approved: bool, allow_deletions: bool = False) -> tuple[str, ...]:
    """Apply reviewed guest changes atomically, restoring Host files on failure."""
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
        _validate_relative(relative)
    deleted = tuple(path for path in changed if path not in after)
    if deleted and not allow_deletions:
        raise WorkspaceError('deletion approval is required')
    for relative in changed:
        target = host.joinpath(*relative.split('/'))
        for parent in (target, *target.parents):
            if parent == host:
                break
            if parent.is_symlink():
                raise WorkspaceError('host destination contains a symlink')
        if relative in before and _by_path(snapshot(host)).get(relative) != before[relative]:
            raise WorkspaceError('host workspace conflict; no files applied')
    originals: dict[str, bytes | None] = {}
    original_modes: dict[str, int] = {}
    prepared: dict[str, pathlib.Path] = {}
    contents: dict[str, bytes] = {}
    created_directories: set[pathlib.Path] = set()
    for relative in changed:
        target = host.joinpath(*relative.split('/'))
        source = guest.joinpath(*relative.split('/'))
        if relative in before:
            originals[relative] = _read_regular(target)
            original_modes[relative] = stat.S_IMODE(target.stat().st_mode)
        else:
            originals[relative] = None
        rollback = target.with_name(target.name + '.oc2-rollback')
        if rollback.exists() or rollback.is_symlink():
            raise WorkspaceError('temporary rollback destination already exists')
        if relative not in after:
            continue
        data = _read_regular(source)
        entry = after[relative]
        if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
            raise WorkspaceError('guest workspace changed during collection')
        temporary = target.with_name(target.name + '.oc2-new')
        if temporary.exists() or temporary.is_symlink():
            raise WorkspaceError('temporary apply destination already exists')
        contents[relative] = data
        prepared[relative] = temporary

    applied: list[str] = []
    try:
        for relative, temporary in prepared.items():
            target = host.joinpath(*relative.split('/'))
            missing = [parent for parent in target.parents
                       if parent != host and not parent.exists()]
            target.parent.mkdir(parents=True, exist_ok=True)
            created_directories.update(missing)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                _ = stream.write(contents[relative])
        for relative in changed:
            target = host.joinpath(*relative.split('/'))
            if relative in after:
                os.replace(prepared[relative], target)
            else:
                target.unlink(missing_ok=True)
            applied.append(relative)
    except (OSError, WorkspaceError) as exc:
        try:
            for relative in reversed(applied):
                target = host.joinpath(*relative.split('/'))
                original_bytes = originals[relative]
                if original_bytes is None:
                    target.unlink(missing_ok=True)
                else:
                    rollback = target.with_name(target.name + '.oc2-rollback')
                    descriptor = os.open(rollback, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
                    with os.fdopen(descriptor, 'wb') as stream:
                        os.fchmod(stream.fileno(), original_modes[relative])
                        _ = stream.write(original_bytes)
                    os.replace(rollback, target)
            for temporary in prepared.values():
                if temporary.exists() or temporary.is_symlink():
                    temporary.unlink()
            for directory in sorted(created_directories, key=lambda item: len(item.parts),
                                     reverse=True):
                directory.rmdir()
        except OSError as rollback_error:
            raise WorkspaceError('apply failed and Host rollback was incomplete') from rollback_error
        raise exc
    finally:
        for temporary in prepared.values():
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
    return changed
