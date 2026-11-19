from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from typing import TYPE_CHECKING, final

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_offline_preservation as op
    import sandbox.scripts.oc2_offline_disk as disk
    import sandbox.scripts.oc2_offline_preserver as preserve
    import sandbox.scripts.oc2_slice_b_git as slice_b_git
    import sandbox.scripts.oc2_slice_b_session as session
    from sandbox.tests.oc2_host_lifecycle_test_support import HostFixture
else:
    import oc2_host_control as hc
    import oc2_offline_preservation as op
    import oc2_offline_disk as disk
    import oc2_offline_preserver as preserve
    import oc2_slice_b_git as slice_b_git
    import oc2_slice_b_session as session
    from oc2_host_lifecycle_test_support import HostFixture


@final
class FakeOfflineOps:
    def __init__(
        self, fixture: HostFixture, *, dirty: bool | None = False,
        copy_failure: bool = False,
    ) -> None:
        self.fixture = fixture
        self.dirty = dirty
        self.copy_failure = copy_failure
        self.calls: list[str] = []
        self.audit = fixture.preservation_evidence()

    def source_identity_matches(self, identity: hc.HostVmIdentity) -> bool | None:
        return identity.disk == self.fixture.disk

    def inspect_qcow2(self, path: Path) -> preserve.Qcow2Metadata:
        self.calls.append('inspect:' + path.name)
        return preserve.Qcow2Metadata(
            'qcow2', 1, None, self.dirty, False,
        )

    def create_output_dir(self, output_root: Path) -> Path:
        self.calls.append('create-output')
        output_root.mkdir()
        destination = output_root / 'oc2-t7-offline.fixture'
        destination.mkdir(mode=0o700)
        return destination

    def destination_isolated(
        self, destination: Path, baseline: slice_b_git.GitBaseline,
    ) -> bool | None:
        return destination != baseline.root

    def copy_disk(
        self, source: Path, destination: Path, expected_source: hc.HostDiskIdentity,
    ) -> hc.HostDiskIdentity:
        if source != Path(self.fixture.disk.path) or expected_source != self.fixture.disk:
            raise AssertionError('unexpected source disk')
        self.calls.append('copy')
        if self.copy_failure:
            raise OSError('injected copy failure')
        destination.write_bytes(b'fixture qcow image')
        return hc.HostDiskIdentity(str(destination), 99, 101)

    def sha256(self, path: Path) -> str:
        self.calls.append('sha256:' + path.name)
        return 'd' * 64

    def byte_identical(self, source: Path, copy: Path) -> bool:
        self.calls.append('byte-compare')
        return source != copy

    def logical_compare(self, source: Path, copy: Path) -> bool:
        self.calls.append('logical-compare')
        return source != copy

    def host_repository_unchanged(self, baseline: slice_b_git.GitBaseline) -> bool | None:
        if not baseline.root:
            return None
        return True

    def audit_readonly(
        self,
        copy: Path,
        settings: preserve.LibguestfsSettings,
        identity: hc.HostVmIdentity,
        authority: session.VerifiedGuestAuthority,
        config: preserve.OfflinePreservationConfig,
    ) -> op.OfflinePreservationEvidence | None:
        if authority.key != identity.session_key or not settings.kernel_version:
            return None
        self.calls.append('guestfish-ro')
        return replace(
            self.audit, repository_path=config.guest_repository_path,
        )


@final
class OfflinePreserverTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.fixture: HostFixture = HostFixture.create(root)

    def make_preserver(self, ops: FakeOfflineOps) -> preserve.OfflinePreserver:
        return preserve.OfflinePreserver(
            preserve.OfflinePreservationConfig(
                source_disk_path=Path(self.fixture.disk.path),
                output_root=self.fixture.root / 'cache',
                guest_repository_path='/home/ubuntu/.cache/guest-repo',
                guest_receipt_path='/home/ubuntu/.cache/receipt.json',
                guest_manifest_path='/home/ubuntu/.cache/manifest.json',
                libguestfs=preserve.LibguestfsSettings(
                    kernel_version='7.0.0-34-generic',
                    kernel_image=Path('/injected/kernel'),
                    modules=Path('/lib/modules/7.0.0-34-generic'),
                    cache_dir=Path('/injected/cache'),
                    tmp_dir=Path('/injected/tmp'),
                    backend='direct',
                ),
            ),
            ops,
        )

    def test_valid_copy_and_readonly_audit_yield_session_evidence(self) -> None:
        f = self.fixture
        ops = FakeOfflineOps(f)
        preserver = self.make_preserver(ops)

        evidence = preserver.preserve(
            f.host_identity, f.authority,
            hc.HostIsolationResult(True, True, ()),
        )

        self.assertIsNotNone(evidence)
        if evidence is None:
            self.fail('offline preservation evidence missing')
        self.assertEqual(evidence.session_key, f.key)
        self.assertEqual(evidence.source_sha256, evidence.copy_sha256)
        self.assertEqual(ops.calls[-1], 'guestfish-ro')

    def test_qcow_metadata_reads_dirty_flag_and_nested_corruption(self) -> None:
        metadata = disk.parse_qcow2_metadata(
            b'{"format":"qcow2","dirty-flag":true,"backing-filename":null,'
            b'"format-specific":{"data":{"corrupt":true}}}',
        )

        self.assertIs(metadata.dirty_flag, True)
        self.assertIs(metadata.corrupt, True)

    def test_missing_qcow_metadata_remains_unknown(self) -> None:
        metadata = disk.parse_qcow2_metadata(b'{"format":"qcow2"}')

        self.assertIsNone(metadata.dirty_flag)
        self.assertIsNone(metadata.corrupt)

    def test_dirty_qcow2_stops_before_copy(self) -> None:
        f = self.fixture
        ops = FakeOfflineOps(f, dirty=True)
        preserver = self.make_preserver(ops)

        evidence = preserver.preserve(
            f.host_identity, f.authority,
            hc.HostIsolationResult(True, True, ()),
        )

        self.assertIsNone(evidence)
        self.assertNotIn('copy', ops.calls)

    def test_unknown_qcow2_dirty_state_stops_before_copy(self) -> None:
        f = self.fixture
        ops = FakeOfflineOps(f, dirty=None)
        preserver = self.make_preserver(ops)

        evidence = preserver.preserve(
            f.host_identity, f.authority,
            hc.HostIsolationResult(True, True, ()),
        )

        self.assertIsNone(evidence)
        self.assertNotIn('copy', ops.calls)

    def test_unverified_host_isolation_never_copies_disk(self) -> None:
        f = self.fixture
        ops = FakeOfflineOps(f)
        preserver = self.make_preserver(ops)

        evidence = preserver.preserve(
            f.host_identity, f.authority,
            hc.HostIsolationResult(True, False, (hc.HostFailureCode.SHARED_WRITE_UNKNOWN,)),
        )

        self.assertIsNone(evidence)
        self.assertEqual(ops.calls, [])

    def test_copy_io_failure_returns_unknown_without_claiming_preservation(self) -> None:
        f = self.fixture
        ops = FakeOfflineOps(f, copy_failure=True)
        preserver = self.make_preserver(ops)

        evidence = preserver.preserve(
            f.host_identity, f.authority,
            hc.HostIsolationResult(True, True, ()),
        )

        self.assertIsNone(evidence)
        self.assertNotIn('guestfish-ro', ops.calls)


if __name__ == '__main__':
    unittest.main()
