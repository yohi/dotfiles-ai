from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import (
        HostDiskIdentity,
        HostIsolationResult,
        HostVmIdentity,
    )
    from sandbox.scripts.oc2_slice_b_git import GitBaseline
    from sandbox.scripts.oc2_slice_b_session import VerifiedGuestAuthority

else:
    from oc2_host_control import HostDiskIdentity, HostIsolationResult, HostVmIdentity
    from oc2_host_identity import host_disk_identity_valid
    from oc2_offline_preservation import OfflinePreservationEvidence
    from oc2_slice_b_git import GitBaseline
    from oc2_slice_b_session import VerifiedGuestAuthority

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_identity import host_disk_identity_valid
    from sandbox.scripts.oc2_offline_preservation import OfflinePreservationEvidence

@dataclass(frozen=True, slots=True)
class Qcow2Metadata:
    image_format: str | None
    backing_chain_length: int | None
    backing_file: str | None
    dirty_flag: bool | None
    corrupt: bool | None


@dataclass(frozen=True, slots=True)
class LibguestfsSettings:
    kernel_version: str
    kernel_image: Path
    modules: Path
    cache_dir: Path
    tmp_dir: Path
    backend: str

    def environment(self) -> tuple[tuple[str, str], ...]:
        return (
            ('SUPERMIN_KERNEL', str(self.kernel_image)),
            ('SUPERMIN_MODULES', str(self.modules)),
            ('SUPERMIN_KERNEL_VERSION', self.kernel_version),
            ('LIBGUESTFS_CACHEDIR', str(self.cache_dir)),
            ('LIBGUESTFS_TMPDIR', str(self.tmp_dir)),
            ('LIBGUESTFS_BACKEND', self.backend),
        )


@dataclass(frozen=True, slots=True)
class OfflinePreservationConfig:
    source_disk_path: Path
    output_root: Path
    guest_repository_path: str
    guest_receipt_path: str
    guest_manifest_path: str
    libguestfs: LibguestfsSettings


class GuestfsAuditProvider(Protocol):
    def audit_readonly(
        self,
        copy_path: Path,
        settings: LibguestfsSettings,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        config: OfflinePreservationConfig,
    ) -> OfflinePreservationEvidence | None: ...


class OfflinePreservationOps(Protocol):
    def source_identity_matches(self, identity: HostVmIdentity) -> bool | None: ...

    def inspect_qcow2(self, path: Path) -> Qcow2Metadata: ...

    def create_output_dir(self, output_root: Path) -> Path: ...

    def copy_disk(
        self, source: Path, destination: Path, expected_source: HostDiskIdentity,
    ) -> HostDiskIdentity: ...

    def sha256(self, path: Path) -> str: ...

    def byte_identical(self, source: Path, copy: Path) -> bool: ...

    def logical_compare(self, source: Path, copy: Path) -> bool: ...

    def host_repository_unchanged(self, baseline: GitBaseline) -> bool | None: ...

    def destination_isolated(self, destination: Path, baseline: GitBaseline) -> bool | None: ...

    def audit_readonly(
        self,
        copy: Path,
        settings: LibguestfsSettings,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        config: OfflinePreservationConfig,
    ) -> OfflinePreservationEvidence | None: ...


@dataclass(frozen=True, slots=True)
class OfflinePreserver:
    config: OfflinePreservationConfig
    ops: OfflinePreservationOps

    def preserve(
        self,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        isolation: HostIsolationResult,
    ) -> OfflinePreservationEvidence | None:
        try:
            return self._preserve(identity, authority, isolation)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _preserve(
        self,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        isolation: HostIsolationResult,
    ) -> OfflinePreservationEvidence | None:
        if (
            not isolation.verified
            or authority.key != identity.session_key
            or self.config.source_disk_path != Path(identity.disk.path)
            or not host_disk_identity_valid(identity.disk)
            or self.ops.source_identity_matches(identity) is not True
        ):
            return None
        baseline = authority.manifest.baseline
        source_info = self.ops.inspect_qcow2(self.config.source_disk_path)
        if not self._clean_single_qcow(source_info):
            return None
        output_dir = self.ops.create_output_dir(self.config.output_root)
        if (output_dir.is_symlink() or not output_dir.is_dir()
                or not self.ops.destination_isolated(output_dir, baseline)):
            return None
        copy_path = output_dir / 'recovered-audit.qcow2'
        copy_disk = self.ops.copy_disk(
            self.config.source_disk_path, copy_path, identity.disk,
        )
        if (not host_disk_identity_valid(copy_disk) or copy_disk == identity.disk
                or copy_path.is_symlink() or not copy_path.is_file()):
            return None
        copy_info = self.ops.inspect_qcow2(copy_path)
        source_sha = self.ops.sha256(self.config.source_disk_path)
        copy_sha = self.ops.sha256(copy_path)
        if (
            not self._clean_single_qcow(copy_info)
            or source_info != copy_info
            or source_sha != copy_sha
            or not self.ops.byte_identical(self.config.source_disk_path, copy_path)
            or not self.ops.logical_compare(self.config.source_disk_path, copy_path)
            or self.ops.source_identity_matches(identity) is not True
        ):
            return None
        evidence = self.ops.audit_readonly(
            copy_path, self.config.libguestfs, identity, authority, self.config,
        )
        if evidence is None:
            return None
        if (
            evidence.session_key != authority.key
            or evidence.receipt_sha256 != authority.receipt_sha256
            or evidence.manifest_sha256 != authority.manifest_sha256
            or evidence.repository_path != self.config.guest_repository_path
            or evidence.guestfs_readonly is not True
            or evidence.session_artifacts_verified is not True
            or self.ops.host_repository_unchanged(baseline) is not True
        ):
            return None
        return replace(
            evidence,
            source_disk=identity.disk,
            copy_disk=copy_disk,
            copy_destination_isolated=True,
            host_repository_unchanged=True,
            source_sha256=source_sha,
            copy_sha256=copy_sha,
            qcow2_structure_verified=True,
            qcow2_logical_content_verified=True,
            guestfs_readonly=True,
        )

    @staticmethod
    def _clean_single_qcow(metadata: Qcow2Metadata) -> bool:
        return (
            metadata.image_format == 'qcow2'
            and metadata.backing_chain_length == 1
            and metadata.backing_file is None
            and metadata.dirty_flag is False
            and metadata.corrupt is False
        )
