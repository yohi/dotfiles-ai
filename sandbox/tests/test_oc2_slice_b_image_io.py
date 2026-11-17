from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from oc2_slice_b_image import BuildInputs, ImageBuildRequest  # noqa: E402
import oc2_slice_b_image_io as image_io  # noqa: E402


class ImageRunnerTests(unittest.TestCase):
    def test_host_runner_inspect_uses_explicit_socket_without_context_environment(self) -> None:
        response = json.dumps([{"Id": "sha256:" + "a" * 64}])
        completed = subprocess.CompletedProcess([], 0, response, "")
        with patch.object(image_io.subprocess, "run", return_value=completed) as run:
            runner = image_io.DockerHostImageRunner(
                "/usr/bin/docker", "unix:///run/user/1000/docker.sock",
            )
            result = runner.inspect_image("alpine@sha256:" + "b" * 64)

        self.assertEqual(result["Id"], "sha256:" + "a" * 64)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], [
            "/usr/bin/docker", "--host", "unix:///run/user/1000/docker.sock", "image",
        ])
        self.assertEqual(argv[4], "inspect")
        self.assertNotIn("DOCKER_HOST", run.call_args.kwargs["env"])
        self.assertNotIn("DOCKER_CONFIG", run.call_args.kwargs["env"])

    def test_host_runner_build_is_offline_and_uses_pinned_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = ImageBuildRequest(
                source_root=root,
                base_image_ref="alpine@sha256:" + "a" * 64,
                archive_path=root / "writer.tar",
                docker_host="unix:///run/user/1000/docker.sock",
            )
            inputs = BuildInputs(
                request.base_image_ref,
                "b" * 64,
                "c" * 64,
                "d" * 40,
            )
            expected_id = "sha256:" + "f" * 64
            completed = subprocess.CompletedProcess([], 0, expected_id, "")
            with patch.object(image_io.subprocess, "run", return_value=completed) as run:
                runner = image_io.DockerHostImageRunner(
                    "/usr/bin/docker", request.docker_host,
                )
                config_id = runner.build_image(request, inputs, "e" * 64)

        self.assertEqual(config_id, expected_id)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], [
            "/usr/bin/docker", "--host", request.docker_host, "build",
        ])
        self.assertIn("--pull=false", argv)
        self.assertIn("--network=none", argv)
        self.assertIn("--quiet", argv)
        self.assertNotIn("-t", argv)
        self.assertIn("BASE_IMAGE=" + request.base_image_ref, argv)
        self.assertNotIn("DOCKER_HOST", run.call_args.kwargs["env"])

    def test_host_runner_saves_by_config_id_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            archive = root / "writer.tar"

            def write_archive(argv, **kwargs):
                kwargs["stdout"].write(b"config-id archive")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch.object(image_io.subprocess, "run", side_effect=write_archive) as run:
                runner = image_io.DockerHostImageRunner(
                    "/usr/bin/docker", "unix:///run/user/1000/docker.sock",
                )
                runner.save_image("sha256:" + "f" * 64, archive)

            self.assertEqual(archive.read_bytes(), b"config-id archive")
            self.assertEqual(run.call_args.args[0][-3:], [
                "image", "save", "sha256:" + "f" * 64,
            ])
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)

    def test_guest_runner_load_and_inspect_are_explicitly_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            archive = root / "image.tar"
            archive.write_bytes(b"archive")
            archive.chmod(0o600)
            inspect_output = json.dumps([{"Id": "sha256:" + "c" * 64}])
            load_result = subprocess.CompletedProcess([], 0, "Loaded image ID", "")
            inspect_result = subprocess.CompletedProcess([], 0, inspect_output, "")
            with patch.object(
                image_io.subprocess,
                "run",
                side_effect=(load_result, inspect_result),
            ) as run:
                runner = image_io.DockerGuestImageRunner(
                    "/usr/bin/docker",
                    "unix:///var/run/docker.sock",
                    root,
                )
                runner.load_image(archive)
                observed = runner.inspect_config_id("sha256:" + "c" * 64)

        self.assertEqual(observed["Id"], "sha256:" + "c" * 64)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:4], [
            "/usr/bin/docker", "--host", "unix:///var/run/docker.sock", "image",
        ])
        self.assertEqual(commands[0][4:6], ["load", "--input"])
        self.assertEqual(commands[1][4:], ["inspect", "sha256:" + "c" * 64])
        self.assertNotIn("DOCKER_HOST", run.call_args_list[0].kwargs["env"])

    def test_guest_runner_rejects_archive_outside_control_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "control"
            root.mkdir(mode=0o700)
            outside = Path(temporary) / "outside.tar"
            outside.write_bytes(b"archive")
            runner = image_io.DockerGuestImageRunner(
                "/usr/bin/docker", "unix:///var/run/docker.sock", root,
            )
            with patch.object(image_io.subprocess, "run") as run:
                with self.assertRaises(image_io.SliceBImageRejected):
                    runner.load_image(outside)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
