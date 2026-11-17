"""Constrained explicit-socket Docker adapters for Slice B image operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

from oc2_slice_b_image_build import BuildInputs
from oc2_slice_b_image_host import ImageBuildRequest
from oc2_slice_b_image_record import SliceBImageRejected, _validate_docker_host

_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DIGEST_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")
_MAX_INSPECT_BYTES = 4 * 1024 * 1024
_TIMEOUT_SECONDS = 300


def _docker_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or os.path.normpath(value) != value
        or Path(value).name != "docker"
    ):
        raise SliceBImageRejected("Docker executable path is not canonical")
    return value


def _environment() -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}


def _inspect_record(raw: str) -> Mapping[str, Any]:
    try:
        values = json.loads(raw)
    except (TypeError, ValueError, UnicodeError) as error:
        raise SliceBImageRejected("invalid Docker image inspection") from error
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], Mapping):
        raise SliceBImageRejected("unexpected Docker image inspection shape")
    return values[0]


class DockerHostImageRunner:
    """Build and export only the pinned Slice B image through one explicit Host socket."""

    def __init__(self, docker_path: str, docker_host: str) -> None:
        self._docker_path = _docker_path(docker_path)
        self._docker_host = _validate_docker_host(docker_host)

    @property
    def docker_host(self) -> str:
        return self._docker_host

    def inspect_image(self, reference: str) -> Mapping[str, Any]:
        if not isinstance(reference, str) or not (
            _DIGEST_REF.fullmatch(reference)
            or _IMAGE_ID.fullmatch(reference)
        ):
            raise SliceBImageRejected("Host image inspect reference is not allowlisted")
        output = self._run("image", "inspect", reference)
        return _inspect_record(output)

    def build_image(
        self,
        request: ImageBuildRequest,
        inputs: BuildInputs,
        build_context_sha256: str,
    ) -> str:
        if (
            request.docker_host != self._docker_host
            or request.base_image_ref != inputs.base_image_ref
        ):
            raise SliceBImageRejected("Host image build request does not match pinned inputs")
        args = (
            "build", "--quiet", "--pull=false", "--network=none",
            "--build-arg", "BASE_IMAGE=" + inputs.base_image_ref,
            "--build-arg", "SOURCE_REVISION=" + inputs.source_revision,
            "--build-arg", "ARTIFACT_SHA256=" + inputs.opencode_binary_sha256,
            "--build-arg", "RUNTIME_SHA256=" + inputs.runtime_sha256,
            "--build-arg", "BUILD_CONTEXT_SHA256=" + build_context_sha256,
            str(request.source_root.resolve(strict=True)),
        )
        config_id = self._run(*args).strip()
        if not _IMAGE_ID.fullmatch(config_id):
            raise SliceBImageRejected("Host offline build returned no Config ID")
        return config_id

    def save_image(self, config_id: str, archive: Path) -> None:
        if not _IMAGE_ID.fullmatch(config_id):
            raise SliceBImageRejected("Host image save requires the built Config ID")
        if not archive.is_absolute() or archive.exists() or archive.is_symlink():
            raise SliceBImageRejected("Host image archive destination must be new")
        if not archive.parent.is_dir() or archive.parent.is_symlink():
            raise SliceBImageRejected("Host image archive parent is unsafe")
        try:
            parent_stat = archive.parent.stat()
        except OSError as error:
            raise SliceBImageRejected("Host image archive parent is unavailable") from error
        if parent_stat.st_uid != os.geteuid() or stat.S_IMODE(parent_stat.st_mode) != 0o700:
            raise SliceBImageRejected("Host image archive parent is not Supervisor-private")
        try:
            descriptor = os.open(
                archive,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as error:
            raise SliceBImageRejected("Host image archive destination unavailable") from error
        try:
            with os.fdopen(descriptor, "wb") as stream:
                result = subprocess.run(
                    [
                        self._docker_path, "--host", self._docker_host,
                        "image", "save", config_id,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.DEVNULL,
                    env=_environment(),
                    timeout=_TIMEOUT_SECONDS,
                    check=False,
                )
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SliceBImageRejected("Host image save failed") from error
        if result.returncode != 0:
            raise SliceBImageRejected("Host image save failed")

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                [self._docker_path, "--host", self._docker_host, *args],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env=_environment(),
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SliceBImageRejected("Host Docker image operation failed") from error
        if result.returncode != 0 or len(result.stdout.encode("utf-8")) > _MAX_INSPECT_BYTES:
            raise SliceBImageRejected("Host Docker image operation failed")
        return result.stdout


class DockerGuestImageRunner:
    """Load and inspect only Host-pinned images through one explicit Guest socket."""

    def __init__(self, docker_path: str, docker_host: str, supervisor_root: Path) -> None:
        self._docker_path = _docker_path(docker_path)
        self._docker_host = _validate_docker_host(docker_host)
        self._supervisor_root = supervisor_root

    @property
    def docker_host(self) -> str:
        return self._docker_host

    def image_ids(self) -> tuple[str, ...]:
        output = self._run("image", "ls", "--all", "--quiet", "--no-trunc")
        ids = tuple(line for line in output.splitlines() if line)
        if any(not _IMAGE_ID.fullmatch(image_id) for image_id in ids):
            raise SliceBImageRejected("Guest Docker image listing is malformed")
        return ids

    def load_image(self, archive: Path) -> None:
        self._validate_archive_path(archive)
        self._run("image", "load", "--input", str(archive))

    def inspect_config_id(self, config_id: str) -> Mapping[str, Any]:
        if not isinstance(config_id, str) or not _IMAGE_ID.fullmatch(config_id):
            raise SliceBImageRejected("Guest image inspection requires exact Config ID")
        return _inspect_record(self._run("image", "inspect", config_id))

    def _validate_archive_path(self, archive: Path) -> None:
        if archive.parent != self._supervisor_root or archive.is_symlink():
            raise SliceBImageRejected("Guest image archive is outside Supervisor control")
        try:
            root_stat = self._supervisor_root.lstat()
            archive_stat = archive.lstat()
        except OSError as error:
            raise SliceBImageRejected("Guest image archive is unavailable") from error
        if (
            root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
            or not stat.S_ISDIR(root_stat.st_mode)
            or archive_stat.st_uid != os.geteuid()
            or stat.S_IMODE(archive_stat.st_mode) != 0o600
            or not stat.S_ISREG(archive_stat.st_mode)
            or archive_stat.st_nlink != 1
        ):
            raise SliceBImageRejected("Guest image archive metadata is unsafe")

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                [self._docker_path, "--host", self._docker_host, *args],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env=_environment(),
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SliceBImageRejected("Guest Docker image operation failed") from error
        if result.returncode != 0 or len(result.stdout.encode("utf-8")) > _MAX_INSPECT_BYTES:
            raise SliceBImageRejected("Guest Docker image operation failed")
        return result.stdout
