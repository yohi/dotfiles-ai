from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_host_control import HostDiskIdentity, HostVmIdentity
    from sandbox.scripts.oc2_host_identity import host_disk_identity_valid
    from sandbox.scripts.oc2_slice_b_git import GitBaseline
    from sandbox.scripts.oc2_t7_index_policy import is_accepted_t7_index_fingerprint
else:
    import oc2_writer as w
    from oc2_host_control import HostDiskIdentity, HostVmIdentity
    from oc2_host_identity import host_disk_identity_valid
    from oc2_t7_index_policy import is_accepted_t7_index_fingerprint

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@unique
class FilesystemState(StrEnum):
    CLEAN_CHECKED = "clean-checked"
    READ_ONLY_INSPECTED = "read-only-inspected"
    UNKNOWN = "unknown"
    CORRUPT = "corrupt"


@unique
class PreservationDisposition(StrEnum):
    VERIFIED = "verified"
    CONDITIONALLY_ACCEPTED = "conditionally-accepted"
    UNVERIFIED = "unverified"
    MISMATCH = "mismatch"


@unique
class PreservationFailure(StrEnum):
    SESSION_MISMATCH = "session-mismatch"
    DISK_IDENTITY_MISMATCH = "disk-identity-mismatch"
    COPY_INTEGRITY_MISMATCH = "copy-integrity-mismatch"
    READ_ONLY_ACCESS_UNVERIFIED = "read-only-access-unverified"
    FILESYSTEM_STATE_UNVERIFIED = "filesystem-state-unverified"
    FILESYSTEM_CORRUPT_OR_REPAIRED = "filesystem-corrupt-or-repaired"
    RECEIPT_MANIFEST_MISMATCH = "receipt-manifest-mismatch"
    GIT_IDENTITY_MISMATCH = "git-identity-mismatch"
    GIT_STRUCTURE_UNVERIFIED = "git-structure-unverified"
    GIT_OBJECT_DATABASE_INVALID = "git-object-database-invalid"
    GIT_DIRTY_OR_UNTRACKED = "git-dirty-or-untracked"
    INDEX_MISMATCH_REQUIRES_OWNER = "index-mismatch-requires-owner"
    EXPORT_MANIFEST_INVALID = "export-manifest-invalid"
    HOST_WRITE_ISOLATION_UNVERIFIED = "host-write-isolation-unverified"
    HOST_REPOSITORY_CHANGED = "host-repository-changed"


@dataclass(frozen=True, slots=True)
class PreservationExpectation:
    session_key: w.WriterSessionKey
    receipt_sha256: str
    manifest_sha256: str
    baseline: GitBaseline


@dataclass(frozen=True, slots=True)
class OfflinePreservationEvidence:
    session_key: w.WriterSessionKey
    source_disk: HostDiskIdentity
    copy_disk: HostDiskIdentity
    copy_destination_isolated: bool | None
    host_repository_unchanged: bool | None
    source_sha256: str
    copy_sha256: str
    qcow2_structure_verified: bool | None
    qcow2_logical_content_verified: bool | None
    guestfs_readonly: bool | None
    filesystem_state: FilesystemState
    filesystem_repair_performed: bool | None
    receipt_sha256: str
    manifest_sha256: str
    session_artifacts_verified: bool | None
    repository_path: str
    branch_ref: str
    head_oid: str
    tree_oid: str
    object_format: str
    index_sha256: str
    index_structure_valid: bool | None
    worktree_sha256: str
    object_database_valid: bool | None
    git_status_complete: bool | None
    git_dirty: bool | None
    tracked_file_count: int | None
    untracked_file_count: int | None
    export_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class PreservationDecision:
    disposition: PreservationDisposition
    failures: tuple[PreservationFailure, ...]


def _is_t7_index_exception(
    expected: PreservationExpectation,
    evidence: OfflinePreservationEvidence,
) -> bool:
    baseline = expected.baseline
    fingerprint = (
        expected.session_key.workspace_id, expected.session_key.sandbox_id,
        expected.session_key.session_generation, expected.receipt_sha256,
        expected.manifest_sha256, baseline.branch_ref, baseline.head_oid,
        baseline.tree_oid, baseline.object_format, baseline.index_sha256,
        baseline.worktree_sha256, evidence.copy_sha256, evidence.index_sha256,
        evidence.head_oid, evidence.tree_oid, evidence.worktree_sha256,
        evidence.filesystem_state.value,
    )
    return is_accepted_t7_index_fingerprint(fingerprint)


