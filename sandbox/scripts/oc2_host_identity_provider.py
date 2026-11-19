from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import HostVmIdentity
    from sandbox.scripts.oc2_host_identity import host_vm_identity_valid
    from sandbox.scripts.oc2_host_config import DIRECT_QEMU_VM_NAME, SSH_HOST, SSH_PORT
    from sandbox.scripts.oc2_writer import WriterSessionKey
else:
    from oc2_host_control import HostVmIdentity
    from oc2_host_identity import host_vm_identity_valid
    from oc2_host_config import DIRECT_QEMU_VM_NAME, SSH_HOST, SSH_PORT
    from oc2_writer import WriterSessionKey


@dataclass(frozen=True, slots=True)
class DirectQemuTarget:
    vm_id: str
    vm_name: str
    disk_path: str
    ssh_forward_host: str
    ssh_forward_port: int


class FreshHostIdentityReader(Protocol):
    def capture(
        self, target: DirectQemuTarget, key: WriterSessionKey,
    ) -> HostVmIdentity | None: ...


def capture_direct_qemu_identity(
    target: DirectQemuTarget,
    key: WriterSessionKey,
    reader: FreshHostIdentityReader,
) -> HostVmIdentity | None:
    if (
        not target.vm_id
        or target.vm_name != DIRECT_QEMU_VM_NAME
        or not target.disk_path.startswith('/')
        or '..' in PurePosixPath(target.disk_path).parts
        or target.ssh_forward_host != SSH_HOST
        or target.ssh_forward_port != SSH_PORT
    ):
        return None
    identity = reader.capture(target, key)
    if (
        identity is None
        or identity.session_key != key
        or identity.vm_id != target.vm_id
        or identity.vm_name != target.vm_name
        or identity.disk.path != target.disk_path
        or identity.ssh_forward_host != target.ssh_forward_host
        or identity.ssh_forward_port != target.ssh_forward_port
        or not host_vm_identity_valid(identity)
    ):
        return None
    return identity
