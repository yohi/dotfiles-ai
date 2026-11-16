"""Slice B immutable Session receipt and Guest Baseline Authority.

No Docker, Sandbox, privileged Writer, credentials or Host Git mutations.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, asdict, replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from oc2_slice_b_git import (
    BundleArtifact,
    GitBaseline,
    SliceBBundleManifestV1,
    SliceBGitRejected,
    _git,
    _manifest_bytes,
    _key_dict,
    _SHA256,
    _REF,
    verify_bundle_manifest,
    admit_clean_repo,
)

_IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FULL_CID = re.compile(r"[0-9a-f]{64}\Z")
_STATES = {"REJECTED", "RUNNING", "PENDING", "PRESERVATION_UNVERIFIED"}


class SliceBSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SliceBReceipt:
    key: object
    baseline: GitBaseline
    bundle_sha256: str
    manifest_sha256: str
    transfer_policy_id: str
    runtime_sha256: str
    image_ref: str
    image_config_id: str
    state: str
    reason: str | None
    writer_id: str | None
    started_at: str | None


@dataclass(frozen=True)
class VerifiedGuestAuthority:
    key: object
    manifest: SliceBBundleManifestV1
    manifest_sha256: str
    image_ref: str
    image_config_id: str


@dataclass(frozen=True)
class SliceBStartMessage:
    session_generation: str
    head_oid: str
    branch_ref: str
    manifest_sha256: str

    def to_wire(self) -> str:
        """Serialize a bounded newline-terminated start frame; oversize raises SliceBSessionError."""
        line = (
            "OC2_SLICE_B_START "
            + " ".join(
                (
                    self.session_generation,
                    self.head_oid,
                    self.branch_ref,
                    self.manifest_sha256,
                )
            )
            + "\n"
        )
        if len(line.encode("ascii")) > 512:
            raise SliceBSessionError("startup frame too large")
        return line


def _private_dir(path: Path) -> None:
    """Create or validate a normalized private directory, rejecting symlink ancestors."""
    if not path.is_absolute() or ".." in path.parts:
        raise SliceBSessionError("state root must be absolute and normalized")
    cur = Path("/")
    for part in path.parts[1:]:
        cur = cur / part
        if cur.is_symlink():
            raise SliceBSessionError("symlink in state root")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise SliceBSessionError("invalid state root")
    os.chmod(path, 0o700)


def _encode_receipt(receipt: SliceBReceipt) -> bytes:
    """Encode the complete receipt as deterministic canonical JSON bytes."""
    b = asdict(receipt.baseline)
    b["root"] = str(b["root"])
    x = {
        "key": _key_dict(receipt.key),
        "baseline": b,
        "bundle_sha256": receipt.bundle_sha256,
        "manifest_sha256": receipt.manifest_sha256,
        "transfer_policy_id": receipt.transfer_policy_id,
        "runtime_sha256": receipt.runtime_sha256,
        "image_ref": receipt.image_ref,
        "image_config_id": receipt.image_config_id,
        "state": receipt.state,
        "reason": receipt.reason,
        "writer_id": receipt.writer_id,
        "started_at": receipt.started_at,
    }
    return (
        json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _validate_receipt(receipt: SliceBReceipt) -> None:
    """Validate identity, states REJECTED/RUNNING/PENDING/PRESERVATION_UNVERIFIED, and Writer fields.

    RUNNING requires both Writer ID and start time; other states retain the
    existing paired-presence rule. This validates a single value, not history.
    """
    try:
        _key_dict(receipt.key)
    except SliceBGitRejected as e:
        raise SliceBSessionError("invalid receipt SessionKey") from e
    if (
        receipt.state not in _STATES
        or receipt.transfer_policy_id != "oc2-slice-b-clean-git-bundle-v1"
        or any(
            not _SHA256.fullmatch(x)
            for x in (
                receipt.bundle_sha256,
                receipt.manifest_sha256,
                receipt.runtime_sha256,
            )
        )
        or not _IMAGE.fullmatch(receipt.image_ref)
        or not _IMAGE_ID.fullmatch(receipt.image_config_id)
    ):
        raise SliceBSessionError("invalid receipt identity")
    if receipt.writer_id is not None and (
        not isinstance(receipt.writer_id, str) or not _FULL_CID.fullmatch(receipt.writer_id)
    ):
        raise SliceBSessionError("invalid Writer Container ID")
    if receipt.started_at is not None and not isinstance(receipt.started_at, str):
        raise SliceBSessionError("invalid Writer start time")
    if bool(receipt.writer_id) != bool(receipt.started_at):
        raise SliceBSessionError("incomplete Writer identity")
    if receipt.state == "RUNNING" and (not receipt.writer_id or not receipt.started_at):
        raise SliceBSessionError("RUNNING receipt requires Writer identity")
    if receipt.reason is not None and (
        not isinstance(receipt.reason, str) or len(receipt.reason) > 200
    ):
        raise SliceBSessionError("invalid bounded reason")


def _read_strict(path: Path) -> bytes:
    """Read a private, single-link regular receipt file within the fixed size limit."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        s = os.fstat(fd)
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_nlink != 1
            or s.st_size > 16_384
            or s.st_mode & 0o077
        ):
            raise SliceBSessionError("unsafe receipt metadata")
        raw = os.read(fd, 16_385)
        if len(raw) != s.st_size:
            raise SliceBSessionError("partial receipt")
        return raw
    finally:
        os.close(fd)


