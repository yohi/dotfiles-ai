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
    """Return whether name has the canonical decimal PID form."""
    return _PID_NAME.fullmatch(name) is not None


def parse_start_ticks(stat_text: str) -> int:
    """Parse the kernel process start-tick field from one procfs stat record."""
    closing = stat_text.rfind(')')
    fields = stat_text[closing + 2:].split()
    return int(fields[19])


def read_status_uid(status_path: Path) -> int:
    """Read the real UID from procfs status or raise ProcfsReadError."""
    for line in status_path.read_text().splitlines():
        if line.startswith('Uid:'):
            return int(line.split()[1])
    raise ProcfsReadError


def matches_qemu(
    arguments: tuple[str, ...], vm_name: str, disk_path: str,
    ssh_host: str, ssh_port: int,
) -> bool:
    """Match the fixed VM only in parsed QEMU name, drive, and netdev values."""
    if not arguments or Path(arguments[0]).name not in _QEMU_NAMES:
        return False
    names = _option_values(arguments, '-name')
    drives = _option_values(arguments, '-drive')
    networks = _option_values(arguments, '-netdev')
    forward = f'hostfwd=tcp:{ssh_host}:{ssh_port}-:22'
    disk_matches = any(
        any(field.partition('=')[0] == 'file'
            and field.partition('=')[2] == disk_path
            for field in value.split(','))
        for value in drives
    )
    forward_matches = any(
        forward in value.split(',') for value in networks
    )
    return names == (vm_name,) and disk_matches and forward_matches


def _option_values(arguments: tuple[str, ...], option: str) -> tuple[str, ...]:
    """Return values paired with exact occurrences of a QEMU option."""
    values: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] == option and index + 1 < len(arguments):
            values.append(arguments[index + 1])
            index += 2
        else:
            index += 1
    return tuple(values)


def scan_process_fds(
    fd_dir: Path,
    disk_stat: os.stat_result,
    openers: list[HostProcessReference],
    process: HostProcessReference,
) -> tuple[bool, frozenset[str]]:
    """Scan process FDs; ``openers`` may be updated before an incomplete result."""
    try:
        directory = os.scandir(fd_dir)
    except OSError:
        return False, frozenset()
    sockets: set[str] = set()
    with directory:
        for entry in directory:
            fd = fd_dir / entry.name
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
    """Return loopback or wildcard listener inodes for the exact TCP port."""
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
        if (separator and found_port == expected
                and address in {'0100007F', '00000000'}):
            inodes.add(columns[9])
    return frozenset(inodes)
