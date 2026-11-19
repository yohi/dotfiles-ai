from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sandbox.scripts.oc2_writer as w
else:
    import oc2_writer as w

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class HostDiskIdentity:
    path: str
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class HostProcessIdentity:
    pid: int
    start_ticks: int
    argv_sha256: str


@dataclass(frozen=True, slots=True)
class HostProcessReference:
    pid: int
    start_ticks: int


@dataclass(frozen=True, slots=True)
class HostVmIdentity:
    vm_id: str
    vm_name: str
    host_boot_id: str
    qemu_process: HostProcessIdentity
    disk: HostDiskIdentity
    session_key: w.WriterSessionKey
    ssh_forward_host: str
    ssh_forward_port: int


def host_disk_identity_valid(identity: HostDiskIdentity) -> bool:
    return (
        identity.path.startswith("/")
        and ".." not in PurePosixPath(identity.path).parts
        and type(identity.device) is int
        and identity.device >= 0
        and type(identity.inode) is int
        and identity.inode > 0
    )


def host_process_identity_valid(identity: HostProcessIdentity) -> bool:
    return (
        type(identity.pid) is int
        and identity.pid > 0
        and type(identity.start_ticks) is int
        and identity.start_ticks > 0
        and _SHA256.fullmatch(identity.argv_sha256) is not None
    )


def host_vm_identity_valid(identity: HostVmIdentity) -> bool:
    if (
        not identity.vm_id
        or not identity.vm_name
        or not identity.host_boot_id
        or not identity.ssh_forward_host
        or type(identity.ssh_forward_port) is not int
        or not 1 <= identity.ssh_forward_port <= 65535
        or not host_disk_identity_valid(identity.disk)
        or not host_process_identity_valid(identity.qemu_process)
    ):
        return False
    try:
        identity.session_key.validate()
    except w.WriterError:
        return False
    return True
