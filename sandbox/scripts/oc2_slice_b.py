"""Offline-only Slice B wiring; production Writer and Host lifecycle are absent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_lifecycle import (
        HostControlledStopRequest,
        HostControlledStopResult,
        HostLifecycleStage,
        LifecycleFailure,
        coordinate_host_controlled_stop,
    )
    from sandbox.scripts.oc2_slice_b_git import (
        GitBaseline,
        SliceBGitRejected,
        _git,
        admit_clean_repo,
        build_verified_bundle,
        recheck_host_baseline,
        verify_bundle_manifest,
    )
    from sandbox.scripts.oc2_offline_preservation import PreservationDisposition
    from sandbox.scripts.oc2_slice_b_image import GuestImageRunner, ImagePin
    from sandbox.scripts.oc2_slice_b_session import (
        GuestAuthorityVerificationRequest,
        SliceBReceipt,
        SliceBStartMessage,
        VerifiedGuestAuthority,
        build_start_message,
        create_session_receipt,
        import_guest_baseline,
        verify_guest_authority_from_host_record,
    )
    from sandbox.scripts.oc2_writer import (
        WriterIdentity,
        WriterSessionKey,
        validate_container_id,
    )
else:
    from oc2_host_lifecycle import (
        HostControlledStopRequest,
        HostControlledStopResult,
        HostLifecycleStage,
        LifecycleFailure,
        coordinate_host_controlled_stop,
    )
    from oc2_offline_preservation import PreservationDisposition
    from oc2_slice_b_git import (
        GitBaseline,
        SliceBGitRejected,
        _git,
        admit_clean_repo,
        build_verified_bundle,
        recheck_host_baseline,
        verify_bundle_manifest,
    )
    from oc2_slice_b_image import GuestImageRunner, ImagePin
    from oc2_slice_b_session import (
        GuestAuthorityVerificationRequest,
        SliceBReceipt,
        SliceBStartMessage,
        VerifiedGuestAuthority,
        build_start_message,
        create_session_receipt,
        import_guest_baseline,
        verify_guest_authority_from_host_record,
    )
    from oc2_writer import WriterIdentity, WriterSessionKey, validate_container_id

SliceBOfflineOutcome = Literal[
    "OFFLINE_FAKE_PASS", "REJECTED", "PENDING", "PRESERVATION_UNVERIFIED"
]

_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STARTED_AT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z\Z"
)


@dataclass(frozen=True)
class SliceBOfflineInputs:
    key: WriterSessionKey
    runtime_sha256: str
    image_pin: ImagePin
    archive_path: Path
    image_control_root: Path
    docker_host: str
    state_root: Path
    bundle_path: Path
    guest_repo_path: Path
    image_runner: GuestImageRunner


@dataclass(frozen=True)
class SliceBWriterObservation:
    identity: WriterIdentity
    tui_exit_code: int
    fixture_commit_oid: str | None


class SliceBOps(Protocol):
    """Injected offline operations; implementations must honor these contracts."""

    def inputs(self, baseline: GitBaseline, sandbox_name: str) -> SliceBOfflineInputs:
        """Return isolated paths and pinned inputs without starting infrastructure."""
        ...

    def run_writer(
        self, authority: VerifiedGuestAuthority, start: SliceBStartMessage,
        guest_repo: Path,
    ) -> SliceBWriterObservation:
        """Return only after the fake Writer exits, with final identity, status, and fixture commit.

        A successful observation requires exit code zero; the adapter independently
        verifies the identity, timestamp, image, and fixture commit before stopping.
        """
        ...

    def stop_request(
        self, authority: VerifiedGuestAuthority, writer: WriterIdentity,
    ) -> HostControlledStopRequest:
        """Build a stop request bound to the exact start authority and Writer identity."""
        ...

    def record_result(
        self, outcome: SliceBOfflineOutcome, reason: str | None,
        result: HostControlledStopResult | None,
    ) -> None:
        """Record a pre-coordination rejection or the completed lifecycle result."""
        ...


def _same_baseline(left: GitBaseline, right: GitBaseline) -> bool:
    """Compare all captured host or imported Guest baseline evidence."""
    return left == right


def _validate_started_at(value: object) -> bool:
    """Accept canonical UTC timestamps except either representation of the zero sentinel."""
    if not isinstance(value, str) or not _STARTED_AT.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed != datetime.min.replace(tzinfo=timezone.utc)


def _verify_fixture(repo: Path, baseline: GitBaseline, commit: str | None) -> bool:
    """Verify the injected fixture is the sole commit directly atop the Guest baseline."""
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        return False
    try:
        head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        parent_line = _git(
            repo, "rev-list", "--parents", "-n", "1", commit,
        ).decode().split()
        paths = _git(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit,
        ).decode().splitlines()
        blob = _git(repo, "cat-file", "blob", f"{commit}:oc2-slice-b-fixture.txt")
    except (SliceBGitRejected, UnicodeError):
        return False
    from sandbox.oc2_slice_b.offline_fixture import FIXTURE_BYTES, FIXTURE_NAME

    return (
        head == commit
        and parent_line == [commit, baseline.head_oid]
        and paths == [FIXTURE_NAME]
        and blob == FIXTURE_BYTES
    )


def _record(ops: SliceBOps, outcome: SliceBOfflineOutcome, reason: str) -> int:
    """Record a rejection before lifecycle coordination and return the failure status."""
    ops.record_result(outcome, reason, None)
    return 1


def run_slice_b(
    repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps
) -> int:
    """Run the offline slice while preserving artifacts on every post-creation failure.

    The Session Receipt remains PENDING evidence of admission; the returned integer
    reports this invocation's lifecycle outcome and never rewrites the Receipt.
    """
    if dry_run:
        return 1
    receipt_path: Path | None = None
    try:
        if (repo_root.is_symlink() or workspace.is_symlink()
                or not repo_root.is_dir() or not workspace.is_dir()):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        baseline = admit_clean_repo(workspace)
        recheck_host_baseline(baseline)
        inputs = ops.inputs(baseline, sandbox_name)
        inputs.key.validate()
        if inputs.guest_repo_path.exists():
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        guest_path = inputs.guest_repo_path.resolve()
        state_path = inputs.state_root.resolve()
        bundle_path = inputs.bundle_path.resolve()
        if (inputs.guest_repo_path.is_symlink()
                or guest_path.is_relative_to(baseline.root)
                or baseline.root.is_relative_to(guest_path)
                or guest_path.is_relative_to(state_path)
                or state_path.is_relative_to(guest_path)
                or bundle_path.is_relative_to(guest_path)):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        if inputs.state_root.resolve().is_relative_to(baseline.root):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        recheck_host_baseline(baseline)
        artifact = build_verified_bundle(
            baseline, inputs.bundle_path, key=inputs.key,
            runtime_sha256=inputs.runtime_sha256,
        )
        manifest = verify_bundle_manifest(
            artifact, expected_key=inputs.key,
            expected_manifest_sha256=artifact.manifest_sha256,
            expected_runtime_sha256=inputs.runtime_sha256,
        )
        if manifest.baseline != baseline:
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        recheck_host_baseline(baseline)
        guest_baseline = import_guest_baseline(
            artifact, inputs.guest_repo_path,
            expected_manifest_sha256=artifact.manifest_sha256,
            expected_key=inputs.key,
            expected_runtime_sha256=inputs.runtime_sha256,
        )
        observed_guest = admit_clean_repo(inputs.guest_repo_path)
        if not _same_baseline(observed_guest, guest_baseline):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        receipt = SliceBReceipt(
            key=inputs.key, baseline=baseline, bundle_sha256=artifact.bundle_sha256,
            manifest_sha256=artifact.manifest_sha256,
            transfer_policy_id=artifact.transfer_policy_id,
            runtime_sha256=inputs.runtime_sha256, image_record=inputs.image_pin,
            image_record_sha256=inputs.image_pin.record_sha256, state="PENDING",
            reason="NOT_RUN", writer_id=None, started_at=None,
        )
        receipt_path = create_session_receipt(inputs.state_root, receipt, artifact)
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        authority = verify_guest_authority_from_host_record(
            GuestAuthorityVerificationRequest(
                receipt_path=receipt_path, expected_key=inputs.key,
                expected_receipt_sha256=receipt_hash, guest_baseline=observed_guest,
                archive_path=inputs.archive_path,
                supervisor_image_root=inputs.image_control_root,
                docker_host=inputs.docker_host,
            ),
            inputs.image_runner,
        )
        if (authority.key != inputs.key
                or authority.manifest.baseline != baseline
                or authority.runtime_sha256 != inputs.runtime_sha256
                or authority.image_config_id != inputs.image_pin.config_id):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        recheck_host_baseline(baseline)
        recheck_host_baseline(guest_baseline)
        if not _same_baseline(admit_clean_repo(inputs.guest_repo_path), guest_baseline):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        start = build_start_message(authority)
        observation = ops.run_writer(authority, start, inputs.guest_repo_path)
        identity = observation.identity
        validate_container_id(identity.container_id)
        if not re.fullmatch(r"[0-9a-f]{64}", identity.container_id):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        if (not _IMAGE_ID.fullmatch(identity.image_id)
                or identity.image_id != authority.image_config_id
                or not _validate_started_at(identity.started_at)
                or type(observation.tui_exit_code) is not int
                or observation.tui_exit_code != 0
                or not _verify_fixture(inputs.guest_repo_path, guest_baseline,
                                       observation.fixture_commit_oid)):
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        request = ops.stop_request(authority, identity)
        stop_identity = getattr(request, "writer_identity", None)
        if not isinstance(stop_identity, WriterIdentity) or stop_identity != identity:
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        if request.authority is not authority:
            return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
        result = coordinate_host_controlled_stop(request)
        stages = set(result.stages)
        failures = set(result.failures)
        guest_unverified = (
            LifecycleFailure.GUEST_STOP_UNVERIFIED in failures
            or HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED in stages
            or (result.guest_verdict is not None and not result.guest_verdict.verified)
        )
        if guest_unverified:
            outcome: SliceBOfflineOutcome = "PENDING"
            reason = "GUEST_QUIESCENCE_UNVERIFIED"
        elif (LifecycleFailure.PRESERVATION_MISMATCH in failures
              or (result.preservation is not None
                  and result.preservation.disposition is PreservationDisposition.MISMATCH)):
            outcome = "REJECTED"
            reason = "OBSERVED_MISMATCH"
        elif (result.host_isolation is None or not result.host_isolation.verified
              or HostLifecycleStage.VM_ISOLATION_VERIFIED not in stages
              or LifecycleFailure.VM_ISOLATION_UNVERIFIED in failures):
            outcome = "PENDING"
            reason = "HOST_ISOLATION_UNVERIFIED"
        elif (result.preservation is None
              or result.preservation.disposition is not PreservationDisposition.VERIFIED
              or HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED not in stages
              or HostLifecycleStage.OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED in stages):
            outcome = "PRESERVATION_UNVERIFIED"
            reason = "PRESERVATION_UNVERIFIED"
        elif (result.failures
              or result.guest_verdict is None
              or not result.guest_verdict.verified
              or HostLifecycleStage.GUEST_QUIESCENCE_VERIFIED not in stages
              or HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED in stages):
            outcome = "PENDING"
            reason = "LIFECYCLE_UNVERIFIED"
        else:
            outcome = "OFFLINE_FAKE_PASS"
            reason = None
        ops.record_result(outcome, reason, result)
        return 0 if outcome == "OFFLINE_FAKE_PASS" else 1
    except Exception:
        return _record(ops, "REJECTED", "OBSERVED_MISMATCH")
