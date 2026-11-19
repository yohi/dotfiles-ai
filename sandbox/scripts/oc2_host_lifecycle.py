from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_host_control import (
        HostFailureCode,
        HostIsolationResult,
        HostStopObservations,
        HostVmControl,
        HostVmIdentity,
        verify_host_isolation,
        verify_host_running,
    )
    from sandbox.scripts.oc2_offline_preservation import (
        OfflinePreservationEvidence,
        PreservationExpectation,
        PreservationDecision,
        PreservationDisposition,
        evaluate_offline_preservation,
    )
    from sandbox.scripts.oc2_slice_b_session import (
        VerifiedGuestAuthority,
        is_verified_guest_authority,
    )
    from sandbox.scripts.oc2_supervisor import SupervisorError, SupervisorState
else:
    import oc2_writer as w
    from oc2_host_control import (
        HostFailureCode,
        HostIsolationResult,
        HostStopObservations,
        HostVmControl,
        HostVmIdentity,
        verify_host_isolation,
        verify_host_running,
    )
    from oc2_offline_preservation import (
        OfflinePreservationEvidence,
        PreservationExpectation,
        PreservationDecision,
        PreservationDisposition,
        evaluate_offline_preservation,
    )
    from oc2_slice_b_session import is_verified_guest_authority
    from oc2_supervisor import SupervisorError, SupervisorState

VM_SHUTDOWN_TIMEOUT_SECONDS = 180


class GuestStopPort(Protocol):
    @property
    def session_key(self) -> w.WriterSessionKey: ...

    @property
    def state(self) -> SupervisorState: ...

    @property
    def identity(self) -> w.WriterIdentity | None: ...

    def authority_is_bound(self, authority: VerifiedGuestAuthority) -> bool: ...

    def stop(self, identity: w.WriterIdentity | None = None) -> w.StopVerdict: ...


class OfflinePreserver(Protocol):
    """Export only after the coordinator supplies verified Host isolation."""

    def preserve(self, identity: HostVmIdentity, authority: VerifiedGuestAuthority,
                 isolation: HostIsolationResult) -> OfflinePreservationEvidence | None: ...


@unique
class HostLifecycleStage(StrEnum):
    WRITER_STOP_REQUESTED = "WRITER_STOP_REQUESTED"
    GUEST_QUIESCENCE_VERIFIED = "GUEST_QUIESCENCE_VERIFIED"
    GUEST_QUIESCENCE_UNVERIFIED = "GUEST_QUIESCENCE_UNVERIFIED"
    VM_STOP_REQUESTED = "VM_STOP_REQUESTED"
    VM_STOPPED_OBSERVED = "VM_STOPPED_OBSERVED"
    VM_ISOLATION_VERIFIED = "VM_ISOLATION_VERIFIED"
    OFFLINE_PRESERVATION_VERIFIED = "OFFLINE_PRESERVATION_VERIFIED"
    OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED = "OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED"


@unique
class LifecycleFailure(StrEnum):
    SESSION_AUTHORITY_MISMATCH = "session-authority-mismatch"
    WRITER_IDENTITY_MISMATCH = "writer-identity-mismatch"
    GUEST_STOP_UNVERIFIED = "guest-stop-unverified"
    HOST_PREFLIGHT_FAILED = "host-preflight-failed"
    HOST_IDENTITY_CHANGED = "host-identity-changed"
    VM_SHUTDOWN_REQUEST_FAILED = "vm-shutdown-request-failed"
    VM_STOP_UNOBSERVED = "vm-stop-unobserved"
    VM_ISOLATION_UNVERIFIED = "vm-isolation-unverified"
    PRESERVATION_UNAVAILABLE = "preservation-unavailable"
    PRESERVATION_UNVERIFIED = "preservation-unverified"
    PRESERVATION_MISMATCH = "preservation-mismatch"


@dataclass(frozen=True, slots=True)
class HostControlledStopRequest:
    guest: GuestStopPort
    authority: VerifiedGuestAuthority
    writer_identity: w.WriterIdentity
    host_identity: HostVmIdentity
    host_control: HostVmControl
    preserver: OfflinePreserver


@dataclass(frozen=True, slots=True)
class HostControlledStopResult:
    stages: tuple[HostLifecycleStage, ...]
    failures: tuple[LifecycleFailure | HostFailureCode, ...]
    guest_verdict: w.StopVerdict | None
    host_isolation: HostIsolationResult | None
    preservation: PreservationDecision | None


def _guest_stop_verified(
    guest: GuestStopPort,
    verdict: w.StopVerdict | None,
) -> bool:
    return (
        verdict is not None
        and verdict.verified
        and guest.state is SupervisorState.STOPPED_VERIFIED
    )


