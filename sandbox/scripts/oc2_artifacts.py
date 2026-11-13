from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sandbox.scripts.oc2_assets import (
    AssetError,
    build_phase4_plugins,
    resolve_superpowers_plugin,
)


@dataclass(frozen=True, slots=True)
class ArtifactPaths:
    root: Path
    superpowers: Path
    akane: Path
    sibyl: Path


@dataclass(frozen=True, slots=True)
class ProvisionInputs:
    repo: Path
    superpowers: Path
    akane: Path
    sibyl: Path
    cache_home: Path | None = None


class ArtifactError(ValueError):
    pass


def artifact_paths(cache_home: Path | None = None) -> ArtifactPaths:
    """Return stable local paths for the explicitly provisioned OC2 artifacts."""
    if cache_home is None:
        configured = os.environ.get('XDG_CACHE_HOME')
        base = Path(configured) if configured else Path.home() / '.cache'
    else:
        base = cache_home
    base = base.expanduser()
    if not base.is_absolute():
        raise ArtifactError('XDG cache directory must be absolute')
    root = base / 'dotfiles-ai' / 'oc2' / 'artifacts-v1'
    return ArtifactPaths(root, root / 'superpowers', root / 'akane.tgz', root / 'sibyl.tgz')


def _verify(paths: ArtifactPaths, repo: Path) -> None:
    if any(path.is_symlink() for path in (paths.root, *paths.root.parents)):
        raise ArtifactError('fixed OC2 artifact cache path contains a symlink')
    if not paths.root.is_dir():
        raise ArtifactError('fixed OC2 artifact directory is missing or linked')
    if paths.root.stat().st_mode & 0o077:
        raise ArtifactError('fixed OC2 artifact directory must be private')
    if {item.name for item in paths.root.iterdir()} != {
        'superpowers', 'akane.tgz', 'sibyl.tgz',
    }:
        raise ArtifactError('fixed OC2 artifact set is incomplete or unexpected')
    try:
        resolve_superpowers_plugin(repo, paths.superpowers)
        build_phase4_plugins(
            repo, (paths.akane, paths.sibyl), explicit_opt_in=True,
        )
    except (AssetError, OSError, ValueError) as exc:
        raise ArtifactError('fixed OC2 artifact identity verification failed') from exc


def provision_artifacts(inputs: ProvisionInputs) -> ArtifactPaths:
    """Validate and cache pinned inputs once for flag-free normal OC2 launches."""
    destination = artifact_paths(inputs.cache_home)
    if destination.root.exists() or destination.root.is_symlink():
        _verify(destination, inputs.repo)
        return destination
    try:
        resolve_superpowers_plugin(inputs.repo, inputs.superpowers)
        build_phase4_plugins(
            inputs.repo, (inputs.akane, inputs.sibyl), explicit_opt_in=True,
        )
    except (AssetError, OSError, ValueError) as exc:
        raise ArtifactError('source artifacts do not match the APM pins') from exc

    parent = destination.root.parent
    if any(path.is_symlink() for path in (parent, *parent.parents)):
        raise ArtifactError('OC2 artifact cache path contains a symlink')
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.oc2-artifacts-', dir=parent) as temporary:
        staging = Path(temporary) / 'artifacts-v1'
        staging.mkdir(mode=0o700)
        shutil.copytree(inputs.superpowers, staging / 'superpowers', symlinks=True)
        shutil.copyfile(inputs.akane, staging / 'akane.tgz')
        shutil.copyfile(inputs.sibyl, staging / 'sibyl.tgz')
        (staging / 'akane.tgz').chmod(0o600)
        (staging / 'sibyl.tgz').chmod(0o600)
        staged = ArtifactPaths(
            staging,
            staging / 'superpowers',
            staging / 'akane.tgz',
            staging / 'sibyl.tgz',
        )
        _verify(staged, inputs.repo)
        try:
            staging.rename(destination.root)
        except OSError as exc:
            if destination.root.exists() or destination.root.is_symlink():
                raise ArtifactError('OC2 artifact cache was concurrently provisioned') from exc
            raise
    return destination
