from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from typing import TYPE_CHECKING, final
from unittest import mock
import uuid

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_host_identity_provider as identity_provider
    import sandbox.scripts.oc2_host_provider as hp
    import sandbox.scripts.oc2_root_observer as root_observer
    import sandbox.scripts.oc2_writer as w
    from sandbox.tests.oc2_host_lifecycle_test_support import HostFixture
else:
    import oc2_host_control as hc
    import oc2_host_identity_provider as identity_provider
    import oc2_host_provider as hp
    import oc2_root_observer as root_observer
    import oc2_writer as w
    from oc2_host_lifecycle_test_support import HostFixture


@dataclass(frozen=True, slots=True)
class ProcfsFixture:
    helper: root_observer.ProcfsRootObservationHelper
    identity: hc.HostVmIdentity
    target: identity_provider.DirectQemuTarget
    process: Path
    argv: bytes
    new_key: w.WriterSessionKey


def build_procfs_fixture(fixture: HostFixture) -> ProcfsFixture:
    """Build isolated procfs evidence for process, listener, and session assertions."""
    proc_root = fixture.root / f'proc-{uuid.uuid4()}'
    process = proc_root / '123'
    (proc_root / 'sys/kernel/random').mkdir(parents=True)
    (process / 'fd').mkdir(parents=True)
    (proc_root / 'net').mkdir()
    source = fixture.root / f'recovered-{uuid.uuid4()}.qcow2'
    source.write_bytes(b'disk fixture')
    source_stat = source.stat()
    argv = (
        b'/usr/bin/qemu-system-x86_64\0-name\0oc2-f002-probe-recovery\0'
        + b'-drive\0file=' + str(source).encode() + b',if=virtio\0'
        + b'-netdev\0user,id=net0,hostfwd=tcp:127.0.0.1:2223-:22\0'
    )
    stat_fields = ['S', *(['0'] * 18), '12345']
    (proc_root / 'sys/kernel/random/boot_id').write_text('fresh-boot-id\n')
    (process / 'stat').write_text(f'123 (qemu-system-x86_64) {" ".join(stat_fields)}\n')
    (process / 'status').write_text('Name:\tqemu\nUid:\t0\t0\t0\t0\n')
    (process / 'cmdline').write_bytes(argv)
    (process / 'fd/3').symlink_to(source)
    (process / 'fd/4').symlink_to('socket:[98765]')
    (proc_root / 'net/tcp').write_text(
        'sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
        '0: 0100007F:08AF 00000000:0000 0A 0 0 0 1 0 98765\n',
    )
    identity = replace(
        fixture.host_identity,
        host_boot_id='fresh-boot-id',
        qemu_process=hc.HostProcessIdentity(123, 12345, hashlib.sha256(argv).hexdigest()),
        disk=hc.HostDiskIdentity(str(source), source_stat.st_dev, source_stat.st_ino),
    )
    target = identity_provider.DirectQemuTarget(
        vm_id=identity.vm_id,
        vm_name=identity.vm_name,
        disk_path=identity.disk.path,
        ssh_forward_host=identity.ssh_forward_host,
        ssh_forward_port=identity.ssh_forward_port,
    )
    return ProcfsFixture(
        root_observer.ProcfsRootObservationHelper(proc_root, qemu_owner_name='root'),
        identity, target, process, argv,
        replace(fixture.key, session_generation=str(uuid.uuid4())),
    )


@final
class FakeRootHelper:
    def __init__(self, observation: hc.HostObservation | None) -> None:
        self.observation = observation

    def read(self, identity: hc.HostVmIdentity) -> hc.HostObservation | None:
        if not identity.vm_id:
            raise AssertionError('Host identity missing')
        return self.observation


