from __future__ import annotations

from dataclasses import dataclass
import pathlib
import sys
import uuid
from typing import TYPE_CHECKING, final

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_host_lifecycle as lifecycle
    import sandbox.scripts.oc2_offline_preservation as op
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_slice_b_session import VerifiedGuestAuthority
    from sandbox.scripts.oc2_supervisor import SupervisorState
    from sandbox.tests.oc2_slice_b_test_support import make_verified_authority
else:
    import oc2_host_control as hc
    import oc2_host_lifecycle as lifecycle
    import oc2_offline_preservation as op
    import oc2_slice_b_test_support
    import oc2_writer as w
    from oc2_slice_b_session import VerifiedGuestAuthority
    from oc2_supervisor import SupervisorState


@final
class FakeGuestStopper:
    def __init__(self, key: w.WriterSessionKey, identity: w.WriterIdentity,
                 authority: VerifiedGuestAuthority, events: list[str], *,
                 stop_verdict: w.StopVerdict | None = None) -> None:
        self.session_key: w.WriterSessionKey = key
        self.identity: w.WriterIdentity = identity
        self.authority: VerifiedGuestAuthority = authority
        self.state: SupervisorState = SupervisorState.RUNNING
        self.events: list[str] = events
        self.stop_verdict: w.StopVerdict = stop_verdict or w.StopVerdict(
            w.STATUS_STOPPED_VERIFIED,
        )

    def authority_is_bound(self, authority: VerifiedGuestAuthority) -> bool:
        return authority is self.authority

    def stop(self, identity: w.WriterIdentity | None = None) -> w.StopVerdict:
        if identity is not None and identity != self.identity:
            raise AssertionError('unexpected Writer identity')
        self.events.append('guest.stop')
        self.state = (SupervisorState.STOPPED_VERIFIED if self.stop_verdict.verified
                      else SupervisorState.UNVERIFIED)
        return self.stop_verdict


@final
class FakeHostControl:
    def __init__(self, observations: tuple[hc.HostObservation | None, ...],
                 events: list[str], *, request_ok: bool = True) -> None:
        self.observations: list[hc.HostObservation | None] = list(observations)
        self.events: list[str] = events
        self.request_ok: bool = request_ok

    def configuration_failure(self) -> hc.HostFailureCode | None:
        return None

    def observe(self, identity: hc.HostVmIdentity) -> hc.HostObservation | None:
        if not identity.vm_id:
            raise AssertionError('Host VM identity missing')
        self.events.append('host.observe')
        return self.observations.pop(0)

    def request_graceful_shutdown(self, identity: hc.HostVmIdentity) -> bool:
        if not identity.vm_id:
            raise AssertionError('Host VM identity missing')
        self.events.append('host.shutdown')
        return self.request_ok

    def wait_for_stopped(
        self, identity: hc.HostVmIdentity, *, timeout_seconds: int,
    ) -> hc.HostObservation | None:
        if not identity.vm_id or timeout_seconds <= 0:
            raise AssertionError('invalid bounded Host wait request')
        self.events.append('host.wait')
        return self.observations.pop(0)


@final
class FakePreserver:
    def __init__(self, evidence: op.OfflinePreservationEvidence,
                 events: list[str]) -> None:
        self.evidence: op.OfflinePreservationEvidence = evidence
        self.events: list[str] = events

    def preserve(
        self,
        identity: hc.HostVmIdentity,
        authority: VerifiedGuestAuthority,
        isolation: hc.HostIsolationResult,
    ) -> op.OfflinePreservationEvidence | None:
        if identity.session_key != authority.key or not isolation.verified:
            raise AssertionError('preservation must be behind bound Host isolation')
        self.events.append('preserve')
        return self.evidence


