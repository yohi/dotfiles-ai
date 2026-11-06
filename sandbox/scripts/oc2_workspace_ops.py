from __future__ import annotations

import hashlib
import os
import pathlib
import shutil

from oc2_workspace import (
    FileEntry,
    Manifest,
    WorkspaceError,
    _by_path,
    _read_regular,
    _validate_relative,
    snapshot,
)


def materialize(source: pathlib.Path, destination: pathlib.Path, manifest: Manifest,
                *, for_guest: bool = False) -> None:
    if source.resolve(strict=True) != pathlib.Path(manifest.root):
        raise WorkspaceError('workspace manifest root mismatch')
    if _by_path(snapshot(source, profile=manifest.profile)) != _by_path(manifest):
        raise WorkspaceError('workspace changed after snapshot')
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise WorkspaceError('snapshot destination is not new and safe')
    directory_mode = 0o711 if for_guest else 0o700
    file_mode = 0o600
    destination.mkdir(mode=directory_mode)
    try:
        for entry in manifest.files:
            relative = _validate_relative(entry.path, manifest.profile)
            data = _read_regular(source.joinpath(*relative.split('/')))
            if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
                raise WorkspaceError('workspace changed while snapshot was copied')
            target = destination.joinpath(*relative.split('/'))
            _ = target.parent.mkdir(mode=directory_mode, parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  getattr(os, 'O_NOFOLLOW', 0), file_mode)
            with os.fdopen(descriptor, 'wb') as stream:
                _ = stream.write(data)
    except (OSError, WorkspaceError):
        shutil.rmtree(destination, ignore_errors=True)
        raise


def changes(baseline: Manifest, guest: pathlib.Path) -> tuple[str, ...]:
    after = _by_path(snapshot(guest, profile=baseline.profile))
    before = _by_path(baseline)
    return tuple(sorted(path for path in before.keys() | after.keys()
                        if before.get(path) != after.get(path)))


def apply_changes(host: pathlib.Path, guest: pathlib.Path, baseline: Manifest,
                  *, approved: bool, allow_deletions: bool = False) -> tuple[str, ...]:
    if not approved:
        raise WorkspaceError('explicit --apply is required')
    original = pathlib.Path(baseline.root)
    if host.resolve(strict=True) != original:
        raise WorkspaceError('host workspace identity mismatch')
    current = snapshot(host, profile=baseline.profile)
    if _by_path(current) != _by_path(baseline):
        raise WorkspaceError('host workspace conflict; no files applied')
    guest_manifest = snapshot(guest, profile=baseline.profile)
    before = _by_path(baseline)
    after = _by_path(guest_manifest)
    changed = tuple(sorted(path for path in before.keys() | after.keys()
                           if before.get(path) != after.get(path)))
    for relative in changed:
        _validate_relative(relative, baseline.profile)
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
        if relative in before and _by_path(
            snapshot(host, profile=baseline.profile),
        ).get(relative) != before[relative]:
            raise WorkspaceError('host workspace conflict; no files applied')
    for relative in changed:
        target = host.joinpath(*relative.split('/'))
        source = guest.joinpath(*relative.split('/'))
        if relative not in after:
            target.unlink(missing_ok=True)
            continue
        _ = target.parent.mkdir(parents=True, exist_ok=True)
        data = _read_regular(source)
        entry = after[relative]
        if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
            raise WorkspaceError('guest workspace changed during collection')
        temporary = target.with_name(target.name + '.oc2-new')
        if temporary.exists() or temporary.is_symlink():
            raise WorkspaceError('temporary apply destination already exists')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            _ = stream.write(data)
        os.replace(temporary, target)
    return changed
