from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from typing import TYPE_CHECKING, final

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_guestfs_audit as guestfs_audit
    import sandbox.scripts.oc2_guestfs_transport as guestfs_transport
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_offline_preservation as op
    import sandbox.scripts.oc2_offline_preserver as preserve
    import sandbox.scripts.oc2_slice_b_git as slice_b_git
    import sandbox.scripts.oc2_slice_b_session as session
    from sandbox.tests.oc2_slice_b_test_support import make_key, make_verified_authority
else:
    import oc2_guestfs_audit as guestfs_audit
    import oc2_guestfs_transport as guestfs_transport
    import oc2_host_control as hc
    import oc2_offline_preservation as op
    import oc2_offline_preserver as preserve
    import oc2_slice_b_git as slice_b_git
    import oc2_slice_b_session as session
    from oc2_slice_b_test_support import make_key, make_verified_authority


@final
class FakeGuestfishRunner:
    def __init__(self, *, archive: bytes, receipt: bytes, manifest: bytes) -> None:
        self.archive = archive
        self.files = {
            'receipt.json': receipt,
            'bundle.manifest.json': manifest,
        }
        self.calls: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        settings: preserve.LibguestfsSettings,
    ) -> guestfs_transport.GuestfishCommandResult:
        self.calls.append((argv, settings.environment()))
        if 'tar-out' in argv:
            return guestfs_transport.GuestfishCommandResult(0, self.archive)
        command_index = argv.index('download')
        guest_file_path = argv[command_index + 1]
        return guestfs_transport.GuestfishCommandResult(
            0, self.files[Path(guest_file_path).name],
        )


