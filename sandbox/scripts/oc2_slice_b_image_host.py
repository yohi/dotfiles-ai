"""Offline Host build/export orchestration for the immutable Slice B image record."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Protocol

from oc2_slice_b_image_build import (
    BuildInputs,
    build_context_sha256,
    snapshot_build_context,
    verify_build_inputs,
)
from oc2_slice_b_image_record import (
    ImagePin,
    SliceBImageRejected,
    _BASE_IMAGE_DIGESTS,
    _IMAGE_ID,
    _MAX_ARCHIVE,
    _REF,
    _sha_file,
    _validate_docker_host,
    _validate_pin,
)
from oc2_slice_b_image_verify import _validate_image_config, verify_local_base_image


@dataclass(frozen=True, slots=True)
class ImageBuildRequest:
    source_root: Path
    supervisor_snapshot: Path
    base_image_ref: str
    archive_path: Path
    docker_host: str


@dataclass(frozen=True, slots=True)
class _BuiltImage:
    request: ImageBuildRequest
    inputs: BuildInputs
    context_sha256: str
    config_id: str


class HostImageRunner(Protocol):
    @property
    def docker_host(self) -> str: ...

    def inspect_image(self, reference: str) -> Mapping[str, Any]: ...

    def build_image(
        self,
        request: ImageBuildRequest,
        inputs: BuildInputs,
        build_context_sha256: str,
    ) -> str: ...

    def save_image(self, config_id: str, archive: Path) -> None: ...


def offline_build_argv(
    source_root: Path,
    base_ref: str,
    *,
    docker_host: str,
    supervisor_snapshot: Path,
) -> tuple[str, ...]:
    inputs = verify_build_inputs(source_root, supervisor_snapshot)
    if not _BASE_IMAGE_DIGESTS.fullmatch(base_ref) or base_ref != inputs.base_image_ref:
        raise SliceBImageRejected("base must match the trusted digest-pinned input")
    endpoint = _validate_docker_host(docker_host)
    verify_local_base_image(_inspect_local_base_image(base_ref, endpoint), base_ref)
    context = snapshot_build_context(source_root, supervisor_snapshot)
    try:
        context_sha256 = build_context_sha256(context)
        return (
            "docker", "--host", endpoint, "build", "--quiet", "--pull=false", "--network=none",
            "--build-arg", "BASE_IMAGE=" + base_ref,
            "--build-arg", "SOURCE_REVISION=" + inputs.source_revision,
            "--build-arg", "ARTIFACT_SHA256=" + inputs.opencode_binary_sha256,
            "--build-arg", "RUNTIME_SHA256=" + inputs.runtime_sha256,
            "--build-arg", "BUILD_CONTEXT_SHA256=" + context_sha256,
            str(context),
        )
    except (OSError, SliceBImageRejected):
        shutil.rmtree(context)
        raise


def build_offline_image(
    source_root: Path,
    base_ref: str,
    *,
    docker_host: str,
    supervisor_snapshot: Path,
) -> str:
    endpoint = _validate_docker_host(docker_host)
    argv = offline_build_argv(
        source_root, base_ref, docker_host=endpoint,
        supervisor_snapshot=supervisor_snapshot,
    )
    context = Path(argv[-1])
    try:
        result = _run_docker_command(argv, endpoint)
        if result.returncode != 0:
            raise SliceBImageRejected("offline Writer image build failed")
        config_id = result.stdout.strip()
        if not _IMAGE_ID.fullmatch(config_id):
            raise SliceBImageRejected("offline Writer image build returned no Config ID")
        return config_id
    finally:
        shutil.rmtree(context)


def build_and_export_image(request: ImageBuildRequest, runner: HostImageRunner) -> ImagePin:
    if not isinstance(request, ImageBuildRequest):
        raise SliceBImageRejected("invalid Host image build request")
    docker_host = _validate_docker_host(request.docker_host)
    if runner.docker_host != docker_host:
        raise SliceBImageRejected("Host Docker socket does not match the build request")
    if request.source_root.is_symlink():
        raise SliceBImageRejected("Host image build source must not be a symlink")
    root = request.source_root.resolve(strict=True)
    inputs = verify_build_inputs(root, request.supervisor_snapshot)
    if (
        request.base_image_ref != inputs.base_image_ref
        or not request.archive_path.is_absolute()
        or ".." in request.archive_path.parts
        or request.archive_path.exists()
        or request.archive_path.is_symlink()
        or not request.archive_path.parent.is_dir()
    ):
        raise SliceBImageRejected("untrusted Host image build destination or identity")
    verify_local_base_image(
        runner.inspect_image(request.base_image_ref), request.base_image_ref,
    )
    context = snapshot_build_context(root, request.supervisor_snapshot)
    try:
        inputs = verify_build_inputs(context, request.supervisor_snapshot)
        context_sha256 = build_context_sha256(context)
        snapshot_request = replace(request, source_root=context)
        config_id = runner.build_image(snapshot_request, inputs, context_sha256)
        if not _IMAGE_ID.fullmatch(config_id):
            raise SliceBImageRejected("offline build did not return an image Config ID")
        return _complete_image_export(
            runner,
            _BuiltImage(snapshot_request, inputs, context_sha256, config_id),
        )
    finally:
        shutil.rmtree(context)


def _complete_image_export(
    runner: HostImageRunner,
    built: _BuiltImage,
) -> ImagePin:
    request = built.request
    inputs = built.inputs
    context_sha256 = built.context_sha256
    config_id = built.config_id
    root = request.source_root
    built_inspect = runner.inspect_image(config_id)
    dockerfile_sha256 = _sha_file(root / "Dockerfile", 64 * 1024)
    _validate_image_config(
        built_inspect,
        config_id=config_id,
        platform="linux/amd64",
        labels={
            "dev.oc2.source-revision": inputs.source_revision,
            "dev.oc2.artifact-sha256": inputs.opencode_binary_sha256,
            "dev.oc2.runtime-sha256": inputs.runtime_sha256,
            "dev.oc2.base-image-ref": inputs.base_image_ref,
            "dev.oc2.build-context-sha256": context_sha256,
        },
    )
    runner.save_image(config_id, request.archive_path)
    archive_sha256 = _sha_file(request.archive_path, _MAX_ARCHIVE)
    archive_stat = request.archive_path.lstat()
    if archive_stat.st_size < 1:
        raise SliceBImageRejected("Host image archive is empty")
    refs = built_inspect.get("RepoDigests")
    origin_ref = next(
        (ref for ref in refs if isinstance(ref, str) and _REF.fullmatch(ref)),
        None,
    ) if isinstance(refs, list) else None
    pin = ImagePin(
        source_revision=inputs.source_revision,
        artifact_sha256=inputs.opencode_binary_sha256,
        runtime_sha256=inputs.runtime_sha256,
        base_image_ref=inputs.base_image_ref,
        build_context_sha256=context_sha256,
        dockerfile_sha256=dockerfile_sha256,
        image_ref=origin_ref,
        config_id=config_id,
        archive_sha256=archive_sha256,
        archive_size_bytes=archive_stat.st_size,
        platform="linux/amd64",
    )
    _validate_pin(pin)
    return pin


def _run_docker_command(
    argv: tuple[str, ...], docker_host: str,
) -> subprocess.CompletedProcess[str]:
    endpoint = _validate_docker_host(docker_host)
    if len(argv) < 4 or argv[:3] != ("docker", "--host", endpoint):
        raise SliceBImageRejected("Docker command does not use its explicit socket")
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"},
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SliceBImageRejected("Docker command failed") from error


def _inspect_local_base_image(base_ref: str, docker_host: str) -> Mapping[str, Any]:
    if not _BASE_IMAGE_DIGESTS.fullmatch(base_ref):
        raise SliceBImageRejected("base image must use an immutable digest ref")
    result = _run_docker_command(
        ("docker", "--host", docker_host, "image", "inspect", base_ref), docker_host,
    )
    if result.returncode != 0:
        raise SliceBImageRejected("pinned base image is not available locally")
    try:
        values = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise SliceBImageRejected("invalid local base image inspection") from error
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], Mapping):
        raise SliceBImageRejected("invalid local base image inspection")
    return values[0]
