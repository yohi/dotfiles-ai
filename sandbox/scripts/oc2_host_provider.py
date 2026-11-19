from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import (
        HostObservation,
        HostFailureCode,
        HostVmIdentity,
        HostVmState,
        verify_host_running,
    )
    from sandbox.scripts.oc2_host_ssh import (
        CommandRunner,
        OpenSshPoweroff,
    )
    from sandbox.scripts.oc2_host_config import (
        DIRECT_QEMU_VM_NAME,
        HostProviderConfig,
        PINNED_HOST_KEY_FINGERPRINT,
        SSH_HOST,
        SSH_PORT,
        SSH_USER,
    )
else:
    from oc2_host_control import (
        HostObservation,
        HostFailureCode,
        HostVmState,
        HostVmIdentity,
        verify_host_running,
    )
    from oc2_host_ssh import CommandRunner, OpenSshPoweroff
    from oc2_host_config import (
        DIRECT_QEMU_VM_NAME,
        HostProviderConfig,
        PINNED_HOST_KEY_FINGERPRINT,
        SSH_HOST,
        SSH_PORT,
        SSH_USER,
    )

__all__ = (
    'DIRECT_QEMU_VM_NAME',
    'DirectQemuHostEffects',
    'DirectQemuHostVmControl',
    'HostProviderConfig',
    'OpenSshPoweroff',
    'PINNED_HOST_KEY_FINGERPRINT',
    'RootObservationHelper',
    'RootObservationProvider',
    'SSH_HOST',
    'SSH_PORT',
    'SSH_USER',
    'build_direct_qemu_host_control',
)


class RootObservationHelper(Protocol):
    """Read a complete Host snapshot through a separately installed root helper."""

    def read(self, identity: HostVmIdentity) -> HostObservation | None: ...


class PinnedGuestShutdown(Protocol):
    """Send only the fixed graceful poweroff through a pinned SSH connection."""

    def poweroff(self, config: HostProviderConfig) -> bool: ...


class HostControlEffects(Protocol):
    def observe(self, identity: HostVmIdentity) -> HostObservation | None: ...

    def shutdown(self, config: HostProviderConfig) -> bool: ...

    def wait_stopped(
        self, identity: HostVmIdentity, *, timeout_seconds: int,
    ) -> HostObservation | None: ...


@dataclass(frozen=True, slots=True)
class DirectQemuHostEffects:
    config: HostProviderConfig
    observer: RootObservationProvider
    shutdown_client: PinnedGuestShutdown

    def observe(self, identity: HostVmIdentity) -> HostObservation | None:
        return self.observer.observe(identity)

    def shutdown(self, config: HostProviderConfig) -> bool:
        if config != self.config:
            return False
        return self.shutdown_client.poweroff(self.config)

    def wait_stopped(
        self, identity: HostVmIdentity, *, timeout_seconds: int,
    ) -> HostObservation | None:
        if timeout_seconds <= 0:
            return None
        deadline = time.monotonic() + min(timeout_seconds, 180)
        while True:
            observation = self.observe(identity)
            if (observation is not None
                    and observation.state is HostVmState.STOPPED
                    and observation.qemu_process is None
                    and observation.qemu_inventory_complete is True):
                return observation
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.25)


def build_direct_qemu_host_control(
    config: HostProviderConfig,
    helper: RootObservationHelper,
    command_runner: CommandRunner,
) -> DirectQemuHostVmControl:
    observer = RootObservationProvider(helper)
    shutdown = OpenSshPoweroff(command_runner)
    effects = DirectQemuHostEffects(config, observer, shutdown)
    return DirectQemuHostVmControl(config, effects)


@dataclass(frozen=True, slots=True)
class RootObservationProvider:
    helper: RootObservationHelper

    def observe(self, identity: HostVmIdentity) -> HostObservation | None:
        """Fail closed on partial root snapshots and unproven isolation controls."""
        observation = self.helper.read(identity)
        if observation is None:
            return None
        if (
            observation.host_boot_id is None
            or observation.disk is None
            or observation.qemu_inventory_complete is not True
            or observation.expected_pid_observation_complete is not True
            or observation.disk_openers_complete is not True
            or observation.disk_openers is None
            or type(observation.processes_scanned) is not int
            or observation.processes_scanned <= 0
            or observation.unreadable_processes != 0
        ):
            return None
        return replace(
            observation,
            autostart_policy=type(observation.autostart_policy).UNKNOWN,
            restart_audit_complete=False,
            shared_write_possible=None,
            shared_write_scope_complete=False,
        )


@dataclass(frozen=True, slots=True)
class DirectQemuHostVmControl:
    config: HostProviderConfig
    effects: HostControlEffects

    def _supported(self, identity: HostVmIdentity) -> bool:
        return (
            self.configuration_failure() is None
            and self.config.vm_name == identity.vm_name
            and self.config.ssh_host == SSH_HOST == identity.ssh_forward_host
            and self.config.ssh_port == SSH_PORT == identity.ssh_forward_port
            and self.config.ssh_user == SSH_USER
            and Path(self.config.private_key_path)
            == Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'
            and self.config.host_key_fingerprint == PINNED_HOST_KEY_FINGERPRINT
        )

    def configuration_failure(self) -> HostFailureCode | None:
        if self.config.management_mode != 'direct-qemu':
            return HostFailureCode.UNSUPPORTED_MANAGEMENT_MODE
        if (
            self.config.vm_name != DIRECT_QEMU_VM_NAME
            or self.config.ssh_host != SSH_HOST
            or self.config.ssh_port != SSH_PORT
            or self.config.ssh_user != SSH_USER
            or Path(self.config.private_key_path)
            != Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'
            or not self.config.known_hosts_path
            or self.config.host_key_fingerprint != PINNED_HOST_KEY_FINGERPRINT
        ):
            return HostFailureCode.INVALID_IDENTITY
        return None

    def observe(self, identity: HostVmIdentity) -> HostObservation | None:
        if not self._supported(identity):
            return None
        return self.effects.observe(identity)

    def request_graceful_shutdown(self, identity: HostVmIdentity) -> bool:
        if not self._supported(identity):
            return False
        if verify_host_running(identity, self.effects.observe(identity)):
            return False
        return self.effects.shutdown(self.config)

    def wait_for_stopped(
        self, identity: HostVmIdentity, *, timeout_seconds: int,
    ) -> HostObservation | None:
        if not self._supported(identity) or timeout_seconds <= 0:
            return None
        observation = self.effects.wait_stopped(
            identity, timeout_seconds=timeout_seconds,
        )
        if observation is None:
            return None
        if (
            observation.host_boot_id != identity.host_boot_id
            or observation.vm_id != identity.vm_id
            or observation.vm_name != identity.vm_name
            or observation.disk != identity.disk
            or observation.qemu_process is not None
            or observation.qemu_inventory_complete is not True
            or observation.expected_pid_observation_complete is not True
        ):
            return None
        return observation
