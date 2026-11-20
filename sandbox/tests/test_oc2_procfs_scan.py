from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2_procfs_scan as scan  # noqa: E402
import oc2_host_control as hc  # noqa: E402


class ProcfsScanTests(unittest.TestCase):
    def test_parse_start_ticks_rejects_missing_closing_parenthesis(self) -> None:
        with self.assertRaises(ValueError):
            scan.parse_start_ticks('123 (qemu S 0')

    def test_parse_start_ticks_rejects_truncated_fields(self) -> None:
        with self.assertRaises(ValueError):
            scan.parse_start_ticks('123 (qemu) S 0 0')

    def test_read_status_uid_rejects_missing_uid_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status = Path(temporary) / 'status'
            status.write_text('Uid:\n', encoding='ascii')

            with self.assertRaises(ValueError):
                scan.read_status_uid(status)

    def test_fd_enumeration_keeps_scandir_open_during_readlink(self) -> None:
        """Keep the enumeration descriptor live until every listed FD is inspected."""
        class Entry:
            name = '4'

        class Directory:
            closed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.closed = True

            def __iter__(self):
                return iter((Entry(),))

        with tempfile.TemporaryDirectory() as temporary:
            disk = Path(temporary) / 'disk'
            disk.write_bytes(b'disk')
            directory = Directory()
            openers: list[hc.HostProcessReference] = []
            process = hc.HostProcessReference(123, 456)

            def readlink(_path: Path) -> str:
                self.assertFalse(directory.closed)
                return 'socket:[12345]'

            with patch.object(scan.os, 'scandir', return_value=directory), \
                 patch.object(scan.os, 'readlink', side_effect=readlink):
                complete, sockets = scan.scan_process_fds(
                    Path('/proc/123/fd'), disk.stat(), openers, process,
                )

        self.assertTrue(complete)
        self.assertEqual(sockets, frozenset({'12345'}))

    def test_qemu_identity_requires_exact_name_and_option_values(self) -> None:
        """Accept exact QEMU option values and reject aliases or embedded substrings."""
        arguments = (
            '/usr/bin/qemu-system-x86_64', '-name', 'oc2-f002-probe-recovery',
            '-drive', 'file=/tmp/disk.qcow2,if=virtio',
            '-netdev', 'user,id=net0,hostfwd=tcp:127.0.0.1:2223-:22',
        )

        self.assertTrue(scan.matches_qemu(
            arguments, 'oc2-f002-probe-recovery', '/tmp/disk.qcow2', '127.0.0.1', 2223,
        ))
        self.assertFalse(scan.matches_qemu(
            (*arguments[:2], 'oc2-f002-probe-recovery-extra', *arguments[3:]),
            'oc2-f002-probe-recovery', '/tmp/disk.qcow2', '127.0.0.1', 2223,
        ))
        self.assertFalse(scan.matches_qemu(
            (*arguments[:3], '-name', 'oc2-f002-probe-recovery-extra', *arguments[3:]),
            'oc2-f002-probe-recovery', '/tmp/disk.qcow2', '127.0.0.1', 2223,
        ))
        self.assertFalse(scan.matches_qemu(
            (*arguments[:4], 'file=/tmp/disk.qcow2-extra,if=virtio', *arguments[5:]),
            'oc2-f002-probe-recovery', '/tmp/disk.qcow2', '127.0.0.1', 2223,
        ))

    def test_listener_scanner_includes_wildcard_address_for_expected_port(self) -> None:
        """Recognize wildcard listeners only when their port matches the expected port."""
        with tempfile.TemporaryDirectory() as temporary:
            tcp = Path(temporary) / 'tcp'
            tcp.write_text(
                'header\n'
                '0: 00000000:08AF 00000000:0000 0A 0 0 0 1 0 12345\n'
                '1: 00000000:08B0 00000000:0000 0A 0 0 0 1 0 67890\n',
                encoding='ascii',
            )

            inodes = scan.ssh_listener_inodes(tcp, 2223)

        self.assertEqual(inodes, frozenset({'12345'}))


if __name__ == '__main__':
    unittest.main()