@final
class GuestfsAuditTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.make_clean_repo(self.root / 'source-repo')
        self.baseline = slice_b_git.admit_clean_repo(self.repo)
        self.key = make_key()
        self.authority_root = self.root / 'authority'
        self.authority: session.VerifiedGuestAuthority = make_verified_authority(
            self.authority_root, self.key, baseline=self.baseline,
        )
        self.control = self.authority_root / 'image-control' / self.key.session_generation
        self.guest_repo_path = '/home/ubuntu/.cache/session-fixture/guest-repo'
        self.guest_state = f'/home/ubuntu/.cache/session-fixture/state/{self.key.workspace_id}/{self.key.session_generation}'
        self.source_disk = self.root / 'recovered.qcow2'
        self.source_disk.write_bytes(b'original offline disk fixture')
        source_stat = self.source_disk.stat()
        self.config = preserve.OfflinePreservationConfig(
            source_disk_path=self.source_disk,
            output_root=self.root / 'audit-output',
            guest_repository_path=self.guest_repo_path,
            guest_receipt_path=f'{self.guest_state}/receipt.json',
            guest_manifest_path=f'{self.guest_state}/bundle.manifest.json',
            libguestfs=preserve.LibguestfsSettings(
                kernel_version='7.0.0-34-generic',
                kernel_image=self.root / 'kernel-copy',
                modules=Path('/lib/modules/7.0.0-34-generic'),
                cache_dir=self.root / 'guestfs-cache',
                tmp_dir=self.root / 'guestfs-tmp',
                backend='direct',
            ),
        )
        self.config.libguestfs.tmp_dir.mkdir(mode=0o700)
        self.disk_copy = self.root / 'recovered-audit.qcow2'
        self.disk_copy.write_bytes(b'offline disk fixture')
        self.identity = hc.HostVmIdentity(
            'direct-qemu:fixture', 'oc2-f002-probe-recovery', 'host-boot',
            hc.HostProcessIdentity(901, 12345, 'c' * 64),
            hc.HostDiskIdentity(str(self.source_disk), source_stat.st_dev, source_stat.st_ino),
            self.key, '127.0.0.1', 2223,
        )

    @staticmethod
    def make_clean_repo(path: Path) -> Path:
        path.mkdir()
        subprocess.run(('git', 'init', '-q', str(path)), check=True)
        subprocess.run(('git', '-C', str(path), 'config', 'user.name', 'OC2 Test'), check=True)
        subprocess.run(('git', '-C', str(path), 'config', 'user.email', 'oc2@example.invalid'), check=True)
        (path / 'tracked.txt').write_text('clean fixture\n')
        subprocess.run(('git', '-C', str(path), 'add', 'tracked.txt'), check=True)
        subprocess.run(('git', '-C', str(path), 'commit', '-qm', 'fixture'), check=True)
        return path

    @staticmethod
    def tar_repository(path: Path, *, unsafe_name: str | None = None) -> bytes:
        payload = BytesIO()
        with tarfile.open(fileobj=payload, mode='w') as archive:
            if unsafe_name is not None:
                member = tarfile.TarInfo(unsafe_name)
                member.size = 4
                archive.addfile(member, BytesIO(b'evil'))
            else:
                for entry in sorted(path.rglob('*')):
                    archive.add(entry, arcname=entry.relative_to(path).as_posix(), recursive=False)
        return payload.getvalue()

    def make_provider(self, runner: FakeGuestfishRunner) -> guestfs_audit.GuestfishReadOnlyAuditProvider:
        return guestfs_audit.GuestfishReadOnlyAuditProvider(runner)

    def test_guestfish_exports_are_readonly_and_verified_for_this_session(self) -> None:
        runner = FakeGuestfishRunner(
            archive=self.tar_repository(self.repo),
            receipt=(self.control / 'receipt.json').read_bytes(),
            manifest=(self.control / 'bundle.manifest.json').read_bytes(),
        )
        provider = self.make_provider(runner)

        evidence = provider.audit_readonly(
            self.disk_copy, self.config.libguestfs, self.identity,
            self.authority, self.config,
        )

        if evidence is None:
            self.fail('current Guest Session evidence was not verified')
        self.assertEqual(evidence.session_key, self.key)
        self.assertEqual(evidence.head_oid, self.baseline.head_oid)
        self.assertEqual(evidence.receipt_sha256, self.authority.receipt_sha256)
        self.assertEqual(evidence.manifest_sha256, self.authority.manifest_sha256)
        self.assertTrue(evidence.session_artifacts_verified)
        self.assertIs(evidence.filesystem_state, op.FilesystemState.READ_ONLY_INSPECTED)
        self.assertFalse(evidence.filesystem_repair_performed)
        self.assertTrue(all('--ro' in argv for argv, _ in runner.calls))
        self.assertTrue(all('--format=qcow2' in argv for argv, _ in runner.calls))
        self.assertEqual(runner.calls[0][0][-3:], ('tar-out', self.guest_repo_path, '-'))
        self.assertEqual(runner.calls[1][1], self.config.libguestfs.environment())

    def test_guestfish_rejects_archive_path_traversal(self) -> None:
        runner = FakeGuestfishRunner(
            archive=self.tar_repository(self.repo, unsafe_name='../escaped'),
            receipt=(self.control / 'receipt.json').read_bytes(),
            manifest=(self.control / 'bundle.manifest.json').read_bytes(),
        )

        evidence = self.make_provider(runner).audit_readonly(
            self.disk_copy, self.config.libguestfs, self.identity,
            self.authority, self.config,
        )

        self.assertIsNone(evidence)
        self.assertEqual(len(runner.calls), 1)

    def test_guestfish_rejects_receipt_from_another_session(self) -> None:
        runner = FakeGuestfishRunner(
            archive=self.tar_repository(self.repo),
            receipt=b'not the pinned Receipt',
            manifest=(self.control / 'bundle.manifest.json').read_bytes(),
        )

        evidence = self.make_provider(runner).audit_readonly(
            self.disk_copy, self.config.libguestfs, self.identity,
            self.authority, self.config,
        )

        self.assertIsNone(evidence)

    def test_guestfish_rejects_guest_paths_with_command_delimiters_before_io(self) -> None:
        runner = FakeGuestfishRunner(
            archive=self.tar_repository(self.repo),
            receipt=(self.control / 'receipt.json').read_bytes(),
            manifest=(self.control / 'bundle.manifest.json').read_bytes(),
        )
        unsafe_config = replace(
            self.config,
            guest_repository_path='/home/ubuntu/repo:download/guest-repo',
        )

        evidence = self.make_provider(runner).audit_readonly(
            self.disk_copy, unsafe_config.libguestfs, self.identity,
            self.authority, unsafe_config,
        )

        self.assertIsNone(evidence)
        self.assertEqual(runner.calls, [])


if __name__ == '__main__':
    unittest.main()
