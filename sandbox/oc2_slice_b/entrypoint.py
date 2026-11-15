#!/usr/bin/env python3
"""Fixed Slice B image PID1: validated Host Baseline → TUI → offline fixture.

The Supervisor-controlled fixture boundary is deliberately fail-closed until
Task 5 installs and verifies the framed attach transport. This file alone does
not authorize TUI/Sandbox/Writer execution.
"""

from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time

_WORKSPACE = Path("/workspace")
_TUI = "/opt/oc2/bin/opencode"
_TOKEN = "OC2_SLICE_B_START"
_REF = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]{0,180}\Z")
_OID = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


@dataclass(frozen=True)
class SliceBStartMessage:
    session_generation: str
    head_oid: str
    branch_ref: str
    manifest_sha256: str


class SliceBEntryRejected(RuntimeError):
    pass


def parse_start_line(line: str) -> SliceBStartMessage:
    try:
        wire = line.encode("ascii", "strict")
    except UnicodeError as e:
        raise SliceBEntryRejected("invalid startup encoding") from e
    if (
        len(wire) > 512
        or not wire.endswith(b"\n")
        or wire.count(b"\n") != 1
        or b"\r" in wire
        or b"\x00" in wire
    ):
        raise SliceBEntryRejected("invalid startup framing")
    parts = line[:-1].split(" ")
    if len(parts) != 5 or parts[0] != _TOKEN:
        raise SliceBEntryRejected("invalid startup token count")
    _, gen, oid, ref, digest = parts
    if not (
        _UUID4.fullmatch(gen)
        and _OID.fullmatch(oid)
        and _REF.fullmatch(ref)
        and _SHA.fullmatch(digest)
    ):
        raise SliceBEntryRejected("invalid startup identity")
    if ".." in ref or "//" in ref or ref.endswith(".lock"):
        raise SliceBEntryRejected("invalid startup branch")
    return SliceBStartMessage(gen, oid, ref, digest)


def _read_start_line(deadline_secs: float = 30.0) -> str:
    end = time.monotonic() + deadline_secs
    buf = bytearray()
    while time.monotonic() < end and len(buf) <= 512:
        ready, _, _ = select.select(
            [sys.stdin.buffer], [], [], max(0, end - time.monotonic())
        )
        if not ready:
            break
        x = os.read(sys.stdin.fileno(), 1)
        if not x:
            break
        buf.extend(x)
        if x == b"\n":
            break
    if not buf.endswith(b"\n") or len(buf) > 512:
        raise SliceBEntryRejected("missing/expired startup barrier")
    return buf.decode("ascii", "strict")


def _check_guest_baseline(
    expected: SliceBStartMessage, repo: Path = _WORKSPACE
) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }

    def git(*args):
        p = subprocess.run(
            ["git", *args],
            cwd=repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if p.returncode or len(p.stdout) > 256:
            raise SliceBEntryRejected("Guest baseline unavailable")
        return p.stdout.strip().decode("ascii")

    if (
        git("rev-parse", "--verify", "HEAD") != expected.head_oid
        or git("symbolic-ref", "HEAD") != expected.branch_ref
    ):
        raise SliceBEntryRejected("Guest HEAD/branch differs from Supervisor baseline")


def _run_tui() -> int:
    # No credentials, no provider bootstrap, no untrusted repo entrypoint.
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    with tempfile.TemporaryDirectory(prefix="oc2-home-") as home:
        env["HOME"] = home
        result = subprocess.run([_TUI, "--standalone"], cwd=_WORKSPACE, env=env)
        return result.returncode


def _supervisor_fixture_boundary() -> None:
    """Task 5 must provide a trusted framed channel before enabling fixture.

    No untrusted TUI bytes or Writer self-reported result may self-authorize
    the Supervisor's snapshot. Until wired, reject rather than skipping it.
    """
    raise SliceBEntryRejected("trusted Supervisor fixture boundary unavailable")


def run_entrypoint(start_line: str) -> int:
    try:
        data = parse_start_line(start_line)
        _check_guest_baseline(data)
        if _run_tui() != 0:
            return 23
        _check_guest_baseline(data)
        _supervisor_fixture_boundary()
        import offline_fixture

        offline_fixture.run_offline_fixture(_WORKSPACE, data.head_oid, data.branch_ref)
        return 0
    except (SliceBEntryRejected, OSError, ValueError, subprocess.SubprocessError):
        return 22
    except Exception:
        return 24


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["run"]:
        return 20
    try:
        start = _read_start_line(30)
    except (SliceBEntryRejected, UnicodeError, OSError):
        return 21
    return run_entrypoint(start)


if __name__ == "__main__":
    raise SystemExit(main())