def create_session_receipt(
    state_root: Path, receipt: SliceBReceipt, artifact: BundleArtifact
) -> Path:
    """Verify artifact identity, then create immutable manifest and receipt files.

    Requires a verified BundleArtifact and matching receipt. Files are created
    with O_EXCL, flushed and fsynced; failures may leave already-created files
    because this two-file create path does not roll back partial writes. Git
    verification exceptions are not universally converted to SliceBSessionError.
    """
    _validate_receipt(receipt)
    if receipt.baseline.root.resolve().is_relative_to(state_root.resolve()):
        raise SliceBSessionError("state root cannot contain the Host repository")
    if state_root.resolve().is_relative_to(receipt.baseline.root.resolve()):
        raise SliceBSessionError("receipt must be outside Host Git workspace")
    if (
        artifact.key != receipt.key
        or artifact.baseline != receipt.baseline
        or artifact.bundle_sha256 != receipt.bundle_sha256
        or artifact.manifest_sha256 != receipt.manifest_sha256
        or artifact.runtime_sha256 != receipt.runtime_sha256
    ):
        raise SliceBSessionError("receipt/Bundle identity mismatch")
    verify_bundle_manifest(
        artifact,
        expected_key=receipt.key,
        expected_manifest_sha256=receipt.manifest_sha256,
        expected_runtime_sha256=receipt.runtime_sha256,
    )
    k = _key_dict(receipt.key)
    parent = state_root / k["workspace_id"] / k["session_generation"]
    _private_dir(parent)
    dest = parent / "receipt.json"
    manifest = parent / "bundle.manifest.json"
    if dest.exists() or manifest.exists():
        raise SliceBSessionError("session receipt already exists")
    for name, payload in (
        (manifest, artifact.manifest_path.read_bytes()),
        (dest, _encode_receipt(receipt)),
    ):
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return Path(dest)


def verify_session_receipt(path: Path, expected_key: object) -> SliceBReceipt:
    """Read and validate receipt plus copied Manifest; malformed data becomes SliceBSessionError.

    Underlying Git baseline inspection is not performed by this function.
    """
    try:
        raw = _read_strict(path)
        mraw = _read_strict(path.with_name("bundle.manifest.json"))
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {
            "key",
            "baseline",
            "bundle_sha256",
            "manifest_sha256",
            "transfer_policy_id",
            "runtime_sha256",
            "image_ref",
            "image_config_id",
            "state",
            "reason",
            "writer_id",
            "started_at",
        }:
            raise SliceBSessionError("receipt schema mismatch")
        if data["key"] != _key_dict(expected_key):
            raise SliceBSessionError("receipt SessionKey changed")
        b = data["baseline"]
        if set(b) != {
            "root",
            "branch_ref",
            "head_oid",
            "tree_oid",
            "object_format",
            "index_sha256",
            "worktree_sha256",
        }:
            raise SliceBSessionError("baseline shape mismatch")
        base = GitBaseline(
            Path(b["root"]),
            b["branch_ref"],
            b["head_oid"],
            b["tree_oid"],
            b["object_format"],
            b["index_sha256"],
            b["worktree_sha256"],
        )
        rec = SliceBReceipt(
            key=expected_key,
            baseline=base,
            **{k: v for k, v in data.items() if k not in ("key", "baseline")},
        )
        _validate_receipt(rec)
        if (
            raw != _encode_receipt(rec)
            or hashlib.sha256(mraw).hexdigest() != rec.manifest_sha256
        ):
            raise SliceBSessionError("noncanonical or tampered receipt/manifest")
        if path.parent.name != _key_dict(expected_key)["session_generation"]:
            raise SliceBSessionError("wrong receipt generation directory")
        return rec
    except (ValueError, TypeError, UnicodeError, OSError, KeyError) as e:
        raise SliceBSessionError("receipt unavailable or malformed") from e


