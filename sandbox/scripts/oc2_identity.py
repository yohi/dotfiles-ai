"""Deterministic identities for isolated OpenCode runtimes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_GENERATOR_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-verification-generator/v2\0'
_RUNTIME_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-verification-runtime/v1\0'
_PHASE4_GENERATOR_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-phase4-generator/v1\0'
_PHASE4_RUNTIME_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-phase4-runtime/v1\0'


@dataclass(frozen=True, slots=True)
class Phase4RuntimeIdentity:
    manifest_sha256: str
    base_assets_sha256: str
    plugin_assets_sha256: str
    generator_sha256: str


def verification_generator_fingerprint(
    guest_script: Path,
    native_helper: Path,
    identity_helper: Path,
) -> str:
    """Fingerprint the Guest materializer and both imported helper modules."""
    digest = hashlib.sha256(_GENERATOR_NAMESPACE)
    for path in (guest_script, native_helper, identity_helper):
        if path.is_symlink() or not path.is_file():
            raise OSError('verification generator source is missing or linked')
        digest.update(path.name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def runtime_identity_sha256(
    manifest_sha256: str,
    assets_sha256: str,
    generator_fingerprint: str | None = None,
) -> str:
    """Return the legacy or generator-aware full runtime identity digest."""
    material = bytes.fromhex(manifest_sha256) + bytes.fromhex(assets_sha256)
    if generator_fingerprint is None:
        return hashlib.sha256(material).hexdigest()
    return hashlib.sha256(
        _RUNTIME_NAMESPACE + material + bytes.fromhex(generator_fingerprint),
    ).hexdigest()


def phase4_generator_fingerprint(paths: tuple[Path, ...]) -> str:
    """Fingerprint the ordered Phase 4 Guest verifier and policy sources."""
    digest = hashlib.sha256(_PHASE4_GENERATOR_NAMESPACE)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise OSError('Phase 4 generator source is missing or linked')
        digest.update(path.name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def phase4_runtime_identity_sha256(identity: Phase4RuntimeIdentity) -> str:
    """Create a Phase 4-only identity from config, assets, plugins and code."""
    material = b''.join(bytes.fromhex(value) for value in (
        identity.manifest_sha256,
        identity.base_assets_sha256,
        identity.plugin_assets_sha256,
        identity.generator_sha256,
    ))
    return hashlib.sha256(_PHASE4_RUNTIME_NAMESPACE + material).hexdigest()
