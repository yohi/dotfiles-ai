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

import yaml

REPO = Path(__file__).resolve().parents[2]
REQUIRED_APM = (0, 37, 0)

# APM 0.37 reads virtual subfolders relative to the repository root.
# Keep source apm.yml immutable; adjust only the Host V2 stage manifest.
HOST_V2_APM_PATH_REWRITES = {
    "greptileai/skills//check-pr": "greptileai/skills/skills/check-pr",
    "greptileai/skills//greploop": "greptileai/skills/skills/greploop",
}
HOST_V2_APM_EXCLUDED = {
    "anthropics/claude-code//plugins/code-review":
        "Claude Code plugin path is absent upstream; not a Host V2 skill",
}



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


def prepare_apm_manifest() -> tuple[dict, str]:
    """Project only APM-owned fields out of the anchor-bearing source SSOT."""
    source = REPO / "apm.yml"
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        stop("APM SSOT must be a regular file no larger than 2 MiB")
    try:
        parsed = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        stop(f"cannot parse source APM SSOT: {exc}")
    if not isinstance(parsed, dict) or not isinstance(parsed.get("dependencies"), dict):
        stop("APM SSOT lacks dependencies mapping")
    dependencies = parsed["dependencies"]
    packages, servers = dependencies.get("apm"), dependencies.get("mcp")
    if not isinstance(packages, list) or not isinstance(servers, list):
        stop("APM SSOT must contain dependencies.apm and dependencies.mcp lists")
    if not packages and not servers:
        stop("APM SSOT has no dependencies to synchronize")
    if any(not isinstance(item, (str, dict)) for item in [*packages, *servers]):
        stop("APM SSOT dependencies contain an unsupported entry")
    if not isinstance(parsed.get("name"), str) or not parsed["name"]:
        stop("APM SSOT name is missing")
    # Repair the two confirmed Greptile monorepo paths for APM 0.37. Exclude
    # the confirmed non-existent Claude Code-only plugin reference. Do not
    # silently filter any other dependency; preserve remaining entries exactly.
    remapped_packages = []
    for dependency in packages:
        if isinstance(dependency, str) and dependency in HOST_V2_APM_EXCLUDED:
            print(f"APM_HOST_V2_EXCLUDE: {dependency} "
                  f"({HOST_V2_APM_EXCLUDED[dependency]})", file=sys.stderr)
            continue
        if isinstance(dependency, str) and dependency in HOST_V2_APM_PATH_REWRITES:
            corrected = HOST_V2_APM_PATH_REWRITES[dependency]
            if corrected in packages or corrected in remapped_packages:
                stop(f"ambiguous duplicate Host V2 dependency: {corrected}")
            print(f"APM_HOST_V2_REWRITE: {dependency} -> {corrected}",
                  file=sys.stderr)
            remapped_packages.append(corrected)
        else:
            remapped_packages.append(dependency)
    if not remapped_packages and not servers:
        stop("Host V2 manifest would have no dependencies")
    manifest = {
        "name": parsed["name"],
        "version": str(parsed.get("version", "1.0.0")),
        "targets": ["opencode"],
        "dependencies": {"apm": remapped_packages, "mcp": servers},
    }
    # APM 0.37 rejects all YAML anchors/aliases; even shared objects must be
    # rendered as literal mappings, independent of the source provider section.
    class NoAliasDumper(yaml.SafeDumper):
        def ignore_aliases(self, data: object) -> bool:
            return True

    rendered = yaml.dump(manifest, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
    return manifest, rendered


def stage_apm_source(stage: Path, rendered: str) -> None:
    (stage / "apm.yml").write_text(rendered, encoding="utf-8")
    # APM compiles local primitives from cwd/.apm, not from --root. Copy only
    # approved instruction sources; never follow symlinks or copy credentials.
    source = REPO / ".apm/instructions"
    if source.exists() or source.is_symlink():
        if not source.is_dir() or source.is_symlink():
            stop("unsafe source .apm/instructions")
        target = stage / ".apm/instructions"
        target.mkdir(parents=True)
        instructions = list(source.iterdir())
        if len(instructions) > 64:
            stop("too many local APM instruction files")
        for item in instructions:
            if (item.is_symlink() or not item.is_file()
                    or not item.name.endswith(".instructions.md")
                    or item.stat().st_size > 256 * 1024):
                stop("unsafe local APM instruction primitive")
            shutil.copyfile(item, target / item.name)


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


def refresh_codegraph_mcp(home: Path) -> None:
    """Refresh only CodeGraph's Host V2 command, retaining MCP enablement."""
    manifest, _ = prepare_apm_manifest()
    matches = [item for item in manifest["dependencies"]["mcp"]
               if isinstance(item, dict) and item.get("name") == "codegraph"]
    if (len(matches) != 1 or matches[0].get("command") != "codegraph"
            or matches[0].get("args") != ["serve", "--mcp"]
            or "cwd" in matches[0]):
        stop("CodeGraph SSOT must use the official direct 'codegraph serve --mcp' entrypoint")
    private = home / ".config/opencode-v2/opencode"
    if not private.is_dir() or private.is_symlink():
        stop("Host V2 private configuration directory is unsafe")
    config_path = private / "opencode.json"
    state_path = private / "apm-host-sync-state.json"
    config = read_object(config_path)
    state = read_object(state_path)
    mcp = config.get("mcp")
    if not isinstance(mcp, dict) or not isinstance(mcp.get("servers"), dict):
        stop("Host V2 has no mcp.servers")
    servers = mcp["servers"]
    if state.get("source") != "apm.yml" or json_hash(servers) != state.get("mcp_sha256"):
        stop("APM-managed MCP state changed; refusing overwrite")
    snapshot_text = state.get("snapshot")
    root = home / ".local/share/opencode-v2/apm-host-snapshots"
    if not isinstance(snapshot_text, str) or not snapshot_text:
        stop("APM snapshot identity is missing")
    snapshot = Path(snapshot_text)
    if (not snapshot.is_absolute() or snapshot.is_symlink()
            or snapshot.parent != root or not snapshot.name.startswith("snapshot-")
            or not snapshot.is_dir()):
        stop("APM snapshot is missing or outside the Host V2 private area")
    staged = read_object(snapshot / "opencode.json")
    staged_mcp = staged.get("mcp")
    if (not isinstance(staged_mcp, dict)
            or not isinstance(staged_mcp.get("servers"), dict)
            or set(staged_mcp["servers"]) != set(servers)):
        stop("APM snapshot MCP ownership mismatch")
    existing = servers.get("codegraph")
    if not isinstance(existing, dict) or existing.get("type") != "local":
        stop("CodeGraph is not an APM-managed local MCP")
    command = existing.get("command")
    args = existing.get("args")
    if isinstance(command, list):
        if (len(command) != 3 or command[1:] != ["serve", "--mcp"]
                or not isinstance(command[0], str)):
            stop("CodeGraph MCP command has unexpected structure")
        executable = command[0]
    elif isinstance(command, str) and args == ["serve", "--mcp"]:
        executable = command
    else:
        stop("CodeGraph MCP command has unexpected structure")
    legacy = (executable in ("_scripts/codegraph-bootstrap.sh",
                             "./_scripts/codegraph-bootstrap.sh")
              or executable.endswith("/_scripts/codegraph-bootstrap.sh"))
    if not legacy and executable != "codegraph":
        stop("CodeGraph MCP is not on the known bootstrap or official entrypoint")
    # Keep every other CodeGraph attribute (including disabled/codemode/env)
    # and every other MCP entry intact. Convert into native V2 command list.
    updated = {k: v for k, v in existing.items() if k not in ("command", "args", "cwd")}
    updated["command"] = ["codegraph", "serve", "--mcp"]
    if updated == existing:
        print("NO_CHANGE: CodeGraph already uses codegraph serve --mcp")
        return
    newer = dict(servers)
    newer["codegraph"] = updated
    # Check for concurrent edits before replacing either owned state file.
    if read_object(config_path) != config or read_object(state_path) != state:
        stop("Host V2 configuration changed during CodeGraph update")
    config["mcp"] = {**mcp, "servers": newer}
    new_state = {**state, "mcp_sha256": json_hash(newer)}
    # The files are individually atomic; a failure between the two writes
    # leaves a mismatched receipt and blocks later APM-managed changes.
    for target, data in ((config_path, config), (state_path, new_state)):
        fd, tmp = tempfile.mkstemp(prefix=".codegraph-sync-", dir=private)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        finally:
            if os.path.lexists(tmp):
                os.unlink(tmp)
    print("UPDATED: Host V2 CodeGraph now uses codegraph serve --mcp")
    print("All MCP enablement flags preserved; no index initialization or network calls.")


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
    # Validate the source before writing any stage files or invoking APM.
    manifest, rendered = prepare_apm_manifest()
    snapshots = home / ".local/share/opencode-v2/apm-host-snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=snapshots))
    promoted = False
    try:
        stage_apm_source(stage, rendered)
        (stage / ".opencode").mkdir()
        (stage / "opencode.json").write_text('{"mcp":{"servers":{}}}\n', encoding="utf-8")
        for args in (["install", "--root", str(stage), "--target", "opencode"],
                     ["compile", "--root", str(stage), "--target", "opencode"]):
            # --root redirects writes only; it cannot redirect manifest input.
            subprocess.run([apm, *args], cwd=stage, check=True)
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
            # Preserve the Owner-selected state of previously deployed MCPs.
            # APM owns executable/transport/args; resync never resets choices.
            previous = old_servers.get(name)
            if previous is not None and not isinstance(previous, dict):
                stop(f"invalid previously deployed MCP server: {name}")
            disabled = previous.get("disabled", True) if previous is not None else True
            if not isinstance(disabled, bool):
                stop(f"invalid MCP disabled state: {name}")
            # Source documents a strict hold on the shared Cloudflare Portal.
            if name == "cf-mcp-portal":
                disabled = True
            servers[name] = {**settings, "disabled": disabled}
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
    group.add_argument("--refresh-codegraph", action="store_true",
                       help="repair only CodeGraph MCP entry from SSOT without reinstalling APM")
    args = parser.parse_args()
    home = Path(os.environ.get("HOME", ""))
    if not home.is_absolute() or not home.is_dir():
        stop("HOME must be an existing absolute directory")
    if not (REPO / "apm.yml").is_file():
        stop("run from the dotfiles-ai checkout")
    if args.refresh_codegraph:
        refresh_codegraph_mcp(home)
        return 0
    apm = os.environ.get("HOST_V2_APM_BIN", "apm")
    version = apm_version(apm)
    print(f"APM {'.'.join(map(str, version))}; source={REPO / 'apm.yml'}; target=opencode")
    if args.check:
        manifest, rendered = prepare_apm_manifest()
        print(f"CHECK_ONLY: APM-only manifest valid; "
              f"{len(manifest['dependencies']['apm'])} packages, "
              f"{len(manifest['dependencies']['mcp'])} MCP entries; "
              f"normalized SHA-256={hashlib.sha256(rendered.encode()).hexdigest()}")
        print("No files changed; this does not resolve or execute dependencies.")
        return 0
    apply(apm, home)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"APM_HOST_V2_STOP: {exc}", file=sys.stderr)
        sys.exit(1)