def evaluate_offline_preservation(
    expected: PreservationExpectation,
    identity: HostVmIdentity,
    evidence: OfflinePreservationEvidence,
) -> PreservationDecision:
    if evidence.session_key != expected.session_key or identity.session_key != expected.session_key:
        return PreservationDecision(
            PreservationDisposition.MISMATCH,
            (PreservationFailure.SESSION_MISMATCH,),
        )
    if (evidence.source_disk != identity.disk or evidence.copy_disk == identity.disk
            or not host_disk_identity_valid(evidence.copy_disk)):
        return PreservationDecision(
            PreservationDisposition.MISMATCH,
            (PreservationFailure.DISK_IDENTITY_MISMATCH,),
        )
    hashes = (evidence.source_sha256, evidence.copy_sha256)
    if any(not _SHA256.fullmatch(value) for value in hashes):
        return PreservationDecision(
            PreservationDisposition.MISMATCH,
            (PreservationFailure.COPY_INTEGRITY_MISMATCH,),
        )
    if evidence.source_sha256 != evidence.copy_sha256 or evidence.copy_disk.path == identity.disk.path:
        return PreservationDecision(
            PreservationDisposition.MISMATCH,
            (PreservationFailure.COPY_INTEGRITY_MISMATCH,),
        )

    failures: list[PreservationFailure] = []
    mismatch = False
    unknown = False
    if (evidence.copy_destination_isolated is None
            or evidence.host_repository_unchanged is None):
        failures.append(PreservationFailure.HOST_WRITE_ISOLATION_UNVERIFIED)
        unknown = True
    elif not evidence.copy_destination_isolated or not evidence.host_repository_unchanged:
        failures.append(PreservationFailure.HOST_REPOSITORY_CHANGED)
        mismatch = True

    for verified in (evidence.qcow2_structure_verified,
                     evidence.qcow2_logical_content_verified):
        if verified is None:
            failures.append(PreservationFailure.COPY_INTEGRITY_MISMATCH)
            unknown = True
        elif not verified:
            failures.append(PreservationFailure.COPY_INTEGRITY_MISMATCH)
            mismatch = True
    if evidence.guestfs_readonly is None:
        failures.append(PreservationFailure.READ_ONLY_ACCESS_UNVERIFIED)
        unknown = True
    elif not evidence.guestfs_readonly:
        failures.append(PreservationFailure.READ_ONLY_ACCESS_UNVERIFIED)
        mismatch = True
    if evidence.filesystem_repair_performed is None:
        failures.append(PreservationFailure.FILESYSTEM_STATE_UNVERIFIED)
        unknown = True
    elif evidence.filesystem_repair_performed:
        failures.append(PreservationFailure.FILESYSTEM_CORRUPT_OR_REPAIRED)
        mismatch = True
    if evidence.filesystem_state is FilesystemState.CORRUPT:
        failures.append(PreservationFailure.FILESYSTEM_CORRUPT_OR_REPAIRED)
        mismatch = True
    elif evidence.filesystem_state is FilesystemState.UNKNOWN:
        failures.append(PreservationFailure.FILESYSTEM_STATE_UNVERIFIED)
        unknown = True
    if (evidence.receipt_sha256 != expected.receipt_sha256
            or evidence.manifest_sha256 != expected.manifest_sha256):
        failures.append(PreservationFailure.RECEIPT_MANIFEST_MISMATCH)
        mismatch = True
    if evidence.session_artifacts_verified is None:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    elif not evidence.session_artifacts_verified:
        failures.append(PreservationFailure.RECEIPT_MANIFEST_MISMATCH)
        mismatch = True
    if (not evidence.repository_path.startswith("/")
            or ".." in evidence.repository_path.split("/")):
        failures.append(PreservationFailure.GIT_IDENTITY_MISMATCH)
        mismatch = True
    if not _SHA256.fullmatch(evidence.export_manifest_sha256):
        failures.append(PreservationFailure.EXPORT_MANIFEST_INVALID)
        mismatch = True

    if evidence.index_structure_valid is None:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    elif not evidence.index_structure_valid:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        mismatch = True
    if evidence.git_status_complete is not True:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    if evidence.object_database_valid is None:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    elif not evidence.object_database_valid:
        failures.append(PreservationFailure.GIT_OBJECT_DATABASE_INVALID)
        mismatch = True
    if evidence.git_dirty is None:
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    elif evidence.git_dirty:
        failures.append(PreservationFailure.GIT_DIRTY_OR_UNTRACKED)
        mismatch = True
    if (evidence.tracked_file_count is None or evidence.untracked_file_count is None):
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        unknown = True
    elif (isinstance(evidence.tracked_file_count, bool)
          or isinstance(evidence.untracked_file_count, bool)
          or evidence.tracked_file_count < 0 or evidence.untracked_file_count < 0):
        failures.append(PreservationFailure.GIT_STRUCTURE_UNVERIFIED)
        mismatch = True
    elif evidence.untracked_file_count:
        failures.append(PreservationFailure.GIT_DIRTY_OR_UNTRACKED)
        mismatch = True
    baseline = expected.baseline
    if not _SHA256.fullmatch(evidence.index_sha256):
        failures.append(PreservationFailure.GIT_IDENTITY_MISMATCH)
        mismatch = True
    git_fields_match = (
        evidence.branch_ref == baseline.branch_ref
        and evidence.head_oid == baseline.head_oid
        and evidence.tree_oid == baseline.tree_oid
        and evidence.object_format == baseline.object_format
        and evidence.worktree_sha256 == baseline.worktree_sha256
    )
    if not git_fields_match:
        failures.append(PreservationFailure.GIT_IDENTITY_MISMATCH)
        mismatch = True
    index_matches = evidence.index_sha256 == baseline.index_sha256
    t7_exception = not index_matches and _is_t7_index_exception(expected, evidence)
    if not index_matches and not t7_exception:
        failures.append(PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER)
        unknown = True

    unique_failures = tuple(dict.fromkeys(failures))
    if mismatch:
        return PreservationDecision(PreservationDisposition.MISMATCH, unique_failures)
    if unknown:
        return PreservationDecision(PreservationDisposition.UNVERIFIED, unique_failures)
    if t7_exception:
        return PreservationDecision(
            PreservationDisposition.CONDITIONALLY_ACCEPTED,
            (PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,),
        )
    if evidence.filesystem_state is not FilesystemState.CLEAN_CHECKED:
        return PreservationDecision(
            PreservationDisposition.UNVERIFIED,
            (PreservationFailure.FILESYSTEM_STATE_UNVERIFIED,),
        )
    return PreservationDecision(PreservationDisposition.VERIFIED, ())
