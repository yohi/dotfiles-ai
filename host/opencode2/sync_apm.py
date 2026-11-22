#!/usr/bin/env python3
"""Stage Microsoft APM output for Host OpenCode V2 without touching V1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[2]
REQUIRED_APM = (0, 37, 0)


def stop(message: str) -> None:
    raise RuntimeError(message)


def json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        stop(f"missing or unsafe regular JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        stop(f"expected JSON object: {path}")
    return value


def apm_version(command: str) -> tuple[int, int, int]:
    proc = subprocess.run([command, "--version"], text=True, capture_output=True, timeout=15, check=True)
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", proc.stdout + proc.stderr)
    if not match:
        stop("cannot parse apm --version")
    version = tuple(map(int, match.groups()))
    if version < REQUIRED_APM:
        stop("APM 0.37.0 or newer is required; upgrade it separately, not via this script")
    return version


def destination_ok(dest: Path, prior: dict | None, name: str) -> None:
    if not dest.exists() and not dest.is_symlink():
        return
    if prior is None or not dest.is_symlink():
        stop(f"unmanaged destination; refusing replacement: {dest}")
    old = Path(prior.get("snapshot", "")) / {
        "skills": ".agents/skills", "commands": ".opencode/commands",
        "AGENTS.md": "AGENTS.md",
    }[name]
    if os.readlink(dest) != str(old):
        stop(f"changed adapter; refusing replacement: {dest}")


def apply(apm: str, home: Path) -> None:
    private = home / ".config/opencode-v2/opencode"
    config_path = private / "opencode.json"
    state_path = private / "apm-host-sync-state.json"
    config = read_object(config_path)
    if not private.is_dir() or private.is_symlink():
        stop("V2 private configuration directory is unsafe")
    mcp = config.get("mcp", {})
    if not isinstance(mcp, dict) or not isinstance(mcp.get("servers", {}), dict):
        stop("V2 MCP configuration is not an mcp.servers mapping")
    old_servers = mcp.get("servers", {})
    prior = read_object(state_path) if state_path.exists() or state_path.is_symlink() else None
    if prior:
        if json_hash(old_servers) != prior.get("mcp_sha256"):
            stop("V2 MCP entries changed since last APM sync; refusing overwrite")
    elif old_servers:
        stop("unmanaged V2 MCP entries exist; refusing overwrite")
    for name in ("skills", "commands", "AGENTS.md"):
        destination_ok(private / name, prior, name)

    # APM's --root redirects project package, MCP and lockfile outputs to stage.
    # The seed forces native V2 mcp.servers layout rather than legacy V1 mcp.
    snapshots = home / ".local/share/opencode-v2/apm-host-snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=snapshots))
    promoted = False
    try:
        (stage / ".opencode").mkdir()
        (stage / "opencode.json").write_text('{"mcp":{"servers":{}}}\n', encoding="utf-8")
        for args in (["install", "--root", str(stage), "--target", "opencode"],
                     ["compile", "--root", str(stage), "--target", "opencode"]):
            subprocess.run([apm, *args], cwd=REPO, check=True)
        generated = read_object(stage / "opencode.json")
        source_mcp = generated.get("mcp")
        if not isinstance(source_mcp, dict) or not isinstance(source_mcp.get("servers"), dict):
            stop("APM did not produce native V2 mcp.servers")
        raw_servers = source_mcp["servers"]
        servers = {}
        for name, settings in raw_servers.items():
            if not isinstance(name, str) or not name or not isinstance(settings, dict):
                stop("invalid APM MCP server declaration")
            if settings.get("type") not in ("local", "remote"):
                stop(f"unsupported MCP type in APM output: {name}")
            servers[name] = {**settings, "disabled": True}
        # Existing user-defined V2 settings are retained; imported tools are
        # disabled until the human owner explicitly chooses which to activate.
        config["mcp"] = {**mcp, "servers": servers}
        asset_paths = {
            "skills": stage / ".agents/skills",
            "commands": stage / ".opencode/commands",
            "AGENTS.md": stage / "AGENTS.md",
        }
        present = {name: path for name, path in asset_paths.items()
                   if path.is_dir() and not path.is_symlink()
                   or path.is_file() and not path.is_symlink()}
        if not present and not servers:
            stop("APM produced no applicable Host V2 assets")
        for name in ("skills", "commands", "AGENTS.md"):
            if name not in present and (private / name).is_symlink():
                stop(f"previous APM adapter is missing from new output: {name}")
        snapshot = snapshots / f"snapshot-{uuid.uuid4().hex}"
        stage.rename(snapshot)
        promoted = True
        state = {"snapshot": str(snapshot), "mcp_sha256": json_hash(servers),
                 "apm_version": apm_version(apm), "source": "apm.yml"}
        # No partial generated files are exposed until the APM pipeline and
        # validation have succeeded. Adapter swaps and config are per-file atomic.
        for name in present:
            src_rel = {"skills": ".agents/skills", "commands": ".opencode/commands", "AGENTS.md": "AGENTS.md"}[name]
            dest = private / name
            link = private / f".apm-{name}-{uuid.uuid4().hex}"
            os.symlink(snapshot / src_rel, link)
            os.replace(link, dest)
        for target, data in ((config_path, config), (state_path, state)):
            fd, tmp = tempfile.mkstemp(prefix=".apm-sync-", dir=private)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, indent=2, ensure_ascii=False)
                    stream.write("\n")
                os.chmod(tmp, 0o600)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        print(f"APM Host V2 applied: {len(present)} adapters, {len(servers)} disabled MCP servers")
        print("Restart opencode2. Review MCP entries before enabling any server.")
    finally:
        if not promoted:
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="read-only compatibility check")
    group.add_argument("--apply", action="store_true", help="explicit APM staging and V2-only sync")
    args = parser.parse_args()
    home = Path(os.environ.get("HOME", ""))
    if not home.is_absolute() or not home.is_dir():
        stop("HOME must be an existing absolute directory")
    if not (REPO / "apm.yml").is_file():
        stop("run from the dotfiles-ai checkout")
    apm = os.environ.get("HOST_V2_APM_BIN", "apm")
    version = apm_version(apm)
    print(f"APM {'.'.join(map(str, version))}; source={REPO / 'apm.yml'}; target=opencode")
    if args.check:
        print("CHECK_ONLY: no files changed. --apply uses an isolated APM --root.")
        return 0
    apply(apm, home)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"APM_HOST_V2_STOP: {exc}", file=sys.stderr)
        sys.exit(1)
