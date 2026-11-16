from pathlib import Path
from dataclasses import replace
import fcntl
import queue
import sys
import tempfile
import threading
import unittest
import uuid
import subprocess
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from oc2_slice_b_git import admit_clean_repo, build_verified_bundle  # noqa: E402
from oc2_slice_b_session import (  # noqa: E402
    SliceBReceipt,
    SliceBSessionError,
    create_session_receipt,
    update_session_receipt,
    verify_session_receipt,
    import_guest_baseline,
    verify_guest_authority,
    build_start_message,
)


class Key:
    """SessionKey fixture with intentionally limited local validation."""

    def __init__(self) -> None:
        """Create identifiers accepted by the Slice B test boundary."""
        self.workspace_id = "a" * 32
        self.sandbox_id = str(uuid.uuid4())
        self.session_generation = str(uuid.uuid4())

    def validate(self) -> None:
        """Validate only the fixture's workspace identifier length."""
        if len(self.workspace_id) != 32:
            raise ValueError()

    def __eq__(self, other: object) -> bool:
        """Compare all generated fixture identity fields."""
        return vars(self) == vars(other)


def git(root: Path, *args: str) -> None:
    """Run Git in the fixture repository with isolated user configuration."""
    home = root.parent / "git-home"
    home.mkdir(mode=0o700, exist_ok=True)
    r = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        env={
            "PATH": "/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/dev/null",
            "GIT_CONFIG_KEY_1": "commit.gpgSign", "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "false",
        },
    )
    if r.returncode:
        raise AssertionError(r.stderr.decode())


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        """Build a clean Host baseline, Bundle, and pending Session receipt."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.host = base / "host"
        self.host.mkdir()
        git(self.host, "init", "-b", "sliceb")
        git(self.host, "config", "user.name", "Fixture")
        git(self.host, "config", "user.email", "fixture@example.invalid")
        (self.host / "hello").write_text("good\n")
        git(self.host, "add", "hello")
        git(self.host, "commit", "-m", "initial")
        self.key = Key()
        self.baseline = admit_clean_repo(self.host)
        self.art = build_verified_bundle(
            self.baseline, base / "ref.bundle", key=self.key, runtime_sha256="b" * 64
        )
        self.rec = SliceBReceipt(
            self.key,
            self.baseline,
            self.art.bundle_sha256,
            self.art.manifest_sha256,
            self.art.transfer_policy_id,
            "b" * 64,
            "example.test/oc2-writer@sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
            "PENDING",
            "NOT_RUN",
            None,
            None,
        )
        self.state = base / "state"
        self.guest = base / "guest"

    def test_receipt_create_and_readback(self) -> None:
        """A pending receipt roundtrips and duplicate creation is rejected."""
        path = create_session_receipt(self.state, self.rec, self.art)
        self.assertEqual(verify_session_receipt(path, self.key), self.rec)
        with self.assertRaises(SliceBSessionError):
            create_session_receipt(self.state, self.rec, self.art)

    def test_guest_import_and_authority(self) -> None:
        """A verified Bundle imports into a new Guest and produces a start frame."""
        path = create_session_receipt(self.state, self.rec, self.art)
        guest = import_guest_baseline(
            self.art,
            self.guest,
            expected_manifest_sha256=self.art.manifest_sha256,
            expected_key=self.key,
            expected_runtime_sha256="b" * 64,
        )
        auth = verify_guest_authority(
            path.parent / "bundle.manifest.json",
            self.rec,
            guest,
            "sha256:" + "d" * 64,
            local_image_inspect={
                "Id": self.rec.image_config_id,
                "RepoDigests": [self.rec.image_ref],
                "Config": {
                    "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                    "Cmd": ["run"],
                },
            },
        )
        start = build_start_message(auth).to_wire()
        self.assertEqual(start.count(" "), 4)
        self.assertTrue(start.endswith("\n"))

    def test_reject_wrong_runtime(self) -> None:
        """Guest import rejects a runtime digest different from its manifest."""
        with self.assertRaises(Exception):
            import_guest_baseline(
                self.art,
                self.guest,
                expected_manifest_sha256=self.art.manifest_sha256,
                expected_key=self.key,
                expected_runtime_sha256="e" * 64,
            )

    def test_reject_receipt_identity_mutation(self) -> None:
        """Receipt updates cannot alter immutable runtime identity."""
        path = create_session_receipt(self.state, self.rec, self.art)
        with self.assertRaises(SliceBSessionError):
            update_session_receipt(path, replace(self.rec, runtime_sha256="e" * 64))
        self.assertEqual(verify_session_receipt(path, self.key), self.rec)

    def test_reject_guest_control_manifest_mutation(self) -> None:
        """Guest authority rejects a changed copied Bundle Manifest."""
        path = create_session_receipt(self.state, self.rec, self.art)
        guest = import_guest_baseline(
            self.art,
            self.guest,
            expected_manifest_sha256=self.art.manifest_sha256,
            expected_key=self.key,
            expected_runtime_sha256="b" * 64,
        )
        p = path.parent / "bundle.manifest.json"
        p.write_bytes(p.read_bytes() + b"X")
        with self.assertRaises(SliceBSessionError):
            verify_guest_authority(
                p,
                self.rec,
                guest,
                "sha256:" + "d" * 64,
                local_image_inspect={
                    "Id": self.rec.image_config_id,
                    "RepoDigests": [self.rec.image_ref],
                    "Config": {
                        "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                        "Cmd": ["run"],
                    },
                },
            )

    def test_running_receipt_requires_writer_identity(self) -> None:
        """RUNNING cannot be represented without both Writer identity fields."""
        running = replace(self.rec, state="RUNNING")
        with self.assertRaises(SliceBSessionError):
            from oc2_slice_b_session import _validate_receipt

            _validate_receipt(running)

    def test_update_cleans_new_tmp_after_replace_failure(self) -> None:
        """A failed replace removes only the tmp created by this update."""
        path = create_session_receipt(self.state, self.rec, self.art)
        with patch("oc2_slice_b_session.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                update_session_receipt(path, self.rec)
        self.assertTrue(path.exists())
        self.assertFalse(path.with_name("receipt.tmp").exists())

    def test_update_preserves_preexisting_tmp_on_exclusive_create_failure(self) -> None:
        """O_EXCL rejects a stale tmp without deleting a file not created here."""
        path = create_session_receipt(self.state, self.rec, self.art)
        tmp = path.with_name("receipt.tmp")
        tmp.write_bytes(b"preexisting")
        with self.assertRaises(FileExistsError):
            update_session_receipt(path, self.rec)
        self.assertEqual(tmp.read_bytes(), b"preexisting")

    def test_update_cleans_tmp_after_fsync_failure(self) -> None:
        """An fsync error propagates while cleaning the new temporary receipt."""
        path = create_session_receipt(self.state, self.rec, self.art)
        with patch("oc2_slice_b_session.os.fsync", side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(OSError, "fsync failed"):
                update_session_receipt(path, self.rec)
        self.assertFalse(path.with_name("receipt.tmp").exists())

    def test_concurrent_writer_identity_binding_is_serialized(self) -> None:
        """A second writer cannot bind from the stale unbound receipt snapshot."""
        path = create_session_receipt(self.state, self.rec, self.art)
        first = replace(
            self.rec,
            state="RUNNING",
            writer_id="a" * 64,
            started_at="2026-11-16T00:00:00Z",
        )
        second = replace(first, writer_id="b" * 64)
        first_read = threading.Event()
        release_first = threading.Event()
        signals: queue.Queue[str] = queue.Queue()
        results: queue.Queue[tuple[str, Exception | None]] = queue.Queue()
        original_flock = fcntl.flock
        original_verify = verify_session_receipt

        def observe_flock(descriptor: int, operation: int) -> None:
            if threading.current_thread().name == "writer-second" and operation == fcntl.LOCK_EX:
                signals.put("lock")
            original_flock(descriptor, operation)

        def pause_first_read(receipt_path: Path, expected_key: object) -> SliceBReceipt:
            result = original_verify(receipt_path, expected_key)
            if threading.current_thread().name == "writer-first":
                first_read.set()
                if not release_first.wait(timeout=5):
                    raise TimeoutError("first update gate timed out")
            else:
                signals.put("verify")
            return result

        def update(receipt: SliceBReceipt) -> None:
            writer = threading.current_thread().name
            try:
                update_session_receipt(path, receipt)
            except Exception as error:
                results.put((writer, error))
            else:
                results.put((writer, None))

        first_thread = threading.Thread(
            target=update, args=(first,), name="writer-first"
        )
        second_thread = threading.Thread(
            target=update, args=(second,), name="writer-second"
        )
        observed: str | None = None
        with patch("oc2_slice_b_session.verify_session_receipt", side_effect=pause_first_read), \
                patch.object(fcntl, "flock", side_effect=observe_flock):
            first_thread.start()
            self.assertTrue(first_read.wait(timeout=5))
            second_thread.start()
            try:
                observed = signals.get(timeout=5)
            finally:
                release_first.set()
            first_thread.join(timeout=5)
            second_thread.join(timeout=5)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(observed, "lock")
        outcomes = dict((results.get_nowait(), results.get_nowait()))
        self.assertIsNone(outcomes["writer-first"])
        self.assertIsInstance(outcomes["writer-second"], SliceBSessionError)
        self.assertEqual(verify_session_receipt(path, self.key).writer_id, first.writer_id)


if __name__ == "__main__":
    unittest.main()