def _failed(
    failures: tuple[LifecycleFailure | HostFailureCode, ...],
    stages: tuple[HostLifecycleStage, ...] = (),
    guest_verdict: w.StopVerdict | None = None,
    host_isolation: HostIsolationResult | None = None,
    preservation: PreservationDecision | None = None,
) -> HostControlledStopResult:
    return HostControlledStopResult(stages, failures, guest_verdict, host_isolation,
                                    preservation)


def coordinate_host_controlled_stop(
    request: HostControlledStopRequest,
) -> HostControlledStopResult:
    """Stop one Writer, then require independent Host isolation before preservation."""
    configuration_failure = request.host_control.configuration_failure()
    if configuration_failure is not None:
        return _failed((configuration_failure,))
    guest = request.guest
    authority = request.authority
    identity = request.host_identity
    writer_identity = request.writer_identity
    if (
        not is_verified_guest_authority(authority)
        or not guest.authority_is_bound(authority)
        or authority.key != guest.session_key
        or guest.session_key != identity.session_key
    ):
        return _failed((LifecycleFailure.SESSION_AUTHORITY_MISMATCH,))
    if (guest.state is not SupervisorState.RUNNING
            or guest.identity != writer_identity):
        return _failed((LifecycleFailure.WRITER_IDENTITY_MISMATCH,))

    initial = request.host_control.observe(identity)
    preflight_failures = verify_host_running(identity, initial)
    if preflight_failures:
        return _failed((LifecycleFailure.HOST_PREFLIGHT_FAILED, *preflight_failures))

    stages = [HostLifecycleStage.WRITER_STOP_REQUESTED]
    verdict: w.StopVerdict | None = None
    failures: list[LifecycleFailure | HostFailureCode] = []
    try:
        verdict = guest.stop(writer_identity)
    except SupervisorError:
        failures.append(LifecycleFailure.GUEST_STOP_UNVERIFIED)

    guest_verified = _guest_stop_verified(guest, verdict)
    if guest_verified:
        stages.append(HostLifecycleStage.GUEST_QUIESCENCE_VERIFIED)
    else:
        stages.append(HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED)
        if LifecycleFailure.GUEST_STOP_UNVERIFIED not in failures:
            failures.append(LifecycleFailure.GUEST_STOP_UNVERIFIED)

    before_shutdown = request.host_control.observe(identity)
    pre_shutdown_failures = verify_host_running(identity, before_shutdown)
    if (
        initial is None
        or before_shutdown is None
        or initial.restart_epoch != before_shutdown.restart_epoch
    ):
        pre_shutdown_failures = (*pre_shutdown_failures, HostFailureCode.VM_RESTARTED)
    if pre_shutdown_failures:
        return _failed(
            tuple((*failures, LifecycleFailure.HOST_IDENTITY_CHANGED,
                   *pre_shutdown_failures)), tuple(stages), verdict,
        )

    stages.append(HostLifecycleStage.VM_STOP_REQUESTED)
    if not request.host_control.request_graceful_shutdown(identity):
        return _failed(
            tuple((*failures, LifecycleFailure.VM_SHUTDOWN_REQUEST_FAILED)),
            tuple(stages), verdict,
        )
    after_shutdown = request.host_control.wait_for_stopped(
        identity, timeout_seconds=VM_SHUTDOWN_TIMEOUT_SECONDS,
    )
    isolation = verify_host_isolation(
        identity,
        HostStopObservations(initial, before_shutdown, after_shutdown),
    )
    if isolation.vm_stopped_observed:
        stages.append(HostLifecycleStage.VM_STOPPED_OBSERVED)
    if not isolation.verified:
        return _failed(
            tuple((*failures, LifecycleFailure.VM_ISOLATION_UNVERIFIED,
                   *isolation.failures)), tuple(stages), verdict, isolation,
        )
    stages.append(HostLifecycleStage.VM_ISOLATION_VERIFIED)

    preservation_evidence = request.preserver.preserve(identity, authority, isolation)
    if preservation_evidence is None:
        return _failed(
            tuple((*failures, LifecycleFailure.PRESERVATION_UNAVAILABLE)),
            tuple(stages), verdict, isolation,
        )
    expectation = PreservationExpectation(
        authority.key, authority.receipt_sha256, authority.manifest_sha256,
        authority.manifest.baseline,
    )
    preservation = evaluate_offline_preservation(
        expectation, identity, preservation_evidence,
    )
    if preservation.disposition is PreservationDisposition.VERIFIED:
        stages.append(HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED)
    elif preservation.disposition is PreservationDisposition.CONDITIONALLY_ACCEPTED:
        stages.append(HostLifecycleStage.OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED)
    elif preservation.disposition is PreservationDisposition.MISMATCH:
        failures.append(LifecycleFailure.PRESERVATION_MISMATCH)
    else:
        failures.append(LifecycleFailure.PRESERVATION_UNVERIFIED)
    return HostControlledStopResult(
        tuple(stages), tuple(failures), verdict, isolation, preservation,
    )
