from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oc2_slice_b_image import (
    ImagePin,
    SliceBImageRejected,
    verify_build_inputs,
    verify_image_archive,
    verify_loaded_image,
    verify_local_base_image,
    verify_runtime_pin_against_manifest,
)


class ImageTests(unittest.TestCase):
    def setUp(self) -> None:
        """Prepare archive metadata and mocked inspect data; neither invokes Docker."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "context"
        self.root.mkdir()
        self.raw = b"test archive"
        self.archive = self.root.parent / "writer-image.tar"
        self.archive.write_bytes(self.raw)
        self.ref = "oc2/slice-b@sha256:" + "a" * 64
        self.config = "sha256:" + "b" * 64
        self.pin = ImagePin(
            "f" * 40,
            "c" * 64,
            "d" * 64,
            self.ref,
            self.config,
            hashlib.sha256(self.raw).hexdigest(),
        )
        self.inspect = {
            "Id": self.config,
            "RepoDigests": [self.ref],
            "Config": {
                "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                "Cmd": ["run"],
                "User": "10001:10001",
                "WorkingDir": "/workspace",
                "Env": [],
            },
        }

    def test_matching_local_digest(self) -> None:
        """A supplied local inspect response must match the digest-qualified pin."""
        verify_image_archive(self.archive, self.pin)
        verify_loaded_image(self.inspect, self.pin)
        verify_runtime_pin_against_manifest(self.pin, "d" * 64)

    def test_reject_bare_config_id_or_tag(self) -> None:
        """Image validation rejects IDs and tags where an immutable ref is required."""
        from dataclasses import replace

        for ref in ("sha256:" + "a" * 64, "oc2/slice-b:latest"):
            with self.assertRaises(SliceBImageRejected):
                verify_loaded_image(self.inspect, replace(self.pin, image_ref=ref))

    def test_reject_repo_digest_missing(self) -> None:
        """Image validation requires the exact pinned RepoDigest."""
        d = {**self.inspect, "RepoDigests": []}
        with self.assertRaises(SliceBImageRejected):
            verify_loaded_image(d, self.pin)

    def test_reject_image_config_id_mismatch(self) -> None:
        """Image validation rejects a different image config ID."""
        with self.assertRaises(SliceBImageRejected):
            verify_loaded_image({**self.inspect, "Id": "sha256:" + "f" * 64}, self.pin)

    def test_archive_tamper(self) -> None:
        """Archive verification detects content changes against its pin."""
        self.archive.write_bytes(self.raw + b"tampered")
        with self.assertRaises(SliceBImageRejected):
            verify_image_archive(self.archive, self.pin)

    def test_runtime_digest_is_independent(self) -> None:
        """Runtime manifest comparison rejects a different digest."""
        with self.assertRaises(SliceBImageRejected):
            verify_runtime_pin_against_manifest(self.pin, "e" * 64)

    def test_unpinned_build_inputs_blocked(self) -> None:
        """Build input verification refuses a missing trust manifest."""
        with self.assertRaises(SliceBImageRejected):
            verify_build_inputs(self.root)

    def _write_build_context(self) -> str:
        """Create a complete locally pinned Docker context and return its runtime digest."""
        runtime = Path(__file__).resolve().parents[1] / "oc2_slice_b"
        shutil.copyfile(runtime / "entrypoint.py", self.root / "entrypoint.py")
        shutil.copyfile(runtime / "offline_fixture.py", self.root / "offline_fixture.py")
        (self.root / "opencode-v2.2.5").write_bytes(b"binary")
        (self.root / "Dockerfile").write_text(
            "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\n"
            "COPY --chmod=0555 opencode-v2.2.5 /opt/oc2/bin/opencode\n"
            "COPY --chmod=0555 entrypoint.py /opt/oc2/slice-b/entrypoint\n"
            "COPY --chmod=0444 offline_fixture.py /opt/oc2/slice-b/offline_fixture.py\n"
            "WORKDIR /workspace\nUSER 10001:10001\n"
            'ENTRYPOINT ["/opt/oc2/slice-b/entrypoint"]\nCMD ["run"]\n'
        )
        runtime_hasher = hashlib.sha256()
        for name in ("entrypoint.py", "offline_fixture.py"):
            content = (self.root / name).read_bytes()
            runtime_hasher.update(name.encode("ascii") + b"\x00")
            runtime_hasher.update(hashlib.sha256(content).digest())
        runtime_hash = runtime_hasher.hexdigest()
        inputs = {
            "base_image_ref": "alpine@sha256:" + "a" * 64,
            "opencode_binary_sha256": hashlib.sha256(b"binary").hexdigest(),
            "runtime_sha256": runtime_hash,
            "source_revision": "f" * 40,
        }
        (self.root / "build-inputs.json").write_text(json.dumps(inputs))
        return runtime_hash

    def test_runtime_pin_covers_both_runtime_sources(self) -> None:
        runtime_hash = self._write_build_context()
        verify_build_inputs(self.root)
        for name in ("entrypoint.py", "offline_fixture.py"):
            original = (self.root / name).read_bytes()
            (self.root / name).write_bytes(original + b"tampered")
            with self.assertRaises(SliceBImageRejected):
                verify_build_inputs(self.root)
            (self.root / name).write_bytes(original)
        expected = hashlib.sha256()
        for name in ("entrypoint.py", "offline_fixture.py"):
            content = (self.root / name).read_bytes()
            expected.update(name.encode("ascii") + b"\x00")
            expected.update(hashlib.sha256(content).digest())
        self.assertEqual(runtime_hash, expected.hexdigest())

    def test_local_base_image_requires_exact_digest_ref(self) -> None:
        """The preflight accepts only an inspect response with the exact local ref."""
        base_ref = "alpine@sha256:" + "a" * 64
        verify_local_base_image({"RepoDigests": [base_ref]}, base_ref)
        with self.assertRaises(SliceBImageRejected):
            verify_local_base_image({"RepoDigests": []}, base_ref)

    def test_offline_build_requires_local_base_inspection(self) -> None:
        """Build argv requires local base evidence and retains offline build flags."""
        runtime_hash = self._write_build_context()
        from oc2_slice_b_image import offline_build_argv

        base_ref = "alpine@sha256:" + "a" * 64
        with self.assertRaises(SliceBImageRejected):
            offline_build_argv(
                self.root, base_ref, transport_tag="oc2-slice-b:transport",
                base_image_inspect={"RepoDigests": []},
            )
        argv = offline_build_argv(
            self.root, base_ref, transport_tag="oc2-slice-b:transport",
            base_image_inspect={"RepoDigests": [base_ref]},
        )
        self.assertIn("--pull=false", argv)
        self.assertIn("--network=none", argv)
        self.assertEqual(runtime_hash, json.loads(
            (self.root / "build-inputs.json").read_text()
        )["runtime_sha256"])


if __name__ == "__main__":
    unittest.main()
