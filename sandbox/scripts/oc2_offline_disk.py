from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import HostDiskIdentity, HostVmIdentity
    from sandbox.scripts.oc2_host_ssh import CommandRunner, SubprocessCommandRunner
    from sandbox.scripts.oc2_guestfs_audit import GuestfishReadOnlyAuditProvider
    from sandbox.scripts.oc2_guestfs_transport import SubprocessGuestfishRunner
    from sandbox.scripts.oc2_offline_preservation import OfflinePreservationEvidence
    from sandbox.scripts.oc2_offline_preserver import (
        GuestfsAuditProvider,
        LibguestfsSettings,
        OfflinePreservationConfig,
        Qcow2Metadata,
    )
    from sandbox.scripts.oc2_slice_b_git import (
        GitBaseline,
        SliceBGitRejected,
        recheck_host_baseline,
    )
    from sandbox.scripts.oc2_slice_b_session import VerifiedGuestAuthority
else:
    from oc2_host_control import HostDiskIdentity, HostVmIdentity
    from oc2_host_ssh import CommandRunner, SubprocessCommandRunner
    from oc2_guestfs_audit import GuestfishReadOnlyAuditProvider
    from oc2_guestfs_transport import SubprocessGuestfishRunner
    from oc2_offline_preservation import OfflinePreservationEvidence
    from oc2_offline_preserver import (
        GuestfsAuditProvider,
        LibguestfsSettings,
        OfflinePreservationConfig,
        Qcow2Metadata,
    )
    from oc2_slice_b_git import GitBaseline, SliceBGitRejected, recheck_host_baseline
    from oc2_slice_b_session import VerifiedGuestAuthority

JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']


@dataclass(frozen=True, slots=True)
class LocalOfflinePreservationOps:
    runner: CommandRunner = SubprocessCommandRunner(timeout_seconds=120)
    audit_provider: GuestfsAuditProvider | None = None

    def source_identity_matches(self, identity: HostVmIdentity) -> bool | None:
        try:
            stat = Path(identity.disk.path).stat(follow_symlinks=False)
        except OSError:
            return None
        return (stat.st_dev, stat.st_ino) == (identity.disk.device, identity.disk.inode)

    def inspect_qcow2(self, path: Path) -> Qcow2Metadata:
        result = self.runner.run((
            '/usr/bin/qemu-img', 'info', '--output=json', '--backing-chain', str(path),
        ))
        if result.returncode != 0:
            return _unknown_metadata()
        try:
            return parse_qcow2_metadata(result.stdout)
        except (ValueError, UnicodeError):
            return _unknown_metadata()

    def create_output_dir(self, output_root: Path) -> Path:
        if output_root.is_symlink() or not output_root.is_dir():
            raise OSError('offline output root is unavailable or linked')
        return Path(tempfile.mkdtemp(prefix='oc2-t7-offline.', dir=output_root))

    def copy_disk(
        self, source: Path, destination: Path, expected_source: HostDiskIdentity,
    ) -> HostDiskIdentity:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        destination_fd = -1
        try:
            source_stat = os.fstat(source_fd)
            if (
                not stat.S_ISREG(source_stat.st_mode)
                or source_stat.st_nlink != 1
                or (source_stat.st_dev, source_stat.st_ino)
                != (expected_source.device, expected_source.inode)
            ):
                raise OSError('source disk identity changed before copy')
            destination_fd = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
                0o600,
            )
            while chunk := os.read(source_fd, 1024 * 1024):
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    view = view[written:]
            os.fsync(destination_fd)
        finally:
            os.close(source_fd)
            if destination_fd >= 0:
                os.close(destination_fd)
        copied = destination.stat(follow_symlinks=False)
        if not stat.S_ISREG(copied.st_mode) or not copied.st_ino or copied.st_nlink != 1:
            raise OSError('offline copy identity is unsafe')
        return HostDiskIdentity(str(destination), copied.st_dev, copied.st_ino)

    def sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def byte_identical(self, source: Path, copy: Path) -> bool:
        return self.sha256(source) == self.sha256(copy)

    def logical_compare(self, source: Path, copy: Path) -> bool:
        return self.runner.run((
            '/usr/bin/qemu-img', 'compare', '-f', 'qcow2', '-F', 'qcow2',
            str(source), str(copy),
        )).returncode == 0

    def host_repository_unchanged(self, baseline: GitBaseline) -> bool | None:
        try:
            recheck_host_baseline(baseline)
        except SliceBGitRejected:
            return False
        return True

    def destination_isolated(self, destination: Path, baseline: GitBaseline) -> bool:
        resolved_destination = destination.resolve(strict=False)
        resolved_repository = baseline.root.resolve(strict=False)
        return (
            resolved_destination != resolved_repository
            and resolved_repository not in resolved_destination.parents
            and resolved_destination not in resolved_repository.parents
        )

    def audit_readonly(
        self,
        copy: Path,
        settings: LibguestfsSettings,
        identity: HostVmIdentity,
        authority: VerifiedGuestAuthority,
        config: OfflinePreservationConfig,
    ) -> OfflinePreservationEvidence | None:
        provider = self.audit_provider or GuestfishReadOnlyAuditProvider(
            SubprocessGuestfishRunner(),
        )
        return provider.audit_readonly(
            copy, settings, identity, authority, config,
        )


def parse_qcow2_metadata(raw: bytes) -> Qcow2Metadata:
    value: JsonValue = json.loads(raw)
    chain = value if isinstance(value, list) else [value]
    if not chain or not isinstance(chain[0], dict):
        return _unknown_metadata()
    first = chain[0]
    image_format = first.get('format')
    backing_file = first.get('backing-filename')
    dirty = first.get('dirty-flag')
    format_specific = first.get('format-specific')
    data = format_specific.get('data') if isinstance(format_specific, dict) else None
    corrupt = data.get('corrupt') if isinstance(data, dict) else None
    data_file = data.get('data-file') if isinstance(data, dict) else None
    data_file_raw = data.get('data-file-raw') if isinstance(data, dict) else None
    return Qcow2Metadata(
        image_format if isinstance(image_format, str) else None,
        len(chain),
        backing_file if isinstance(backing_file, str) else None,
        dirty if type(dirty) is bool else None,
        corrupt if type(corrupt) is bool else None,
        data_file if isinstance(data_file, str) else None,
        data_file_raw if type(data_file_raw) is bool else None,
    )


def _unknown_metadata() -> Qcow2Metadata:
    return Qcow2Metadata(None, None, None, None, None, None, None)
