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
    import sandbox.scripts.oc2_offline_preservation as op
    import sandbox.scripts.oc2_writer as w
    from sandbox.scripts.oc2_slice_b_git import GitBaseline
    from sandbox.tests.oc2_host_lifecycle_test_support import HostFixture
else:
    import oc2_host_control as hc
    import oc2_offline_preservation as op
    import oc2_writer as w
    from oc2_slice_b_git import GitBaseline
    from oc2_host_lifecycle_test_support import HostFixture


@final
class OfflinePreservationGateTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: HostFixture = HostFixture.create(Path(temporary.name))

    def expectation(self) -> op.PreservationExpectation:
        authority = self.fixture.authority
        return op.PreservationExpectation(
            authority.key, authority.receipt_sha256, authority.manifest_sha256,
            authority.manifest.baseline,
        )

    def test_baseline_copy_and_readonly_git_evidence_verify(self) -> None:
        f = self.fixture
        expectation = self.expectation()

        decision = op.evaluate_offline_preservation(
            expectation, f.host_identity, f.preservation_evidence(),
        )

        self.assertIs(decision.disposition, op.PreservationDisposition.VERIFIED)
        self.assertEqual(decision.failures, ())

    def test_invalid_object_database_is_a_mismatch(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        evidence = replace(f.preservation_evidence(), object_database_valid=False)

        decision = op.evaluate_offline_preservation(
            expectation, f.host_identity, evidence,
        )

        self.assertIs(decision.disposition, op.PreservationDisposition.MISMATCH)
        self.assertIn(op.PreservationFailure.GIT_OBJECT_DATABASE_INVALID,
                      decision.failures)

    def test_host_repository_change_or_unisolated_export_fails_closed(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        changed_host = replace(f.preservation_evidence(),
                               host_repository_unchanged=False)
        unknown_destination = replace(f.preservation_evidence(),
                                      copy_destination_isolated=None)

        changed = op.evaluate_offline_preservation(
            expectation, f.host_identity, changed_host,
        )
        unknown = op.evaluate_offline_preservation(
            expectation, f.host_identity, unknown_destination,
        )

        self.assertIs(changed.disposition, op.PreservationDisposition.MISMATCH)
        self.assertIs(unknown.disposition, op.PreservationDisposition.UNVERIFIED)

    def test_repository_path_must_be_derived_from_verified_session_artifacts(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        evidence = replace(f.preservation_evidence(),
                           session_artifacts_verified=False)

        decision = op.evaluate_offline_preservation(
            expectation, f.host_identity, evidence,
        )

        self.assertIs(decision.disposition, op.PreservationDisposition.MISMATCH)
        self.assertIn(op.PreservationFailure.RECEIPT_MANIFEST_MISMATCH,
                      decision.failures)

    def test_copy_receipt_manifest_and_git_identity_mismatches_fail_closed(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        cases = (
            replace(f.preservation_evidence(), copy_sha256='f' * 64),
            replace(f.preservation_evidence(), manifest_sha256='f' * 64),
            replace(f.preservation_evidence(), head_oid='f' * 40),
        )

        for evidence in cases:
            with self.subTest(evidence=evidence):
                decision = op.evaluate_offline_preservation(
                    expectation, f.host_identity, evidence,
                )
                self.assertIs(decision.disposition, op.PreservationDisposition.MISMATCH)

    def test_readonly_filesystem_inspection_is_not_clean_check_for_new_session(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        evidence = replace(
            f.preservation_evidence(),
            filesystem_state=op.FilesystemState.READ_ONLY_INSPECTED,
        )

        decision = op.evaluate_offline_preservation(
            expectation, f.host_identity, evidence,
        )

        self.assertIs(decision.disposition, op.PreservationDisposition.UNVERIFIED)
        self.assertIn(op.PreservationFailure.FILESYSTEM_STATE_UNVERIFIED,
                      decision.failures)

    def test_incomplete_git_status_is_unverified(self) -> None:
        f = self.fixture
        expectation = self.expectation()
        evidence = replace(f.preservation_evidence(), git_status_complete=False)

        decision = op.evaluate_offline_preservation(
            expectation, f.host_identity, evidence,
        )

        self.assertIs(decision.disposition, op.PreservationDisposition.UNVERIFIED)
        self.assertIn(op.PreservationFailure.GIT_STRUCTURE_UNVERIFIED,
                      decision.failures)

    def t7_evidence(self) -> tuple[op.PreservationExpectation,
                                   hc.HostVmIdentity,
                                   op.OfflinePreservationEvidence]:
        key = w.WriterSessionKey(
            '6cbe81664153a2b59eb9755448763aee',
            '37ad86ef-7ed2-449a-b0dc-04575d30bf63',
            '2ec5dc1c-3b92-4e6e-958f-71a718cf775f',
        )
        baseline = GitBaseline(
            Path('/host/baseline'), 'refs/heads/oc2-fixture',
            '1e54222fa8613b4e27f99e416774805d63a9645c',
            '0ea64553e9d6f8beb55298a67bd2a5e1249ba6ed', 'sha1',
            '4e79e8547e6a1a6276894c2c58124bc1e5a1e4419a376f3c841c939031bf8b03',
            '9b0bc8972181c62d93aa33bb55594e05482307c80ab127a524bb106039184e98',
        )
        expectation = op.PreservationExpectation(
            key,
            'dabe011ef7d9ecc92ba865301bc69141b0ec02e9bb06ed535ee09a21cbdeaae6',
            '839a32d9cc0ba1e06f7536161663e63227d2a7e4c702d627d25b28f57c4b59e8',
            baseline,
        )
        disk = hc.HostDiskIdentity('/source/recovery.qcow2', 5, 8)
        identity = hc.HostVmIdentity(
            'vm-id', 'oc2-f002-probe', 'boot',
            hc.HostProcessIdentity(71, 99, 'c' * 64), disk, key, '127.0.0.1', 2223,
        )
        evidence = op.OfflinePreservationEvidence(
            session_key=key,
            source_disk=disk,
            copy_disk=hc.HostDiskIdentity('/evidence/copy.qcow2', 5, 9),
            copy_destination_isolated=True,
            host_repository_unchanged=True,
            source_sha256='68ef7fa18bd9e5324cbadd0294a6f81dadd9e2f35b5c68ef2e20bdb22e32c2ea',
            copy_sha256='68ef7fa18bd9e5324cbadd0294a6f81dadd9e2f35b5c68ef2e20bdb22e32c2ea',
            qcow2_structure_verified=True,
            qcow2_logical_content_verified=True,
            guestfs_readonly=True,
            filesystem_state=op.FilesystemState.READ_ONLY_INSPECTED,
            filesystem_repair_performed=False,
            receipt_sha256=expectation.receipt_sha256,
            manifest_sha256=expectation.manifest_sha256,
            session_artifacts_verified=True,
            repository_path='/guest/state/guest-repo',
            branch_ref=baseline.branch_ref,
            head_oid=baseline.head_oid,
            tree_oid=baseline.tree_oid,
            object_format=baseline.object_format,
            index_sha256='de8497cc42589e0e5a377442c351797572b914c1f87cc3c7a493dbf5518f3fb2',
            index_structure_valid=True,
            worktree_sha256=baseline.worktree_sha256,
            object_database_valid=True,
            git_status_complete=True,
            git_dirty=False,
            tracked_file_count=1,
            untracked_file_count=0,
            export_manifest_sha256='e' * 64,
        )
        return expectation, identity, evidence

    def test_t7_index_digest_discrepancy_is_conditionally_accepted(self) -> None:
        expected, identity, evidence = self.t7_evidence()

        decision = op.evaluate_offline_preservation(expected, identity, evidence)

        self.assertIs(decision.disposition,
                      op.PreservationDisposition.CONDITIONALLY_ACCEPTED)
        self.assertIn(op.PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,
                      decision.failures)

    def test_old_t7_evidence_cannot_bind_to_a_new_session(self) -> None:
        expected, identity, evidence = self.t7_evidence()
        new_key = w.WriterSessionKey('f' * 32, str(uuid.uuid4()), str(uuid.uuid4()))
        future = replace(expected, session_key=new_key)
        future_identity = replace(identity, session_key=new_key)

        decision = op.evaluate_offline_preservation(future, future_identity, evidence)

        self.assertIs(decision.disposition, op.PreservationDisposition.MISMATCH)
        self.assertIn(op.PreservationFailure.SESSION_MISMATCH, decision.failures)

    def test_t7_index_exception_does_not_apply_to_new_generation(self) -> None:
        expected, identity, evidence = self.t7_evidence()
        new_key = w.WriterSessionKey('f' * 32, str(uuid.uuid4()), str(uuid.uuid4()))
        future = replace(expected, session_key=new_key)
        future_identity = replace(identity, session_key=new_key)
        future_evidence = replace(evidence, session_key=new_key)

        decision = op.evaluate_offline_preservation(future, future_identity, future_evidence)

        self.assertIs(decision.disposition, op.PreservationDisposition.UNVERIFIED)
        self.assertIn(op.PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,
                      decision.failures)
