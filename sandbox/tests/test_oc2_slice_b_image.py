from pathlib import Path
from dataclasses import replace
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import oc2_slice_b_image as image_module
from oc2_slice_b_image import (
    ImagePin,
    SliceBImageRejected,
    verify_build_inputs,
    verify_image_archive,
    verify_loaded_image,
    verify_local_base_image,
    verify_runtime_pin_against_manifest,
)

DOCKER_HOST = "unix:///var/run/docker.sock"


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
            source_revision="f" * 40,
            artifact_sha256="c" * 64,
            runtime_sha256="d" * 64,
            base_image_ref="alpine@sha256:" + "a" * 64,
            build_context_sha256="1" * 64,
            dockerfile_sha256="2" * 64,
            image_ref=self.ref,
            config_id=self.config,
            archive_sha256=hashlib.sha256(self.raw).hexdigest(),
            archive_size_bytes=len(self.raw),
            platform="linux/amd64",
        )
        self.inspect = {
            "Id": self.config,
            "RepoDigests": [self.ref],
            "Os": "linux",
            "Architecture": "amd64",
            "Config": {
                "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                "Cmd": ["run"],
                "User": "10001:10001",
                "WorkingDir": "/workspace",
                "Env": [],
                "Labels": {
                    "dev.oc2.source-revision": self.pin.source_revision,
                    "dev.oc2.artifact-sha256": self.pin.artifact_sha256,
                    "dev.oc2.runtime-sha256": self.pin.runtime_sha256,
                    "dev.oc2.base-image-ref": self.pin.base_image_ref,
                    "dev.oc2.build-context-sha256": self.pin.build_context_sha256,
                },
            },
        }

    def test_host_build_export_records_independent_archive_and_config_identity(self) -> None:
        request_type = getattr(image_module, "ImageBuildRequest", None)
        build_export = getattr(image_module, "build_and_export_image", None)
        self.assertTrue(callable(request_type))
        self.assertTrue(callable(build_export))
        if not callable(request_type) or not callable(build_export):
            return
        runtime_sha256 = self._write_build_context()
        base_ref = "alpine@sha256:" + "a" * 64
        saved = b"host-exported image archive"
        export_path = self.root.parent / "host-export.tar"
        image_config_id = self.config
        initial_config = self.inspect["Config"]

        class FakeHostRunner:
            docker_host = "unix:///var/run/docker.sock"

            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def inspect_image(self, reference: str) -> dict[str, object]:
                self.calls.append(("inspect", reference))
                if reference == base_ref:
                    return {"RepoDigests": [base_ref]}
                return {
                    "Id": self.config_id,
                    "RepoDigests": [],
                    "Os": "linux",
                    "Architecture": "amd64",
                    "Size": 123,
                    "Config": self.config,
                }

            def build_image(self, request, inputs, build_context_sha256: str) -> str:
                self.calls.append(("build", build_context_sha256))
                self.config["Labels"] = {
                    "dev.oc2.source-revision": inputs.source_revision,
                    "dev.oc2.artifact-sha256": inputs.opencode_binary_sha256,
                    "dev.oc2.runtime-sha256": inputs.runtime_sha256,
                    "dev.oc2.base-image-ref": inputs.base_image_ref,
                    "dev.oc2.build-context-sha256": build_context_sha256,
                }
                return self.config_id

            def save_image(self, config_id: str, archive: Path) -> None:
                self.calls.append(("save", config_id))
                archive.write_bytes(saved)

            config_id = image_config_id
            config = initial_config

        runner = FakeHostRunner()
        request = request_type(
            source_root=self.root,
            base_image_ref=base_ref,
            archive_path=export_path,
            docker_host=runner.docker_host,
        )

        pin = build_export(request, runner)

        self.assertEqual(pin.source_revision, "f" * 40)
        self.assertEqual(pin.artifact_sha256, hashlib.sha256(b"binary").hexdigest())
        self.assertEqual(pin.runtime_sha256, runtime_sha256)
        self.assertEqual(pin.base_image_ref, base_ref)
        self.assertEqual(pin.config_id, self.config)
        self.assertEqual(pin.archive_sha256, hashlib.sha256(saved).hexdigest())
        self.assertEqual(pin.archive_size_bytes, len(saved))
        self.assertIsNone(pin.image_ref)
        self.assertEqual([verb for verb, _ in runner.calls], ["inspect", "build", "inspect", "save"])
        self.assertEqual(runner.calls[-1], ("save", self.config))

    def test_guest_import_issues_authority_without_repo_digest(self) -> None:
        request_type = getattr(image_module, "GuestImageLoadRequest", None)
        import_image = getattr(image_module, "import_guest_image", None)
        self.assertTrue(callable(request_type))
        self.assertTrue(callable(import_image))
        if not callable(request_type) or not callable(import_image):
            return
        control_root = self.root / "supervisor-control"
        control_root.mkdir(mode=0o700)
        raw = b"trusted archive bytes"
        pin = replace(
            self.pin,
            archive_sha256=hashlib.sha256(raw).hexdigest(),
            archive_size_bytes=len(raw),
        )
        archive = control_root / (pin.archive_sha256 + ".tar")
        archive.write_bytes(raw)
        archive.chmod(0o600)

        class FakeGuestRunner:
            docker_host = "unix:///var/run/docker.sock"

            def __init__(self) -> None:
                self.calls = []

            def image_ids(self):
                self.calls.append(("list", None))
                return ()

            def load_image(self, path):
                self.calls.append(("load", path))

            def inspect_config_id(self, config_id):
                self.calls.append(("inspect", config_id))
                return {
                    "Id": config_id,
                    "RepoDigests": [],
                    "Os": "linux",
                    "Architecture": "amd64",
                    "Config": {
                        "Entrypoint": ["/opt/oc2/slice-b/entrypoint"],
                        "Cmd": ["run"],
                        "User": "10001:10001",
                        "WorkingDir": "/workspace",
                        "Env": [],
                        "Labels": {
                            "dev.oc2.source-revision": pin.source_revision,
                            "dev.oc2.artifact-sha256": pin.artifact_sha256,
                            "dev.oc2.runtime-sha256": pin.runtime_sha256,
                            "dev.oc2.base-image-ref": pin.base_image_ref,
                            "dev.oc2.build-context-sha256": pin.build_context_sha256,
                        },
                    },
                }

        runner = FakeGuestRunner()
        request = request_type(
            archive_path=archive,
            supervisor_root=control_root,
            image_pin=pin,
            expected_record_sha256=pin.record_sha256,
            docker_host=runner.docker_host,
        )

        authority = import_image(request, runner)

        self.assertEqual(authority.config_id, pin.config_id)
        self.assertEqual(authority.image_record_sha256, pin.record_sha256)
        self.assertEqual([call[0] for call in runner.calls], ["list", "load", "inspect"])
        self.assertEqual(runner.calls[2][1], pin.config_id)

    def test_guest_import_rejects_archive_change_during_load(self) -> None:
        request_type = getattr(image_module, "GuestImageLoadRequest", None)
        import_image = getattr(image_module, "import_guest_image", None)
        self.assertTrue(callable(request_type))
        self.assertTrue(callable(import_image))
        if not callable(request_type) or not callable(import_image):
            return
        control_root = self.root / "supervisor-control"
        control_root.mkdir(mode=0o700)
        archive = control_root / (self.pin.archive_sha256 + ".tar")
        archive.write_bytes(self.raw)
        archive.chmod(0o600)

        class ReplacingGuestRunner:
            docker_host = "unix:///var/run/docker.sock"

            def __init__(self) -> None:
                self.inspect_called = False

            def image_ids(self):
                return ()

            def load_image(self, path):
                path.write_bytes(b"replaced during load")

            def inspect_config_id(self, config_id):
                self.inspect_called = True
                return {}

        runner = ReplacingGuestRunner()
        request = request_type(
            archive_path=archive,
            supervisor_root=control_root,
            image_pin=self.pin,
            expected_record_sha256=self.pin.record_sha256,
            docker_host=runner.docker_host,
        )

        with self.assertRaises(SliceBImageRejected):
            import_image(request, runner)
        self.assertFalse(runner.inspect_called)

    def test_guest_import_refuses_nonempty_image_store_before_load(self) -> None:
        request_type = getattr(image_module, "GuestImageLoadRequest", None)
        import_image = getattr(image_module, "import_guest_image", None)
        self.assertTrue(callable(request_type))
        self.assertTrue(callable(import_image))
        if not callable(request_type) or not callable(import_image):
            return
        control_root = self.root / "supervisor-control"
        control_root.mkdir(mode=0o700)
        archive = control_root / (self.pin.archive_sha256 + ".tar")
        archive.write_bytes(self.raw)
        archive.chmod(0o600)

        class OccupiedGuestRunner:
            docker_host = "unix:///var/run/docker.sock"

            def __init__(self) -> None:
                self.load_called = False

            def image_ids(self):
                return ("sha256:" + "e" * 64,)

            def load_image(self, path):
                self.load_called = True

            def inspect_config_id(self, config_id):
                return {}

        runner = OccupiedGuestRunner()
        request = request_type(
            archive_path=archive,
            supervisor_root=control_root,
            image_pin=self.pin,
            expected_record_sha256=self.pin.record_sha256,
            docker_host=runner.docker_host,
        )

        with self.assertRaises(SliceBImageRejected):
            import_image(request, runner)
        self.assertFalse(runner.load_called)

    def test_image_authority_cannot_be_constructed_from_a_config_id(self) -> None:
        authority_type = getattr(image_module, "VerifiedImageAuthority", None)
        self.assertIsNotNone(authority_type)
        if authority_type is None:
            return
        with self.assertRaises(TypeError):
            authority_type(
                self.pin,
                self.pin.record_sha256,
                self.pin.config_id,
                self.pin.platform,
            )

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

    def test_loaded_config_id_does_not_require_repo_digest(self) -> None:
        d = {**self.inspect, "RepoDigests": []}
        try:
            verify_loaded_image(d, self.pin)
        except SliceBImageRejected as error:
            self.fail(f"archive-pinned Config ID was rejected: {error}")

    def test_loaded_image_rejects_runtime_label_mismatch(self) -> None:
        config = {**self.inspect["Config"], "Labels": {
            **self.inspect["Config"]["Labels"],
            "dev.oc2.runtime-sha256": "e" * 64,
        }}
        with self.assertRaises(SliceBImageRejected):
            verify_loaded_image({**self.inspect, "Config": config}, self.pin)

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

    def test_image_pin_encodes_archive_size_and_canonical_record_hash(self) -> None:
        self.assertEqual(getattr(self.pin, "archive_size_bytes", None), len(self.raw))
        encoder = getattr(self.pin, "to_bytes", None)
        self.assertTrue(callable(encoder))
        if not callable(encoder):
            return
        encoded = encoder()
        self.assertEqual(encoded, encoder())
        self.assertEqual(
            getattr(self.pin, "record_sha256", None),
            hashlib.sha256(encoded).hexdigest(),
        )

    def test_image_pin_roundtrips_only_canonical_record_bytes(self) -> None:
        encoder = getattr(self.pin, "to_bytes", None)
        decoder = getattr(ImagePin, "from_bytes", None)
        self.assertTrue(callable(encoder))
        self.assertTrue(callable(decoder))
        if not callable(encoder) or not callable(decoder):
            return
        encoded = encoder()

        self.assertEqual(decoder(encoded, self.pin.record_sha256), self.pin)
        with self.assertRaises(SliceBImageRejected):
            decoder(encoded + b" ", self.pin.record_sha256)

    def test_archive_verification_checks_recorded_size(self) -> None:
        from dataclasses import replace

        with self.assertRaises(SliceBImageRejected):
            verify_image_archive(self.archive, replace(
                self.pin, archive_size_bytes=len(self.raw) + 1,
            ))

    def test_unpinned_build_inputs_blocked(self) -> None:
        """Build input verification refuses a missing trust manifest."""
        with self.assertRaises(SliceBImageRejected):
            verify_build_inputs(self.root)

    def _write_build_context(self) -> str:
        """Create a complete locally pinned Docker context and return its runtime digest."""
        runtime = Path(__file__).resolve().parents[1] / "oc2_slice_b"
        shutil.copyfile(runtime / "entrypoint.py", self.root / "entrypoint.py")
        shutil.copyfile(runtime / "offline_fixture.py", self.root / "offline_fixture.py")
        shutil.copyfile(runtime / "Dockerfile", self.root / "Dockerfile")
        (self.root / "opencode-v2.2.5").write_bytes(b"binary")
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
        absent = subprocess.CompletedProcess(
            ["docker", "image", "inspect", base_ref],
            0,
            json.dumps([{"RepoDigests": []}]),
            "",
        )
        with self.assertRaises(SliceBImageRejected):
            with patch("oc2_slice_b_image_host._run_docker_command", return_value=absent):
                offline_build_argv(self.root, base_ref, docker_host=DOCKER_HOST)
        present = subprocess.CompletedProcess(
            ["docker", "image", "inspect", base_ref],
            0,
            json.dumps([{"RepoDigests": [base_ref]}]),
            "",
        )
        with patch("oc2_slice_b_image_host._run_docker_command", return_value=present):
            argv = offline_build_argv(self.root, base_ref, docker_host=DOCKER_HOST)
        self.assertIn("--pull=false", argv)
        self.assertIn("--network=none", argv)
        self.assertIn("--quiet", argv)
        self.assertNotIn("-t", argv)
        self.assertEqual(runtime_hash, json.loads(
            (self.root / "build-inputs.json").read_text()
        )["runtime_sha256"])

    def test_build_executor_aborts_before_build_when_base_is_missing(self) -> None:
        """A failed local image inspect prevents the Docker build command."""
        self._write_build_context()
        from oc2_slice_b_image import build_offline_image

        missing = subprocess.CompletedProcess(
            ["docker", "image", "inspect"], 1, "", "not found"
        )
        with patch("oc2_slice_b_image_host._run_docker_command", return_value=missing) as run:
            with self.assertRaises(SliceBImageRejected):
                build_offline_image(
                    self.root,
                    "alpine@sha256:" + "a" * 64,
                    docker_host=DOCKER_HOST,
                )
        self.assertEqual(run.call_count, 1)

    def test_build_executor_inspects_before_running_offline_build(self) -> None:
        """The actual build executor verifies local RepoDigests before invoking build."""
        self._write_build_context()
        from oc2_slice_b_image import build_offline_image

        base_ref = "alpine@sha256:" + "a" * 64
        inspected = subprocess.CompletedProcess(
            ["docker", "image", "inspect", base_ref],
            0,
            json.dumps([{"RepoDigests": [base_ref]}]),
            "",
        )
        built = subprocess.CompletedProcess(["docker", "build"], 0, "sha256:" + "b" * 64, "")
        with patch(
            "oc2_slice_b_image_host._run_docker_command",
            side_effect=(inspected, built),
        ) as run:
            build_offline_image(
                self.root,
                base_ref,
                docker_host=DOCKER_HOST,
            )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0][:5],
            ("docker", "--host", DOCKER_HOST, "image", "inspect"),
        )
        self.assertIn("--network=none", run.call_args_list[1].args[0])

    def test_build_argv_fetches_its_own_local_inspection(self) -> None:
        """Callers cannot replace the local base image inspection with supplied data."""
        self._write_build_context()
        from oc2_slice_b_image import offline_build_argv

        base_ref = "alpine@sha256:" + "a" * 64
        inspected = subprocess.CompletedProcess(
            ["docker", "image", "inspect", base_ref],
            0,
            json.dumps([{"RepoDigests": [base_ref]}]),
            "",
        )
        with patch("oc2_slice_b_image_host._run_docker_command", return_value=inspected) as run:
            argv = offline_build_argv(self.root, base_ref, docker_host=DOCKER_HOST)
        run.assert_called_once_with(
            ("docker", "--host", DOCKER_HOST, "image", "inspect", base_ref),
            DOCKER_HOST,
        )
        self.assertIn("--network=none", argv)


if __name__ == "__main__":
    unittest.main()
