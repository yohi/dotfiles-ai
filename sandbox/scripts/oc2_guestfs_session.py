from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import HostDiskIdentity, HostVmIdentity
    from sandbox.scripts.oc2_offline_preservation import (
        FilesystemState,
        OfflinePreservationEvidence,
    )
    from sandbox.scripts.oc2_offline_preserver import DiskHashes, OfflinePreservationConfig
    from sandbox.scripts.oc2_guestfs_files import write_new_file
    from sandbox.scripts.oc2_slice_b_git import (
        GitBaseline,
        SliceBGitRejected,
        _git,
        admit_clean_repo,
    )
    from sandbox.scripts.oc2_slice_b_session import (
        SliceBSessionError,
        VerifiedGuestAuthority,
        is_verified_guest_authority,
        verify_guest_authority,
        verify_session_receipt,
    )
else:
    from oc2_host_control import HostDiskIdentity, HostVmIdentity
    from oc2_offline_preservation import FilesystemState, OfflinePreservationEvidence
    from oc2_offline_preserver import DiskHashes, OfflinePreservationConfig
    from oc2_guestfs_files import write_new_file
    from oc2_slice_b_git import GitBaseline, SliceBGitRejected, _git, admit_clean_repo
    from oc2_slice_b_session import (
        SliceBSessionError,
        VerifiedGuestAuthority,
        is_verified_guest_authority,
        verify_guest_authority,
        verify_session_receipt,
    )


@dataclass(frozen=True, slots=True)
class GitInspection:
    root: Path
    branch_ref: str
    head_oid: str
    tree_oid: str
    object_format: str
    index_sha256: str
    worktree_sha256: str
    tracked_file_count: int


class SessionGitInspector(Protocol):
    def __call__(self, root: Path) -> GitInspection | None: ...


def inspect_clean_session_git(root: Path) -> GitInspection | None:
    """Inspect a clean repository and count paths recorded in its verified Git Index.

    Returns None when admission, Index enumeration, or consistency checks fail.
    Ignored untracked worktree files are not included in the tracked count.
    """
    try:
        baseline = admit_clean_repo(root)
    except (OSError, SliceBGitRejected, UnicodeError):
        return None
    try:
        index_path_raw = _git(baseline.root, 'rev-parse', '--git-path', 'index').rstrip(b'\n')
        index_path = Path(index_path_raw.decode('utf-8'))
        if not index_path.is_absolute():
            index_path = baseline.root / index_path
        index_stat = index_path.stat(follow_symlinks=False)
        if index_path.is_symlink() or not stat.S_ISREG(index_stat.st_mode):
            return None
        indexed_paths = _git(baseline.root, 'ls-files', '--cached', '-z')
    except (OSError, UnicodeError, SliceBGitRejected):
        return None
    try:
        raw_index = index_path.read_bytes()
    except OSError:
        return None
    if hashlib.sha256(raw_index).hexdigest() != baseline.index_sha256:
        return None
    tracked = len(tuple(path for path in indexed_paths.split(b'\0') if path))
    return GitInspection(
        baseline.root,
        baseline.branch_ref,
        baseline.head_oid,
        baseline.tree_oid,
        baseline.object_format,
        baseline.index_sha256,
        baseline.worktree_sha256,
        tracked,
    )


@dataclass(frozen=True, slots=True)
class GuestSessionExport:
    scratch_root: Path
    repo_root: Path
    copy_path: Path
    repository_tar: bytes
    receipt_path: Path
    identity: HostVmIdentity
    authority: VerifiedGuestAuthority
    config: OfflinePreservationConfig
    disk_hashes: DiskHashes


@dataclass(frozen=True, slots=True)
class GuestSessionEvidenceBuilder:
    git_inspector: SessionGitInspector = inspect_clean_session_git

    def build(self, exported: GuestSessionExport) -> OfflinePreservationEvidence | None:
        """Build evidence only when receipt, authority, clean Git, and copy identities bind."""
        identity = exported.identity
        authority = exported.authority
        config = exported.config
        try:
            receipt = verify_session_receipt(
                exported.receipt_path, authority.key, authority.receipt_sha256,
            )
        except (OSError, SliceBSessionError, ValueError):
            return None
        git = self.git_inspector(exported.repo_root)
        if git is None:
            return None
        try:
            rebound = verify_guest_authority(
                receipt, _guest_baseline(git), authority.image_authority,
            )
        except (SliceBGitRejected, SliceBSessionError, ValueError):
            return None
        if not _authority_matches(rebound, authority):
            return None
        try:
            copied = exported.copy_path.stat(follow_symlinks=False)
        except OSError:
            return None
        if not stat.S_ISREG(copied.st_mode) or copied.st_nlink != 1:
            return None
        source_sha = exported.disk_hashes.source_sha256
        copy_sha = exported.disk_hashes.copy_sha256
        export_manifest = json.dumps({
            'schema': 'dotfiles-ai/oc2-offline-export/v1',
            'session_generation': authority.key.session_generation,
            'receipt_sha256': authority.receipt_sha256,
            'manifest_sha256': authority.manifest_sha256,
            'repository_path': config.guest_repository_path,
            'repository_tar_sha256': hashlib.sha256(exported.repository_tar).hexdigest(),
            'head_oid': git.head_oid,
            'tree_oid': git.tree_oid,
            'index_sha256': git.index_sha256,
            'worktree_sha256': git.worktree_sha256,
        }, sort_keys=True, separators=(',', ':')).encode('utf-8')
        try:
            write_new_file(
                exported.scratch_root / 'guest-export-manifest.json',
                export_manifest,
                0o600,
            )
        except OSError:
            return None
        copy_disk = HostDiskIdentity(
            str(exported.copy_path), copied.st_dev, copied.st_ino,
        )
        return OfflinePreservationEvidence(
            session_key=authority.key,
            source_disk=identity.disk,
            copy_disk=copy_disk,
            copy_destination_isolated=None,
            host_repository_unchanged=None,
            source_sha256=source_sha,
            copy_sha256=copy_sha,
            qcow2_structure_verified=None,
            qcow2_logical_content_verified=None,
            guestfs_readonly=True,
            filesystem_state=FilesystemState.READ_ONLY_INSPECTED,
            filesystem_repair_performed=False,
            receipt_sha256=authority.receipt_sha256,
            manifest_sha256=authority.manifest_sha256,
            session_artifacts_verified=True,
            repository_path=config.guest_repository_path,
            branch_ref=git.branch_ref,
            head_oid=git.head_oid,
            tree_oid=git.tree_oid,
            object_format=git.object_format,
            index_sha256=git.index_sha256,
            index_structure_valid=True,
            worktree_sha256=git.worktree_sha256,
            object_database_valid=True,
            git_status_complete=True,
            git_dirty=False,
            tracked_file_count=git.tracked_file_count,
            untracked_file_count=0,
            export_manifest_sha256=hashlib.sha256(export_manifest).hexdigest(),
        )


def _guest_baseline(git: GitInspection) -> GitBaseline:
    return GitBaseline(
        git.root,
        git.branch_ref,
        git.head_oid,
        git.tree_oid,
        git.object_format,
        git.index_sha256,
        git.worktree_sha256,
    )


def _authority_matches(
    observed: VerifiedGuestAuthority, expected: VerifiedGuestAuthority,
) -> bool:
    return (
        is_verified_guest_authority(observed)
        and observed.key == expected.key
        and observed.manifest == expected.manifest
        and observed.manifest_sha256 == expected.manifest_sha256
        and observed.receipt_sha256 == expected.receipt_sha256
        and observed.image_authority == expected.image_authority
    )
