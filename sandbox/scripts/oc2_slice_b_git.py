"""Slice B: restrictive read-only Host admission and bound Git Bundle transport.

This module intentionally rejects repository formats it cannot verify.  There is
no Host checkout, add, reset, index rewrite, hook, remote, or credential access.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
from typing import Literal

SCHEMA: Literal["dotfiles-ai/oc2-slice-b-bundle/v1"] = "dotfiles-ai/oc2-slice-b-bundle/v1"
POLICY: Literal["oc2-slice-b-clean-git-bundle-v1"] = "oc2-slice-b-clean-git-bundle-v1"
MAX_OBJECTS = 4000
MAX_BLOB = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_BUNDLE = 64 * 1024 * 1024
_REF = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]{0,180}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SECRET = (
    re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9]{24,}\b"),
)
_ALLOWED_CONFIG = frozenset({
    "core.repositoryformatversion", "core.filemode", "core.bare",
    "core.logallrefupdates", "core.ignorecase", "user.name", "user.email",
})


class SliceBGitRejected(RuntimeError):
    """A bounded baseline could not be safely verified; do not transfer."""


@dataclasses.dataclass(frozen=True)
class GitBaseline:
    root: Path
    branch_ref: str
    head_oid: str
    tree_oid: str
    object_format: str
    index_sha256: str
    worktree_sha256: str


@dataclasses.dataclass(frozen=True)
class SliceBBundleManifestV1:
    schema: Literal["dotfiles-ai/oc2-slice-b-bundle/v1"]
    key: object
    baseline: GitBaseline
    bundle_sha256: str
    bundle_size_bytes: int
    transfer_policy_id: Literal["oc2-slice-b-clean-git-bundle-v1"]
    runtime_sha256: str


@dataclasses.dataclass(frozen=True)
class BundleArtifact:
    bundle_path: Path
    bundle_sha256: str
    manifest_path: Path
    manifest_sha256: str
    baseline: GitBaseline
    key: object
    transfer_policy_id: str
    runtime_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str, max_output: int = MAX_TOTAL) -> bytes:
    env = {
        "PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
        "GIT_ATTR_NOSYSTEM": "1", "GIT_PAGER": "cat", "GIT_CONFIG_COUNT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1", "GIT_PROTOCOL_FROM_USER": "0",
    }
    argv = ["git", "--no-optional-locks", "-C", str(root),
            "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "diff.external=", *args]
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SliceBGitRejected("bounded Git operation unavailable") from e
    if p.returncode or len(p.stdout) > max_output:
        raise SliceBGitRejected("Git operation failed or exceeded bound")
    return p.stdout


def _checked_index(raw: bytes, oid_bytes: int) -> None:
    if len(raw) < 12 + oid_bytes or raw[:4] != b"DIRC":
        raise SliceBGitRejected("invalid Index")
    version, count = struct.unpack(">II", raw[4:12])
    if version not in (2, 3) or count > 100_000:
        raise SliceBGitRejected("unsupported Index version/size")
    if hashlib.new("sha1" if oid_bytes == 20 else "sha256", raw[:-oid_bytes]).digest() != raw[-oid_bytes:]:
        raise SliceBGitRejected("Index checksum mismatch")
    i = 12
    end = len(raw) - oid_bytes
    for _ in range(count):
        start = i
        min_len = 40 + oid_bytes + 2
        if i + min_len > end:
            raise SliceBGitRejected("truncated Index entry")
        flags = struct.unpack(">H", raw[i + 40 + oid_bytes:i + 42 + oid_bytes])[0]
        if flags & 0x3000:  # stage != 0
            raise SliceBGitRejected("unmerged Index entry")
        i += min_len
        if flags & 0x4000:
            if version != 3 or i + 2 > end:
                raise SliceBGitRejected("unsupported extended Index entry")
            ext = struct.unpack(">H", raw[i:i + 2])[0]
            if ext != 0:  # intent-to-add, skip-worktree, unknown
                raise SliceBGitRejected("Index extended flags prohibited")
            i += 2
        term = raw.find(b"\x00", i, end)
        if term < i:
            raise SliceBGitRejected("missing Index path terminator")
        path = raw[i:term]
        if not path or b"\n" in path or b"\r" in path or b"\t" in path:
            raise SliceBGitRejected("unsupported Index pathname")
        i = (term + 1 + 7 - start) // 8 * 8 + start
        if i > end:
            raise SliceBGitRejected("malformed Index padding")
    while i < end:
        if i + 8 > end:
            raise SliceBGitRejected("truncated Index extension")
        name = raw[i:i+4]
        size = struct.unpack(">I", raw[i+4:i+8])[0]
        i += 8 + size
        if i > end or name != b"TREE":
            raise SliceBGitRejected("unknown Index extension")


def _root_metadata(root: Path) -> tuple[Path, int]:
    resolved = root.resolve(strict=True)
    gitdir = resolved / ".git"
    if not gitdir.is_dir() or gitdir.is_symlink():
        raise SliceBGitRejected("only ordinary non-linked Git directory is supported")
    if any((gitdir / p).exists() for p in ("shallow", "objects/info/alternates", "worktrees", "modules")):
        raise SliceBGitRejected("unsupported Git object/worktree topology")
    cfg = _git(resolved, "config", "--local", "--no-includes", "--name-only", "--list", "-z")
    keys = [x.decode("ascii") for x in cfg.split(b"\x00") if x]
    if any(x not in _ALLOWED_CONFIG for x in keys):
        raise SliceBGitRejected("unsafe or unsupported local Git config")
    fmt = _git(resolved, "rev-parse", "--show-object-format").strip().decode("ascii")
    if fmt not in ("sha1", "sha256"):
        raise SliceBGitRejected("unsupported object format")
    return resolved, 20 if fmt == "sha1" else 32


def _scan_history(root: Path, oid_len: int) -> None:
    objects = _git(root, "rev-list", "--objects", "HEAD").splitlines()
    if len(objects) > MAX_OBJECTS:
        raise SliceBGitRejected("reachable history too large")
    seen = set()
    total = 0
    for item in objects:
        ident, _, raw_path = item.partition(b" ")
        if len(ident) != oid_len * 2 or not re.fullmatch(rb"[a-f0-9]+", ident):
            raise SliceBGitRejected("invalid object identity")
        if raw_path:
            if (b"\n" in raw_path or b"\r" in raw_path or b"\t" in raw_path or
                    b".gitattributes" in raw_path or b".gitmodules" in raw_path or
                    b".env" in raw_path or b".ssh" in raw_path):
                raise SliceBGitRejected("unsafe historical pathname")
        if ident in seen:
            continue
        seen.add(ident)
        kind = _git(root, "cat-file", "-t", ident.decode()).strip()
        if kind not in (b"blob", b"tree", b"commit"):
            raise SliceBGitRejected("unsupported reachable object type")
        size_raw = _git(root, "cat-file", "-s", ident.decode()).strip()
        if not size_raw.isdigit():
            raise SliceBGitRejected("invalid object size")
        size = int(size_raw)
        if size > MAX_BLOB or total + size > MAX_TOTAL:
            raise SliceBGitRejected("oversized reachable history")
        total += size
        if kind == b"blob":
            data = _git(root, "cat-file", "blob", ident.decode(), max_output=MAX_BLOB)
            if any(p.search(data) for p in _SECRET):
                raise SliceBGitRejected("historical secret content rejected")


def _worktree_sha(root: Path) -> str:
    raw = _git(root, "ls-files", "-z")
    parts = raw.split(b"\x00")
    listed = []
    for name in parts:
        if not name:
            continue
        try:
            rel = name.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SliceBGitRejected("non UTF-8 path") from e
        if rel.startswith("/") or ".." in Path(rel).parts or "\n" in rel or "\r" in rel:
            raise SliceBGitRejected("unsafe worktree path")
        path = root / rel
        parent = root
        for component in Path(rel).parts[:-1]:
            parent = parent / component
            if parent.is_symlink() or not parent.is_dir():
                raise SliceBGitRejected("untrusted worktree directory")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BLOB:
            raise SliceBGitRejected("unsupported worktree entry")
        # No-follow protects the final component even if it changes after lstat.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info2 = os.fstat(fd)
            if not stat.S_ISREG(info2.st_mode) or info2.st_ino != info.st_ino or info2.st_dev != info.st_dev:
                raise SliceBGitRejected("worktree changed during inspection")
            data = os.read(fd, MAX_BLOB + 1)
        finally:
            os.close(fd)
        if len(data) != info.st_size or len(data) > MAX_BLOB:
            raise SliceBGitRejected("worktree content changed during inspection")
        if any(p.search(data) for p in _SECRET):
            raise SliceBGitRejected("secret detected in worktree")
        listed.append((rel, stat.S_IMODE(info.st_mode), _sha256(data)))
    return _sha256(json.dumps(listed, sort_keys=True, separators=(",", ":")).encode())


def admit_clean_repo(root: Path) -> GitBaseline:
    resolved, oid_bytes = _root_metadata(root)
    branch = _git(resolved, "symbolic-ref", "--quiet", "HEAD").strip().decode("ascii")
    if not _REF.fullmatch(branch) or ".." in branch or "//" in branch or branch.endswith(".lock"):
        raise SliceBGitRejected("unsupported branch ref")
    head = _git(resolved, "rev-parse", "--verify", "HEAD^{commit}").strip().decode("ascii")
    tree = _git(resolved, "rev-parse", "--verify", "HEAD^{tree}").strip().decode("ascii")
    if not (len(head) == len(tree) == 2 * oid_bytes and re.fullmatch("[a-f0-9]+", head)):
        raise SliceBGitRejected("invalid HEAD OID")
    if _git(resolved, "rev-parse", "--verify", branch).strip().decode() != head:
        raise SliceBGitRejected("branch/HEAD mismatch")
    index = resolved / ".git" / "index"
    if index.is_symlink() or not index.is_file():
        raise SliceBGitRejected("missing or linked Index")
    raw_index = index.read_bytes()
    _checked_index(raw_index, oid_bytes)
    if _git(resolved, "status", "--porcelain=v1", "--untracked-files=all", "-z"):
        raise SliceBGitRejected("dirty Index or worktree")
    _scan_history(resolved, oid_bytes)
    worktree_sha = _worktree_sha(resolved)
    if index.read_bytes() != raw_index:
        raise SliceBGitRejected("Host Index changed during admission")
    return GitBaseline(resolved, branch, head, tree, "sha1" if oid_bytes == 20 else "sha256", _sha256(raw_index), worktree_sha)


def recheck_host_baseline(baseline: GitBaseline) -> None:
    observed = admit_clean_repo(baseline.root)
    if observed != baseline:
        raise SliceBGitRejected("Host baseline changed")


def _key_dict(key: object) -> dict[str, str]:
    validate = getattr(key, "validate", None)
    if not callable(validate):
        raise SliceBGitRejected("invalid SessionKey")
    try:
        validate()
    except Exception as e:
        raise SliceBGitRejected("invalid SessionKey") from e
    return {name: getattr(key, name) for name in ("workspace_id", "sandbox_id", "session_generation")}


def _manifest_bytes(manifest: SliceBBundleManifestV1) -> bytes:
    b = dataclasses.asdict(manifest.baseline)
    b["root"] = str(b["root"])
    payload = {
        "schema": SCHEMA, "key": _key_dict(manifest.key), "baseline": b,
        "bundle_sha256": manifest.bundle_sha256,
        "bundle_size_bytes": manifest.bundle_size_bytes,
        "transfer_policy_id": POLICY, "runtime_sha256": manifest.runtime_sha256,
    }
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def build_verified_bundle(baseline: GitBaseline, output: Path, *, key: object, runtime_sha256: str) -> BundleArtifact:
    if not _SHA256.fullmatch(runtime_sha256):
        raise SliceBGitRejected("invalid Runtime SHA")
    _key_dict(key)
    recheck_host_baseline(baseline)
    path = output.resolve()
    if path.is_relative_to(baseline.root):
        raise SliceBGitRejected("Bundle output must be outside Host repository")
    if path.exists():
        raise SliceBGitRejected("Bundle output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git(baseline.root, "bundle", "create", str(path), baseline.branch_ref)
        if path.stat().st_size > MAX_BUNDLE:
            raise SliceBGitRejected("Bundle too large")
        _git(baseline.root, "bundle", "verify", str(path))
        items = _git(baseline.root, "bundle", "list-heads", str(path)).decode().splitlines()
        if items != [f"{baseline.head_oid} {baseline.branch_ref}"]:
            raise SliceBGitRejected("Bundle refs mismatch")
        recheck_host_baseline(baseline)
        raw = path.read_bytes()
        sha = _sha256(raw)
        manifest = SliceBBundleManifestV1(SCHEMA, key, baseline, sha, len(raw), POLICY, runtime_sha256)
        dest = path.with_name(path.name + ".manifest.json")
        if dest.exists():
            raise SliceBGitRejected("manifest already exists")
        data = _manifest_bytes(manifest)
        with dest.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        return BundleArtifact(path, sha, dest, _sha256(data), baseline, key, POLICY, runtime_sha256)
    except Exception:
        # This is an outside-repo artifact only, never a Host Index/WT mutation.
        if path.exists():
            path.unlink()
        raise


def verify_bundle_manifest(artifact: BundleArtifact, *, expected_key: object,
                           expected_manifest_sha256: str, expected_runtime_sha256: str) -> SliceBBundleManifestV1:
    if artifact.key != expected_key or not _SHA256.fullmatch(expected_runtime_sha256):
        raise SliceBGitRejected("untrusted Bundle identity")
    if artifact.transfer_policy_id != POLICY or artifact.runtime_sha256 != expected_runtime_sha256:
        raise SliceBGitRejected("transfer policy/Runtime mismatch")
    try:
        raw = artifact.manifest_path.read_bytes()
        bundle = artifact.bundle_path.read_bytes()
    except OSError as e:
        raise SliceBGitRejected("missing Bundle or Manifest") from e
    if not _SHA256.fullmatch(expected_manifest_sha256) or _sha256(raw) != expected_manifest_sha256 or _sha256(raw) != artifact.manifest_sha256:
        raise SliceBGitRejected("Manifest digest mismatch")
    if _sha256(bundle) != artifact.bundle_sha256 or len(bundle) > MAX_BUNDLE:
        raise SliceBGitRejected("Bundle digest mismatch")
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as e:
        raise SliceBGitRejected("invalid Manifest") from e
    if not isinstance(data, dict) or set(data) != {"schema", "key", "baseline", "bundle_sha256", "bundle_size_bytes", "transfer_policy_id", "runtime_sha256"}:
        raise SliceBGitRejected("unsupported Manifest schema")
    expected = SliceBBundleManifestV1(SCHEMA, artifact.key, artifact.baseline, artifact.bundle_sha256,
                                      len(bundle), POLICY, expected_runtime_sha256)
    if raw != _manifest_bytes(expected):
        raise SliceBGitRejected("noncanonical or inconsistent Manifest")
    return expected
