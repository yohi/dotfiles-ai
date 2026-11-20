from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import pwd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import (
        AutostartPolicy,
        HostDiskIdentity,
        HostObservation,
        HostProcessIdentity,
        HostProcessReference,
        HostVmIdentity,
        HostVmState,
    )
    from sandbox.scripts.oc2_host_identity_provider import DirectQemuTarget
    from sandbox.scripts.oc2_host_config import DIRECT_QEMU_VM_NAME, SSH_HOST
    from sandbox.scripts.oc2_procfs_scan import (
        ProcfsReadError,
        matches_qemu,
        parse_start_ticks,
        proc_pid_name,
        read_status_uid,
        scan_process_fds,
        ssh_listener_inodes,
    )
    from sandbox.scripts.oc2_writer import WriterSessionKey
else:
    from oc2_host_control import (
        AutostartPolicy,
        HostDiskIdentity,
        HostObservation,
        HostProcessIdentity,
        HostProcessReference,
        HostVmIdentity,
        HostVmState,
    )
    from oc2_writer import WriterSessionKey
    from oc2_host_config import DIRECT_QEMU_VM_NAME, SSH_HOST
    from oc2_procfs_scan import (
        ProcfsReadError,
        matches_qemu,
        parse_start_ticks,
        proc_pid_name,
        read_status_uid,
        scan_process_fds,
        ssh_listener_inodes,
    )


@dataclass(frozen=True, slots=True)
class ProcfsRootObservationHelper:
    proc_root: Path = Path('/proc')
    qemu_owner_name: str = 'y_ohi'

    def capture(
        self, target: DirectQemuTarget, key: WriterSessionKey,
    ) -> HostVmIdentity | None:
        """Capture a fresh QEMU identity only when process, disk, and listener evidence agree."""
        if target.vm_name != DIRECT_QEMU_VM_NAME or target.ssh_forward_host != SSH_HOST:
            return None
        try:
            boot_id = (self.proc_root / 'sys/kernel/random/boot_id').read_text().strip()
            disk_stat = Path(target.disk_path).stat(follow_symlinks=False)
        except OSError:
            return None
        disk = HostDiskIdentity(target.disk_path, disk_stat.st_dev, disk_stat.st_ino)
        provisional = HostVmIdentity(
            target.vm_id, target.vm_name, boot_id,
            HostProcessIdentity(1, 1, '0' * 64), disk, key,
            target.ssh_forward_host, target.ssh_forward_port,
        )
        observation = self.read(provisional)
        if (
            observation is None
            or observation.state is not HostVmState.RUNNING
            or observation.qemu_process is None
            or observation.qemu_inventory_complete is not True
            or observation.disk_openers_complete is not True
            or observation.processes_scanned is None
            or observation.unreadable_processes != 0
            or observation.ssh_forward_listener_present is not True
            or observation.disk_openers != (
                HostProcessReference(
                    observation.qemu_process.pid,
                    observation.qemu_process.start_ticks,
                ),
            )
        ):
            return None
        return HostVmIdentity(
            target.vm_id, target.vm_name, observation.host_boot_id or '',
            observation.qemu_process, observation.disk or disk, key,
            target.ssh_forward_host, target.ssh_forward_port,
        )

    def read(self, identity: HostVmIdentity) -> HostObservation | None:
        """Observe procfs process, disk opener, and listener state for this Host identity."""
        if os.geteuid() != 0:
            return None
        try:
            boot_id = (self.proc_root / 'sys/kernel/random/boot_id').read_text().strip()
            disk_stat = Path(identity.disk.path).stat(follow_symlinks=False)
            expected_qemu_uid = pwd.getpwnam(self.qemu_owner_name).pw_uid
        except (OSError, KeyError):
            return None
        disk = type(identity.disk)(identity.disk.path, disk_stat.st_dev, disk_stat.st_ino)
        complete = disk == identity.disk
        qemu_matches: list[HostProcessIdentity] = []
        openers: list[HostProcessReference] = []
        process_socket_fds: dict[int, frozenset[str]] = {}
        unreadable = 0
        scanned = 0
        expected_pid_ticks: int | None = None
        listener_inodes = ssh_listener_inodes(
            self.proc_root / 'net/tcp', identity.ssh_forward_port,
        )
        if listener_inodes is None:
            complete = False

        try:
            entries = tuple(self.proc_root.iterdir())
        except OSError:
            return None
        for process_dir in entries:
            if not proc_pid_name(process_dir.name) or not process_dir.is_dir():
                continue
            scanned += 1
            try:
                pid = int(process_dir.name)
                stat_text = (process_dir / 'stat').read_text()
                start_ticks = parse_start_ticks(stat_text)
                status = read_status_uid(process_dir / 'status')
                argv = (process_dir / 'cmdline').read_bytes()
                arguments = tuple(part.decode(errors='replace') for part in argv.split(b'\0') if part)
                if pid == identity.qemu_process.pid:
                    expected_pid_ticks = start_ticks
                if matches_qemu(
                    arguments, identity.vm_name, identity.disk.path,
                    identity.ssh_forward_host, identity.ssh_forward_port,
                ):
                    if status != expected_qemu_uid:
                        complete = False
                    qemu_matches.append(HostProcessIdentity(
                        pid, start_ticks, hashlib.sha256(argv).hexdigest(),
                    ))
                complete_fds, socket_fds = scan_process_fds(
                    process_dir / 'fd', disk_stat, openers,
                    HostProcessReference(pid, start_ticks),
                )
                if socket_fds:
                    process_socket_fds[pid] = socket_fds
                if not complete_fds:
                    unreadable += 1
            except (OSError, ProcfsReadError, UnicodeError, ValueError):
                unreadable += 1

        if len(qemu_matches) > 1:
            complete = False
        complete = complete and unreadable == 0
        state = HostVmState.RUNNING if qemu_matches else HostVmState.STOPPED
        qemu_process = qemu_matches[0] if len(qemu_matches) == 1 else None
        listener: bool | None
        if listener_inodes is None:
            listener = None
        elif not listener_inodes:
            listener = False
        elif qemu_process is None:
            listener = True
        else:
            listener = bool(listener_inodes & process_socket_fds.get(qemu_process.pid, frozenset()))
        return HostObservation(
            host_boot_id=boot_id,
            vm_id=identity.vm_id,
            vm_name=identity.vm_name,
            state=state,
            qemu_process=qemu_process,
            qemu_inventory_complete=complete,
            expected_pid_start_ticks=expected_pid_ticks,
            expected_pid_observation_complete=expected_pid_ticks is not None or state is HostVmState.STOPPED,
            disk=disk,
            disk_openers=tuple(sorted(openers, key=lambda item: (item.pid, item.start_ticks))),
            disk_openers_complete=complete,
            ssh_forward_host=identity.ssh_forward_host,
            ssh_forward_port=identity.ssh_forward_port,
            ssh_forward_listener_present=listener,
            autostart_policy=AutostartPolicy.UNKNOWN,
            restart_epoch=None,
            restart_audit_complete=False,
            shared_write_possible=None,
            shared_write_scope_complete=False,
            processes_scanned=scanned,
            unreadable_processes=unreadable,
        )
