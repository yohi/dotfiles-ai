"""Deterministic identities for isolated OpenCode runtimes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

_GENERATOR_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-verification-generator/v2\0'
_RUNTIME_NAMESPACE: Final[bytes] = b'dotfiles-ai/oc2-verification-runtime/v1\0'


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
