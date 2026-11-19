from __future__ import annotations

import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_control import HostProcessReference
else:
    from oc2_host_control import HostProcessReference

_PID_NAME = re.compile(r'[0-9]+\Z')
_QEMU_NAMES = frozenset({
    'qemu-system-x86_64', 'qemu-kvm', 'qemu-system-aarch64',
})


class ProcfsReadError(Exception):
    pass


def proc_pid_name(name: str) -> bool:
    return _PID_NAME.fullmatch(name) is not None


def parse_start_ticks(stat_text: str) -> int:
    closing = stat_text.rfind(')')
    fields = stat_text[closing + 2:].split()
    return int(fields[19])


def read_status_uid(status_path: Path) -> int:
    for line in status_path.read_text().splitlines():
        if line.startswith('Uid:'):
            return int(line.split()[1])
    raise ProcfsReadError


def matches_qemu(
    arguments: tuple[str, ...], vm_name: str, disk_path: str,
    ssh_host: str, ssh_port: int,
) -> bool:
    if not arguments or Path(arguments[0]).name not in _QEMU_NAMES:
        return False
    joined = '\0'.join(arguments)
    forward = f'hostfwd=tcp:{ssh_host}:{ssh_port}-:22'
    return vm_name in joined and disk_path in joined and forward in joined


def scan_process_fds(
    fd_dir: Path,
    disk_stat: os.stat_result,
    openers: list[HostProcessReference],
    process: HostProcessReference,
) -> tuple[bool, frozenset[str]]:
    try:
        fds = tuple(fd_dir.iterdir())
    except OSError:
        return False, frozenset()
    sockets: set[str] = set()
    for fd in fds:
        try:
            target = os.readlink(fd)
            if target.startswith('socket:[') and target.endswith(']'):
                sockets.add(target[8:-1])
                continue
            opened = fd.stat()
        except OSError:
            return False, frozenset(sockets)
        if ((opened.st_dev, opened.st_ino) == (disk_stat.st_dev, disk_stat.st_ino)
                and process not in openers):
            openers.append(process)
    return True, frozenset(sockets)


def ssh_listener_inodes(tcp_table: Path, port: int) -> frozenset[str] | None:
    try:
        rows = tcp_table.read_text().splitlines()[1:]
    except OSError:
        return None
    expected = f'{port:04X}'
    inodes: set[str] = set()
    for row in rows:
        columns = row.split()
        if len(columns) < 10 or columns[3] != '0A':
            continue
        address, separator, found_port = columns[1].rpartition(':')
        if separator and found_port == expected and address == '0100007F':
            inodes.add(columns[9])
    return frozenset(inodes)
