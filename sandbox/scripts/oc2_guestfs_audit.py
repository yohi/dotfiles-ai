from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.scripts.oc2_guestfs_files import (
        MAX_MANIFEST_BYTES,
        MAX_RECEIPT_BYTES,
        MAX_SESSION_ARCHIVE_BYTES,
        extract_regular_tar,
        find_repo_root,
        write_receipt_pair,
    )
    from sandbox.scripts.oc2_guestfs_session import (
        GuestSessionEvidenceBuilder,
        GuestSessionExport,
    )
    from sandbox.scripts.oc2_guestfs_transport import (
        GuestfishCommandResult,
        GuestfishRunner,
    )
    from sandbox.scripts.oc2_host_control import HostVmIdentity
    from sandbox.scripts.oc2_offline_preservation import OfflinePreservationEvidence
    from sandbox.scripts.oc2_offline_preserver import (
        LibguestfsSettings,
        OfflinePreservationConfig,
    )
    from sandbox.scripts.oc2_slice_b_session import VerifiedGuestAuthority
else:
    from oc2_guestfs_files import (
        MAX_MANIFEST_BYTES,
        MAX_RECEIPT_BYTES,
        MAX_SESSION_ARCHIVE_BYTES,
        extract_regular_tar,
        find_repo_root,
        write_receipt_pair,
    )
    from oc2_guestfs_session import GuestSessionEvidenceBuilder, GuestSessionExport
    from oc2_guestfs_transport import GuestfishCommandResult, GuestfishRunner
    from oc2_host_control import HostVmIdentity
    from oc2_offline_preservation import OfflinePreservationEvidence
    from oc2_offline_preserver import LibguestfsSettings, OfflinePreservationConfig
    from oc2_slice_b_session import VerifiedGuestAuthority

_GUEST_PATH_PART = re.compile(r'[A-Za-z0-9._+-]+\Z')


@dataclass(frozen=True, slots=True)
class GuestfishReadOnlyAuditProvider:
    runner: GuestfishRunner
    evidence_builder: GuestSessionEvidenceBuilder = GuestSessionEvidenceBuilder()

    def audit_readonly(
        self,
        copy_path: Path,
        settings: LibguestfsSettings,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        config: OfflinePreservationConfig,
    ) -> OfflinePreservationEvidence | None:
        if (
            authority.key != identity.session_key
            or not _guest_paths_match(config, authority)
            or settings.tmp_dir.is_symlink()
            or not settings.tmp_dir.is_dir()
        ):
            return None
        guestfish = (
            '/usr/bin/guestfish', '--ro', '--format=qcow2', '-a', str(copy_path), '-i',
        )
        with tempfile.TemporaryDirectory(prefix='oc2-guest-audit.', dir=settings.tmp_dir) as scratch:
            scratch_root = Path(scratch)
            repository_export = self.runner.run(
                (*guestfish, 'tar-out', config.guest_repository_path, '-'),
                settings=settings,
            )
            if not _export_valid(repository_export, MAX_SESSION_ARCHIVE_BYTES):
                return None
            repo_parent = scratch_root / 'repo-export'
            repo_parent.mkdir(mode=0o700)
            if not extract_regular_tar(repository_export.stdout, repo_parent):
                return None
            repo_root = find_repo_root(repo_parent)
            if repo_root is None:
                return None

            receipt_export = self.runner.run(
                (*guestfish, 'download', config.guest_receipt_path, '-'),
                settings=settings,
            )
            manifest_export = self.runner.run(
                (*guestfish, 'download', config.guest_manifest_path, '-'),
                settings=settings,
            )
            if (not _export_valid(receipt_export, MAX_RECEIPT_BYTES)
                    or not _export_valid(manifest_export, MAX_MANIFEST_BYTES)):
                return None
            receipt_file = write_receipt_pair(
                scratch_root,
                authority.key.workspace_id,
                authority.key.session_generation,
                receipt_export.stdout,
                manifest_export.stdout,
            )
            if receipt_file is None:
                return None
            return self.evidence_builder.build(GuestSessionExport(
                scratch_root,
                repo_root,
                copy_path,
                repository_export.stdout,
                receipt_file,
                identity,
                authority,
                config,
            ))


def _guest_paths_match(
    config: OfflinePreservationConfig, authority: VerifiedGuestAuthority,
) -> bool:
    paths = tuple(PurePosixPath(path) for path in (
        config.guest_repository_path,
        config.guest_receipt_path,
        config.guest_manifest_path,
    ))
    repository, receipt, manifest = paths
    if any(not _safe_guest_path(path) for path in paths):
        return False
    return (
        repository.name == 'guest-repo'
        and receipt.name == 'receipt.json'
        and manifest.name == 'bundle.manifest.json'
        and receipt.parent == manifest.parent
        and receipt.parent.name == authority.key.session_generation
        and receipt.parent.parent.name == authority.key.workspace_id
    )


def _safe_guest_path(path: PurePosixPath) -> bool:
    return path.is_absolute() and all(
        part not in {'.', '..'} and _GUEST_PATH_PART.fullmatch(part) is not None
        for part in path.parts[1:]
    )


def _export_valid(result: GuestfishCommandResult, maximum: int) -> bool:
    return result.returncode == 0 and 0 < len(result.stdout) <= maximum
