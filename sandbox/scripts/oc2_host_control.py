from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_identity import (
        HostDiskIdentity,
        HostProcessIdentity,
        HostProcessReference,
        HostVmIdentity,
        host_disk_identity_valid,
        host_process_identity_valid,
        host_vm_identity_valid,
    )
else:
    from oc2_host_identity import (
        HostDiskIdentity,
        HostProcessIdentity,
        HostProcessReference,
        HostVmIdentity,
        host_disk_identity_valid,
        host_process_identity_valid,
        host_vm_identity_valid,
    )

__all__ = (
    "AutostartPolicy",
    "HostDiskIdentity",
    "HostFailureCode",
    "HostIsolationResult",
    "HostObservation",
    "HostProcessIdentity",
    "HostProcessReference",
    "HostStopObservations",
    "HostVmControl",
    "HostVmIdentity",
    "HostVmState",
    "verify_host_isolation",
    "verify_host_running",
)


@unique
class HostVmState(StrEnum):
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@unique
class AutostartPolicy(StrEnum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    UNKNOWN = "unknown"


@unique
class HostFailureCode(StrEnum):
    UNSUPPORTED_MANAGEMENT_MODE = "unsupported-management-mode"
    INVALID_IDENTITY = "invalid-host-identity"
    OBSERVATION_UNAVAILABLE = "host-observation-unavailable"
    VM_IDENTITY_MISMATCH = "vm-identity-mismatch"
    VM_STATE_UNEXPECTED = "vm-state-unexpected"
    QEMU_IDENTITY_MISMATCH = "qemu-identity-mismatch"
    QEMU_REMAINS = "qemu-remains"
    QEMU_INVENTORY_INCOMPLETE = "qemu-inventory-incomplete"
    PID_REUSED_OR_UNKNOWN = "qemu-pid-reused-or-unknown"
    DISK_IDENTITY_MISMATCH = "disk-identity-mismatch"
    DISK_OPENERS_UNKNOWN = "disk-openers-unknown"
    DISK_OPENERS_PRESENT = "disk-openers-present"
    SSH_FORWARD_IDENTITY_MISMATCH = "ssh-forward-identity-mismatch"
    SSH_FORWARD_UNKNOWN = "ssh-forward-unknown"
    SSH_FORWARD_ABSENT = "ssh-forward-absent"
    SSH_FORWARD_PRESENT = "ssh-forward-present"
    AUTOSTART_NOT_DISABLED = "vm-autostart-not-disabled"
    RESTART_AUDIT_INCOMPLETE = "restart-audit-incomplete"
    VM_RESTARTED = "vm-restarted-during-audit"
    SHARED_WRITE_UNKNOWN = "shared-write-scope-unknown"
    SHARED_WRITE_POSSIBLE = "shared-write-possible"


@dataclass(frozen=True, slots=True)
class HostObservation:
    host_boot_id: str | None
    vm_id: str | None
    vm_name: str | None
    state: HostVmState
    qemu_process: HostProcessIdentity | None
    qemu_inventory_complete: bool | None
    expected_pid_start_ticks: int | None
    expected_pid_observation_complete: bool | None
    disk: HostDiskIdentity | None
    disk_openers: tuple[HostProcessReference, ...] | None
    disk_openers_complete: bool | None
    ssh_forward_host: str | None
    ssh_forward_port: int | None
    ssh_forward_listener_present: bool | None
    autostart_policy: AutostartPolicy
    restart_epoch: int | None
    restart_audit_complete: bool | None
    shared_write_possible: bool | None
    shared_write_scope_complete: bool | None
    processes_scanned: int | None = None
    unreadable_processes: int | None = None


class HostVmControl(Protocol):
    """Host-trusted VM control; implementations expose graceful shutdown only."""

    def configuration_failure(self) -> HostFailureCode | None: ...

    def observe(self, identity: HostVmIdentity) -> HostObservation | None: ...

    def request_graceful_shutdown(self, identity: HostVmIdentity) -> bool: ...

    def wait_for_stopped(self, identity: HostVmIdentity, *, timeout_seconds: int
                         ) -> HostObservation | None: ...


@dataclass(frozen=True, slots=True)
class HostStopObservations:
    before_guest_stop: HostObservation | None
    before_vm_shutdown: HostObservation | None
    after_vm_shutdown: HostObservation | None


@dataclass(frozen=True, slots=True)
class HostIsolationResult:
    vm_stopped_observed: bool
    verified: bool
    failures: tuple[HostFailureCode, ...]


def _binding_failures(
    identity: HostVmIdentity, observation: HostObservation | None,
) -> list[HostFailureCode]:
    if observation is None:
        return [HostFailureCode.OBSERVATION_UNAVAILABLE]
    failures: list[HostFailureCode] = []
    if ((observation.host_boot_id, observation.vm_id, observation.vm_name)
            != (identity.host_boot_id, identity.vm_id, identity.vm_name)):
        failures.append(HostFailureCode.VM_IDENTITY_MISMATCH)
    if observation.disk != identity.disk:
        failures.append(HostFailureCode.DISK_IDENTITY_MISMATCH)
    if observation.disk is not None and not host_disk_identity_valid(observation.disk):
        failures.append(HostFailureCode.DISK_IDENTITY_MISMATCH)
    if (observation.ssh_forward_host != identity.ssh_forward_host
            or observation.ssh_forward_port != identity.ssh_forward_port):
        failures.append(HostFailureCode.SSH_FORWARD_IDENTITY_MISMATCH)
    if observation.qemu_inventory_complete is not True:
        failures.append(HostFailureCode.QEMU_INVENTORY_INCOMPLETE)
    if (observation.qemu_process is not None
            and not host_process_identity_valid(observation.qemu_process)):
        failures.append(HostFailureCode.QEMU_IDENTITY_MISMATCH)
    if observation.expected_pid_observation_complete is not True:
        failures.append(HostFailureCode.PID_REUSED_OR_UNKNOWN)
    if observation.autostart_policy is not AutostartPolicy.DISABLED:
        failures.append(HostFailureCode.AUTOSTART_NOT_DISABLED)
    epoch_valid = (
        type(observation.restart_epoch) is int and observation.restart_epoch >= 0
    )
    if observation.restart_audit_complete is not True or not epoch_valid:
        failures.append(HostFailureCode.RESTART_AUDIT_INCOMPLETE)
    if observation.shared_write_scope_complete is not True:
        failures.append(HostFailureCode.SHARED_WRITE_UNKNOWN)
    elif observation.shared_write_possible is None:
        failures.append(HostFailureCode.SHARED_WRITE_UNKNOWN)
    elif observation.shared_write_possible:
        failures.append(HostFailureCode.SHARED_WRITE_POSSIBLE)
    return failures


def verify_host_running(
    identity: HostVmIdentity, observation: HostObservation | None,
) -> tuple[HostFailureCode, ...]:
    if not host_vm_identity_valid(identity):
        return (HostFailureCode.INVALID_IDENTITY,)
    failures = _binding_failures(identity, observation)
    failures = [failure for failure in failures if failure not in {
        HostFailureCode.AUTOSTART_NOT_DISABLED,
        HostFailureCode.RESTART_AUDIT_INCOMPLETE,
        HostFailureCode.SHARED_WRITE_UNKNOWN,
    }]
    if observation is None:
        return tuple(dict.fromkeys(failures))
    if observation.state is not HostVmState.RUNNING:
        failures.append(HostFailureCode.VM_STATE_UNEXPECTED)
    if observation.qemu_process != identity.qemu_process:
        failures.append(HostFailureCode.QEMU_IDENTITY_MISMATCH)
    if (type(observation.expected_pid_start_ticks) is not int
            or observation.expected_pid_start_ticks != identity.qemu_process.start_ticks):
        failures.append(HostFailureCode.PID_REUSED_OR_UNKNOWN)
    if observation.ssh_forward_listener_present is None:
        failures.append(HostFailureCode.SSH_FORWARD_UNKNOWN)
    elif not observation.ssh_forward_listener_present:
        failures.append(HostFailureCode.SSH_FORWARD_ABSENT)
    expected_openers = (HostProcessReference(identity.qemu_process.pid,
                                               identity.qemu_process.start_ticks),)
    if observation.disk_openers_complete is not True or observation.disk_openers is None:
        failures.append(HostFailureCode.DISK_OPENERS_UNKNOWN)
    elif any(type(opener.pid) is not int or type(opener.start_ticks) is not int
             for opener in observation.disk_openers):
        failures.append(HostFailureCode.DISK_OPENERS_UNKNOWN)
    elif observation.disk_openers != expected_openers:
        failures.append(HostFailureCode.DISK_OPENERS_PRESENT)
    return tuple(dict.fromkeys(failures))


def _stopped_failures(
    identity: HostVmIdentity,
    observation: HostObservation | None,
    restart_epoch: int | None,
) -> list[HostFailureCode]:
    failures = _binding_failures(identity, observation)
    if observation is None:
        return failures
    if observation.state is not HostVmState.STOPPED:
        failures.append(HostFailureCode.VM_STATE_UNEXPECTED)
    if observation.qemu_process is not None:
        failures.append(HostFailureCode.QEMU_REMAINS)
    if observation.expected_pid_start_ticks is not None:
        failures.append(HostFailureCode.PID_REUSED_OR_UNKNOWN)
    if observation.ssh_forward_listener_present is None:
        failures.append(HostFailureCode.SSH_FORWARD_UNKNOWN)
    elif observation.ssh_forward_listener_present:
        failures.append(HostFailureCode.SSH_FORWARD_PRESENT)
    if observation.disk_openers_complete is not True or observation.disk_openers is None:
        failures.append(HostFailureCode.DISK_OPENERS_UNKNOWN)
    elif observation.disk_openers:
        failures.append(HostFailureCode.DISK_OPENERS_PRESENT)
    if restart_epoch is None or observation.restart_epoch is None:
        failures.append(HostFailureCode.RESTART_AUDIT_INCOMPLETE)
    elif observation.restart_epoch != restart_epoch:
        failures.append(HostFailureCode.VM_RESTARTED)
    return failures


def verify_host_isolation(
    identity: HostVmIdentity,
    observations: HostStopObservations,
) -> HostIsolationResult:
    """Verify stable Host VM identity, shutdown, no openers, and no restart."""
    if not host_vm_identity_valid(identity):
        return HostIsolationResult(False, False, (HostFailureCode.INVALID_IDENTITY,))
    initial = observations.before_guest_stop
    before_shutdown = observations.before_vm_shutdown
    after_shutdown = observations.after_vm_shutdown
    failures = list(verify_host_running(identity, initial))
    failures.extend(verify_host_running(identity, before_shutdown))
    restart_epoch = initial.restart_epoch if initial is not None else None
    if (initial is not None and before_shutdown is not None
            and initial.restart_epoch != before_shutdown.restart_epoch):
        failures.append(HostFailureCode.VM_RESTARTED)
    failures.extend(_stopped_failures(identity, after_shutdown, restart_epoch))
    stopped = bool(
        after_shutdown is not None
        and after_shutdown.host_boot_id == identity.host_boot_id
        and after_shutdown.vm_id == identity.vm_id
        and after_shutdown.vm_name == identity.vm_name
        and after_shutdown.disk == identity.disk
        and after_shutdown.state is HostVmState.STOPPED
        and after_shutdown.qemu_process is None
        and after_shutdown.qemu_inventory_complete is True
        and after_shutdown.expected_pid_observation_complete is True
        and after_shutdown.expected_pid_start_ticks is None
    )
    unique_failures = tuple(dict.fromkeys(failures))
    return HostIsolationResult(stopped, not unique_failures, unique_failures)
