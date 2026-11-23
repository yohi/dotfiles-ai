from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from typing import TYPE_CHECKING, final

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_host_identity_provider as identity_provider
    import sandbox.scripts.oc2_host_provider as hp
    import sandbox.tests.oc2_host_lifecycle_test_support as fixtures
    from sandbox.scripts.oc2_writer import WriterSessionKey
else:
    import oc2_host_control as hc
    import oc2_host_identity_provider as identity_provider
    import oc2_host_lifecycle_test_support as fixtures
    import oc2_host_provider as hp


@final
class FakeFreshIdentityReader:
    def __init__(self, identity: hc.HostVmIdentity | None) -> None:
        self.identity = identity
        self.requested_keys: list[str] = []

    def capture(
        self, target: identity_provider.DirectQemuTarget, key: WriterSessionKey,
    ) -> hc.HostVmIdentity | None:
        self.requested_keys.append(key.session_generation)
        return self.identity


@final
class HostIdentityProviderTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: fixtures.HostFixture = fixtures.HostFixture.create(Path(temporary.name))

    def test_identity_is_captured_for_new_session_and_old_generation_is_rejected(self) -> None:
        f = self.fixture
        new_key = replace(f.key, session_generation=str(uuid.uuid4()))
        target = identity_provider.DirectQemuTarget(
            vm_id=f.host_identity.vm_id,
            vm_name=hp.DIRECT_QEMU_VM_NAME,
            disk_path=f.disk.path,
            ssh_forward_host=hp.SSH_HOST,
            ssh_forward_port=hp.SSH_PORT,
        )
        reader = FakeFreshIdentityReader(f.host_identity)

        identity = identity_provider.capture_direct_qemu_identity(
            target, new_key, reader,
        )

        self.assertIsNone(identity)
        self.assertEqual(reader.requested_keys, [new_key.session_generation])

    def test_fresh_pid_and_boot_identity_are_bound_to_new_session(self) -> None:
        f = self.fixture
        new_key = replace(f.key, session_generation=str(uuid.uuid4()))
        fresh = replace(
            f.host_identity,
            host_boot_id='new-boot-id',
            qemu_process=hc.HostProcessIdentity(987, 65432, 'f' * 64),
            session_key=new_key,
        )
        target = identity_provider.DirectQemuTarget(
            vm_id=fresh.vm_id,
            vm_name=hp.DIRECT_QEMU_VM_NAME,
            disk_path=fresh.disk.path,
            ssh_forward_host=hp.SSH_HOST,
            ssh_forward_port=hp.SSH_PORT,
        )

        identity = identity_provider.capture_direct_qemu_identity(
            target, new_key, FakeFreshIdentityReader(fresh),
        )

        if identity is None:
            self.fail('fresh Host identity missing')
        self.assertEqual(identity, fresh)
        self.assertEqual(identity.qemu_process.pid, 987)
        self.assertEqual(identity.host_boot_id, 'new-boot-id')

    def test_wrong_management_target_is_rejected_before_host_observation(self) -> None:
        f = self.fixture
        target = identity_provider.DirectQemuTarget(
            vm_id=f.host_identity.vm_id,
            vm_name='unknown-qemu-wrapper',
            disk_path=f.disk.path,
            ssh_forward_host=hp.SSH_HOST,
            ssh_forward_port=hp.SSH_PORT,
        )
        reader = FakeFreshIdentityReader(f.host_identity)

        identity = identity_provider.capture_direct_qemu_identity(
            target, f.key, reader,
        )

        self.assertIsNone(identity)
        self.assertEqual(reader.requested_keys, [])


if __name__ == '__main__':
    unittest.main()