@contextmanager
def _receipt_update_lock(path: Path) -> Iterator[None]:
    """Hold a stable sibling lockfile exclusively until the update transaction ends."""
    lock_path = path.with_name("receipt.lock")
    descriptor = os.open(
        lock_path,
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
        ):
            raise SliceBSessionError("unsafe receipt update lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def update_session_receipt(path: Path, receipt: SliceBReceipt) -> None:
    """Serialize validation through replacement to prevent stale concurrent updates.

    Receipt identity is immutable; all four validated states are accepted as
    update targets, and Writer identity may bind once only on RUNNING. Once
    bound, both Writer fields are immutable.
    The file and directory are fsynced. If writing, flushing, fsync, or replace
    fails, only this call's successfully created temp file is removed; cleanup
    errors are attached to, rather than substituted for, the original error.
    """
    with _receipt_update_lock(path):
        _update_session_receipt_locked(path, receipt)


def _update_session_receipt_locked(path: Path, receipt: SliceBReceipt) -> None:
    """Update a receipt while its sibling flock is held by the caller."""
    _validate_receipt(receipt)
    old = verify_session_receipt(path, receipt.key)
    immutable = (
        "key",
        "baseline",
        "bundle_sha256",
        "manifest_sha256",
        "transfer_policy_id",
        "runtime_sha256",
        "image_ref",
        "image_config_id",
    )
    if any(getattr(old, k) != getattr(receipt, k) for k in immutable):
        raise SliceBSessionError("immutable receipt identity changed")
    if old.writer_id is not None and (
        old.writer_id != receipt.writer_id or old.started_at != receipt.started_at
    ):
        raise SliceBSessionError("Writer identity cannot be rebound")
    if (
        old.writer_id is None
        and receipt.writer_id is not None
        and receipt.state != "RUNNING"
    ):
        raise SliceBSessionError("Writer identity cannot bind after running")
    tmp = path.with_name("receipt.tmp")
    fd = os.open(
        tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(_encode_receipt(receipt))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    except OSError as error:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError as cleanup_error:
            error.add_note(f"temporary receipt cleanup failed: {cleanup_error}")
        raise
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def import_guest_baseline(
    bundle: BundleArtifact,
    repo: Path,
    *,
    expected_manifest_sha256: str,
    expected_key: object,
    expected_runtime_sha256: str,
) -> GitBaseline:
    """Import an already verified Bundle into a new Guest repository without network access.

    Requires trusted expected key, Manifest, and runtime pins. Rejects an
    existing/overlapping destination and validates imported HEAD/tree. Local
    Git and filesystem side effects create the Guest repository; failures may
    leave a partial destination. SliceBGitRejected may propagate from Git checks.
    """
    verify_bundle_manifest(
        bundle,
        expected_key=expected_key,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_runtime_sha256=expected_runtime_sha256,
    )
    if repo.exists():
        raise SliceBSessionError("Guest repository must be newly initialized")
    if repo.resolve().is_relative_to(bundle.baseline.root):
        raise SliceBSessionError("Guest repository overlaps Host")
    repo.mkdir(parents=True)
    try:
        _git(repo, "init", "-q")
        _git(
            repo,
            "-c",
            "protocol.file.allow=always",
            "fetch",
            "--no-tags",
            str(bundle.bundle_path),
            bundle.baseline.branch_ref,
        )
        _git(repo, "update-ref", bundle.baseline.branch_ref, bundle.baseline.head_oid)
        _git(repo, "symbolic-ref", "HEAD", bundle.baseline.branch_ref)
        _git(repo, "read-tree", "--reset", "-u", "HEAD")
        observed = admit_clean_repo(repo)
        if (
            observed.head_oid != bundle.baseline.head_oid
            or observed.tree_oid != bundle.baseline.tree_oid
            or observed.branch_ref != bundle.baseline.branch_ref
            or observed.worktree_sha256 != bundle.baseline.worktree_sha256
        ):
            raise SliceBSessionError("Guest imported baseline mismatch")
        return observed
    except (SliceBGitRejected, OSError) as e:
        raise SliceBSessionError("Guest baseline import/readback failed") from e


def verify_guest_authority(
    guest_control_manifest: Path,
    receipt: SliceBReceipt,
    guest_baseline: GitBaseline,
    image_config_id: str,
    *,
    local_image_inspect: Mapping[str, object] | None = None,
) -> VerifiedGuestAuthority:
    """Bind receipt, Guest baseline, copied Manifest, and exact local Writer image evidence.

    Rejects mismatched identity or image metadata with SliceBSessionError and
    returns authority data only. Malformed JSON becomes SliceBSessionError;
    filesystem read errors may propagate. It does not launch a Writer or freeze
    any input file.
    """
    _validate_receipt(receipt)
    if image_config_id != receipt.image_config_id:
        raise SliceBSessionError("image config identity mismatch")
    # Never issue Writer Baseline Authority based only on an image ID string.
    # This inspect must come from the trusted Guest's exact digest-ref lookup.
    if local_image_inspect is None:
        raise SliceBSessionError("digest-qualified local image evidence required")
    repo_digests = local_image_inspect.get("RepoDigests")
    image_config = local_image_inspect.get("Config")
    if (
        not isinstance(repo_digests, list)
        or any(not isinstance(ref, str) for ref in repo_digests)
        or not isinstance(image_config, Mapping)
    ):
        raise SliceBSessionError("invalid local image evidence")
    if (
        local_image_inspect.get("Id") != receipt.image_config_id
        or receipt.image_ref not in repo_digests
        or image_config.get("Entrypoint") != ["/opt/oc2/slice-b/entrypoint"]
        or image_config.get("Cmd") != ["run"]
    ):
        raise SliceBSessionError(
            "local digest-qualified image does not match Host Receipt"
        )
    raw = guest_control_manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt.manifest_sha256:
        raise SliceBSessionError("Guest private Manifest digest mismatch")
    manifest = SliceBBundleManifestV1(
        "dotfiles-ai/oc2-slice-b-bundle/v1",
        receipt.key,
        receipt.baseline,
        receipt.bundle_sha256,
        0,
        "oc2-slice-b-clean-git-bundle-v1",
        receipt.runtime_sha256,
    )
    try:
        j = json.loads(raw)
        if (
            j["key"] != _key_dict(receipt.key)
            or j["baseline"]["head_oid"] != receipt.baseline.head_oid
            or j["baseline"]["branch_ref"] != receipt.baseline.branch_ref
            or j["bundle_sha256"] != receipt.bundle_sha256
            or j["runtime_sha256"] != receipt.runtime_sha256
            or j["transfer_policy_id"] != receipt.transfer_policy_id
        ):
            raise SliceBSessionError("Guest manifest identity mismatch")
        manifest = replace(manifest, bundle_size_bytes=j["bundle_size_bytes"])
        if raw != _manifest_bytes(manifest):
            raise SliceBSessionError("Guest manifest is not canonical")
    except (KeyError, ValueError, TypeError) as e:
        raise SliceBSessionError("invalid Guest manifest") from e
    if (
        guest_baseline.head_oid != receipt.baseline.head_oid
        or guest_baseline.tree_oid != receipt.baseline.tree_oid
        or guest_baseline.branch_ref != receipt.baseline.branch_ref
        or guest_baseline.worktree_sha256 != receipt.baseline.worktree_sha256
    ):
        raise SliceBSessionError("Guest Git is not expected baseline")
    return VerifiedGuestAuthority(
        receipt.key,
        manifest,
        receipt.manifest_sha256,
        receipt.image_ref,
        receipt.image_config_id,
    )


def build_start_message(authority: VerifiedGuestAuthority) -> SliceBStartMessage:
    """Build the Supervisor startup frame from previously verified Guest authority."""
    key = _key_dict(authority.key)
    m = authority.manifest
    if m.key != authority.key or not _SHA256.fullmatch(authority.manifest_sha256):
        raise SliceBSessionError("untrusted authority")
    if not _REF.fullmatch(m.baseline.branch_ref):
        raise SliceBSessionError("invalid branch authority")
    return SliceBStartMessage(
        key["session_generation"],
        m.baseline.head_oid,
        m.baseline.branch_ref,
        authority.manifest_sha256,
    )