@dataclass(frozen=True, slots=True)
class HostFixture:
    root: pathlib.Path
    key: w.WriterSessionKey
    authority: VerifiedGuestAuthority
    writer: w.WriterIdentity
    disk: hc.HostDiskIdentity
    qemu: hc.HostProcessIdentity
    host_identity: hc.HostVmIdentity

    @classmethod
    def create(cls, root: pathlib.Path) -> HostFixture:
        key = w.WriterSessionKey('a' * 32, str(uuid.uuid4()), str(uuid.uuid4()))
        authority: VerifiedGuestAuthority
        if TYPE_CHECKING:
            authority = make_verified_authority(root / 'authority', key)
        else:
            authority = oc2_slice_b_test_support.make_verified_authority(
                root / 'authority', key,
            )
        writer = w.WriterIdentity('b' * 64, authority.image_config_id,
                                  '2026-11-19T00:00:00Z', 101, 'host-boot')
        disk = hc.HostDiskIdentity('/vm/recovery.qcow2', 77, 88)
        qemu = hc.HostProcessIdentity(901, 12345, 'c' * 64)
        host_identity = hc.HostVmIdentity(
            'vm-uuid', 'oc2-f002-probe-recovery', 'host-boot', qemu, disk,
            key, '127.0.0.1', 2223,
        )
        return cls(root, key, authority, writer, disk, qemu, host_identity)

    def observation(self, *, stopped: bool = False) -> hc.HostObservation:
        return hc.HostObservation(
            host_boot_id='host-boot', vm_id='vm-uuid', vm_name=self.host_identity.vm_name,
            state=hc.HostVmState.STOPPED if stopped else hc.HostVmState.RUNNING,
            qemu_process=None if stopped else self.qemu,
            qemu_inventory_complete=True,
            expected_pid_start_ticks=None if stopped else self.qemu.start_ticks,
            expected_pid_observation_complete=True,
            disk=self.disk,
            disk_openers=() if stopped else (hc.HostProcessReference(901, 12345),),
            disk_openers_complete=True,
            ssh_forward_host='127.0.0.1',
            ssh_forward_port=2223,
            ssh_forward_listener_present=not stopped,
            autostart_policy=hc.AutostartPolicy.DISABLED,
            restart_epoch=4,
            restart_audit_complete=True,
            shared_write_possible=False,
            shared_write_scope_complete=True,
            processes_scanned=803,
            unreadable_processes=0,
        )

    def preservation_evidence(self) -> op.OfflinePreservationEvidence:
        baseline = self.authority.manifest.baseline
        return op.OfflinePreservationEvidence(
            session_key=self.key,
            source_disk=self.disk,
            copy_disk=hc.HostDiskIdentity('/evidence/copy.qcow2', 77, 89),
            copy_destination_isolated=True,
            host_repository_unchanged=True,
            source_sha256='d' * 64,
            copy_sha256='d' * 64,
            qcow2_structure_verified=True,
            qcow2_logical_content_verified=True,
            guestfs_readonly=True,
            filesystem_state=op.FilesystemState.CLEAN_CHECKED,
            filesystem_repair_performed=False,
            receipt_sha256=self.authority.receipt_sha256,
            manifest_sha256=self.authority.manifest_sha256,
            session_artifacts_verified=True,
            repository_path='/guest/session/repo',
            branch_ref=baseline.branch_ref,
            head_oid=baseline.head_oid,
            tree_oid=baseline.tree_oid,
            object_format=baseline.object_format,
            index_sha256=baseline.index_sha256,
            index_structure_valid=True,
            worktree_sha256=baseline.worktree_sha256,
            object_database_valid=True,
            git_status_complete=True,
            git_dirty=False,
            tracked_file_count=1,
            untracked_file_count=0,
            export_manifest_sha256='e' * 64,
        )

    def make_request(
        self,
        observations: tuple[hc.HostObservation, ...],
        *,
        stop_verdict: w.StopVerdict | None = None,
        request_ok: bool = True,
        evidence: op.OfflinePreservationEvidence | None = None,
        authority: VerifiedGuestAuthority | None = None,
    ) -> tuple[lifecycle.HostControlledStopRequest, list[str], FakeGuestStopper]:
        events: list[str] = []
        guest = FakeGuestStopper(self.key, self.writer, self.authority, events,
                                 stop_verdict=stop_verdict)
        host = FakeHostControl(observations, events, request_ok=request_ok)
        preserver = FakePreserver(evidence or self.preservation_evidence(), events)
        request = lifecycle.HostControlledStopRequest(
            guest, authority or self.authority, self.writer, self.host_identity,
            host, preserver,
        )
        return request, events, guest