@final
class RootObservationProviderTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: HostFixture = HostFixture.create(Path(temporary.name))

    def test_incomplete_root_observation_is_unknown(self) -> None:
        f = self.fixture
        unknown = replace(
            f.observation(), qemu_inventory_complete=None,
            disk_openers_complete=None, expected_pid_observation_complete=None,
        )
        observer = hp.RootObservationProvider(FakeRootHelper(unknown))

        observed = observer.observe(f.host_identity)

        self.assertIsNone(observed)

    def test_complete_snapshot_keeps_unproven_exclusion_controls_unknown(self) -> None:
        f = self.fixture
        observer = hp.RootObservationProvider(
            FakeRootHelper(f.observation(stopped=True)),
        )

        observed = observer.observe(f.host_identity)

        self.assertIsNotNone(observed)
        if observed is None:
            self.fail('root observation missing')
        self.assertIs(observed.autostart_policy, hc.AutostartPolicy.UNKNOWN)
        self.assertFalse(observed.restart_audit_complete)
        self.assertFalse(observed.shared_write_scope_complete)
        self.assertIsNone(observed.shared_write_possible)

    def test_procfs_helper_captures_normal_identity_and_listener_ownership(self) -> None:
        """Verify ordinary identity, disk opener, and listener observations together."""
        fixture = build_procfs_fixture(self.fixture)

        with mock.patch.object(os, 'geteuid', return_value=0):
            observation = fixture.helper.read(fixture.identity)

        self.assertIsNotNone(observation)
        if observation is None or observation.qemu_process is None:
            self.fail('procfs process observation missing')
        self.assertEqual(observation.qemu_process.pid, 123)
        self.assertEqual(observation.disk_openers, (hc.HostProcessReference(123, 12345),))
        self.assertTrue(observation.ssh_forward_listener_present)

    def test_procfs_helper_counts_malformed_process_records_as_unreadable(self) -> None:
        for record in ('stat', 'status'):
            with self.subTest(record=record):
                current = build_procfs_fixture(self.fixture)
                if record == 'stat':
                    current.process.joinpath('stat').write_text(
                        '123 (truncated process record', encoding='ascii',
                    )
                else:
                    current.process.joinpath('status').write_text(
                        'Uid:\n', encoding='ascii',
                    )

                with mock.patch.object(os, 'geteuid', return_value=0):
                    observation = current.helper.read(current.identity)

                self.assertIsNotNone(observation)
                if observation is None:
                    self.fail('procfs observation missing')
                self.assertEqual(observation.unreadable_processes, 1)

    def test_procfs_helper_captures_new_session_identity(self) -> None:
        """Verify capture binds a freshly observed QEMU identity to the requested session."""
        fixture = build_procfs_fixture(self.fixture)

        with mock.patch.object(os, 'geteuid', return_value=0):
            captured = fixture.helper.capture(fixture.target, fixture.new_key)

        self.assertIsNotNone(captured)
        if captured is None:
            self.fail('fresh Host identity missing')
        self.assertEqual(captured.session_key, fixture.new_key)
        self.assertEqual(captured.qemu_process.pid, 123)

    def test_procfs_helper_rejects_missing_host_forward(self) -> None:
        """Reject identity capture when the exact configured host-forward is absent."""
        fixture = build_procfs_fixture(self.fixture)
        fixture.process.joinpath('cmdline').write_bytes(
            fixture.argv.replace(b',hostfwd=tcp:127.0.0.1:2223-:22', b''),
        )

        with mock.patch.object(os, 'geteuid', return_value=0):
            captured = fixture.helper.capture(fixture.target, fixture.new_key)

        self.assertIsNone(captured)

    def test_procfs_helper_marks_socket_fd_absence_as_no_listener(self) -> None:
        """Treat a QEMU process without the observed socket FD as no owned listener."""
        fixture = build_procfs_fixture(self.fixture)
        fixture.process.joinpath('fd/4').unlink()

        with mock.patch.object(os, 'geteuid', return_value=0):
            observation = fixture.helper.read(fixture.identity)

        self.assertIsNotNone(observation)
        if observation is None:
            self.fail('procfs observation missing')
        self.assertFalse(observation.ssh_forward_listener_present)


if __name__ == '__main__':
    unittest.main()
