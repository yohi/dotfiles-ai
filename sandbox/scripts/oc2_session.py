#!/usr/bin/env python3
"""Persist local OC2 transfer receipts without storing credentials."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
from dataclasses import dataclass

from oc2_workspace import Manifest, WorkspaceError, decode_manifest

MAX_RECEIPT_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class Session:
    directory: pathlib.Path
    sandbox: str
    remote: str
    manifest: Manifest
    collected: bool
    applied: bool


def session_directory(state_root: pathlib.Path, workspace: pathlib.Path) -> pathlib.Path:
    root = workspace.resolve(strict=True)
    state = state_root.expanduser().absolute()
    if state.is_relative_to(root) or state == root:
        raise WorkspaceError('OC2 state directory must be outside the project workspace')
    for parent in (state, *state.parents):
        if parent.is_symlink():
            raise WorkspaceError('OC2 state path contains a symlink')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    key = hashlib.sha256(os.fsencode(root)).hexdigest()[:32]
    return state / key


def create(state_root: pathlib.Path, sandbox: str, remote: str,
           manifest: Manifest) -> Session:
    directory = session_directory(state_root, pathlib.Path(manifest.root))
    directory.mkdir(mode=0o700)
    receipt = {
        'schema': 'dotfiles-ai/oc2-session/v1',
        'workspace': manifest.root,
        'sandbox': sandbox,
        'remote': remote,
        'manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest(),
        'collected': False,
        'applied': False,
    }
    _write_new(directory / 'baseline.json', manifest.encode())
    _write_new(directory / 'receipt.json', _encoded(receipt))
    return Session(directory, sandbox, remote, manifest, False, False)


def load(state_root: pathlib.Path, workspace: pathlib.Path) -> Session:
    directory = session_directory(state_root, workspace)
    receipt_file = _read_regular(directory / 'receipt.json')
    baseline_raw = _read_regular(directory / 'baseline.json')
    try:
        receipt = json.loads(receipt_file)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError('OC2 transfer receipt is invalid') from exc
    expected = {'schema', 'workspace', 'sandbox', 'remote', 'manifest_sha256',
                'collected', 'applied'}
    if not isinstance(receipt, dict) or set(receipt) != expected or \
            receipt.get('schema') != 'dotfiles-ai/oc2-session/v1':
        raise WorkspaceError('OC2 transfer receipt schema is invalid')
    root = workspace.resolve(strict=True)
    if receipt['workspace'] != str(root):
        raise WorkspaceError('OC2 receipt workspace mismatch')
    if not isinstance(receipt['sandbox'], str) or \
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9]', receipt['sandbox']) is None:
        raise WorkspaceError('OC2 receipt Sandbox identity is invalid')
    if not isinstance(receipt['remote'], str) or \
            re.fullmatch(r'/home/agent/workspace/oc2/projects/[a-f0-9]{32}', receipt['remote']) is None:
        raise WorkspaceError('OC2 receipt project path is invalid')
    if type(receipt['collected']) is not bool or type(receipt['applied']) is not bool:
        raise WorkspaceError('OC2 receipt state is invalid')
    manifest = decode_manifest(baseline_raw, root)
    if hashlib.sha256(manifest.encode()).hexdigest() != receipt['manifest_sha256']:
        raise WorkspaceError('OC2 baseline manifest digest mismatch')
    if receipt['collected'] and not (directory / 'collected').is_dir():
        raise WorkspaceError('OC2 collection is missing')
    return Session(directory, receipt['sandbox'], receipt['remote'], manifest,
                   receipt['collected'], receipt['applied'])


def update(session: Session, *, collected: bool | None = None,
           applied: bool | None = None) -> Session:
    receipt_path = session.directory / 'receipt.json'
    try:
        data = json.loads(_read_regular(receipt_path))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError('OC2 transfer receipt is invalid') from exc
    if collected is not None:
        data['collected'] = collected
    if applied is not None:
        data['applied'] = applied
    temp = session.directory / 'receipt.json.new'
    _write_new(temp, _encoded(data))
    os.replace(temp, receipt_path)
    return Session(session.directory, session.sandbox, session.remote,
                   session.manifest,
                   data['collected'], data['applied'])


def _encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _write_new(path: pathlib.Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)


def _read_regular(path: pathlib.Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise WorkspaceError('OC2 receipt file is missing or unsafe')
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECEIPT_BYTES:
            raise WorkspaceError('OC2 receipt file is not regular')
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        result = b''.join(chunks)
        if len(result) > MAX_RECEIPT_BYTES:
            raise WorkspaceError('OC2 receipt file exceeds size limit')
        return result
    finally:
        os.close(descriptor)
