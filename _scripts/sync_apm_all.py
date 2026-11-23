#!/usr/bin/env python3
"""Explicit one-command apm.yml sync for installed, enabled host environments.

No startup hook, git pull, CLI upgrade, credential import, or Sandbox mutation.
The entire plan is checked before applying; a failed step stops subsequent steps.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys

import yaml

REPO = Path(__file__).resolve().parents[1]
SUPPORTED_TARGETS = frozenset({"opencode", "codex", "claude", "gemini", "antigravity"})
GENERATED_FILES = (
    "opencode/opencode.jsonc", "opencode.json", "codex/config.toml",
    "gemini/settings.json", "apm.lock.yaml",
)


class SyncStopped(RuntimeError):
    """A prerequisite or one step failed; do not continue other environments."""


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]


def source_targets() -> set[str]:
    source = REPO / "apm.yml"
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        raise SyncStopped("missing or unsafe apm.yml (regular file <= 2 MiB required)")
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SyncStopped(f"cannot parse apm.yml: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), dict):
        raise SyncStopped("apm.yml lacks dependencies")
    deps = data["dependencies"]
    if not isinstance(deps.get("mcp"), list) or not isinstance(deps.get("apm"), list):
        raise SyncStopped("apm.yml lacks APM/MCP dependency lists")
    targets = data.get("targets")
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(t, str) or not t for t in targets)
            or len(set(targets)) != len(targets)):
        raise SyncStopped("apm.yml targets must be a unique, non-empty list")
    unsupported = set(targets) - SUPPORTED_TARGETS
    if unsupported:
        raise SyncStopped(f"unsupported target(s): {sorted(unsupported)}")
    return set(targets)


def paths(home: Path) -> dict[str, Path]:
    return {
        "host_v2": home / ".config/opencode-v2/opencode/opencode.json",
        "claude": home / ".claude",
        "gemini": home / ".gemini",
        "antigravity": home / ".gemini/antigravity-cli",
    }


def build_steps(targets: set[str], home: Path, apm: str = "apm") -> tuple[list[Step], dict[str, str]]:
    mk = lambda target: ("make", "--no-print-directory", target)
    py = lambda script, arg: (sys.executable, str(REPO / script), arg)
    steps: list[Step] = []
    skipped: dict[str, str] = {}
    active_standard = targets & {"opencode", "codex"}
    if active_standard:
        if "codex" in active_standard:
            steps.append(Step("codex: seed existing APM configuration", mk("sync-codex-apm-seed")))
        steps.extend((
            Step("APM: install declared standard targets", (apm, "install")),
            Step("APM: compile declared standard targets", (apm, "compile")),
            Step("Skills: native adapters", mk("setup-skill-adapters")),
            Step("Rules: refresh generated agent instructions", mk("sync-agents-rules")),
            Step("Commands: update linked agent commands", mk("link-agent-commands")),
        ))
        if "opencode" in active_standard:
            steps.extend((
                Step("OpenCode V1: link generated settings", mk("setup-opencode")),
                Step("OpenCode V1: refresh meta prompt", mk("inject-meta-prompt-opencode")),
            ))
        else:
            skipped["OpenCode V1"] = "not enabled in apm.yml targets"
        if "codex" in active_standard:
            steps.extend((
                Step("Codex: regenerate MCP from SSOT", mk("sync-codex-mcp")),
                Step("Codex: link generated configuration", mk("sync-codex")),
                Step("Codex: refresh meta prompt", mk("inject-meta-prompt-codex")),
            ))
        else:
            skipped["Codex"] = "not enabled in apm.yml targets"
    else:
        skipped["OpenCode V1 / Codex"] = "neither target enabled in apm.yml"

    state = paths(home)
    # Existing, configured Claude profiles are synchronized even though they
    # are managed through the separate APM user-scope target, not the root
    # targets list. Never install a new Claude profile implicitly.
    if state["claude"].is_dir() or (home / ".claude.json").is_file():
        steps.append(Step("Claude Code: APM user-scope MCP and settings", mk("setup-claude")))
    else:
        skipped["Claude Code"] = "no existing profile; not installed or activated"
    if "gemini" in targets:
        if state["gemini"].is_dir() or shutil.which("gemini"):
            steps.append(Step("Gemini CLI: regenerate MCP configuration", py("_scripts/generate-gemini-codex-mcp.py", "--gemini-only")))
        else:
            skipped["Gemini CLI"] = "target enabled but CLI/profile missing; not installed automatically"
    else:
        skipped["Gemini CLI"] = "not enabled in apm.yml targets"
    # An already-configured Antigravity profile is a distinct opt-in from
    # adding the root APM default target; respect its existing installation.
    if state["antigravity"].is_dir():
        steps.append(Step("Antigravity: APM target sync", mk("sync-antigravity")))
    else:
        skipped["Antigravity"] = "no existing profile; not installed or activated"

    if state["host_v2"].is_file() and not state["host_v2"].is_symlink():
        steps.extend((
            Step("Host V2: sync model and providers", py("host/opencode2/sync_models.py", "--apply")),
            Step("Host V2: sync APM/MCP/skills", py("host/opencode2/sync_apm.py", "--apply")),
        ))
    else:
        skipped["Host OpenCode V2"] = "not installed (or unsafe config); never installed automatically"
    skipped["OC2 Sandbox live runtime"] = "requires separate Owner approval; live Sandboxes never modified"
    return steps, skipped


def protect_tracked_generated() -> None:
    # Avoid overwriting unsaved edits to generated files; other dirty files,
    # including the SSOT itself, are allowed. Never fetch or reset git state.
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--", *GENERATED_FILES], cwd=REPO,
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise SyncStopped(f"cannot inspect tracked generated files: {proc.stderr.strip()}")
    if proc.stdout.strip():
        raise SyncStopped(f"generated files have unstaged edits: {proc.stdout.strip()}")
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", *GENERATED_FILES],
        cwd=REPO, text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0 or proc.stdout.strip():
        raise SyncStopped("generated files have staged edits, or staged-state check failed")


def preflight(targets: set[str], steps: list[Step], home: Path, apm: str) -> None:
    if not home.is_absolute() or not home.is_dir() or home.is_symlink():
        raise SyncStopped("HOME must be an existing, non-symlink absolute directory")
    if any(s.command[0] == "make" for s in steps) and not shutil.which("make"):
        raise SyncStopped("make is required")
    if any(s.command[0] == apm for s in steps) or any(s.name.startswith("Host V2: sync APM") for s in steps):
        if not shutil.which(apm) and not Path(apm).is_file():
            raise SyncStopped(f"APM executable missing: {apm}; no installation attempted")
    if ("opencode" in targets or "codex" in targets) and not (REPO / "Makefile").is_file():
        raise SyncStopped("repository Makefile missing")
    protect_tracked_generated()
    if any(s.name.startswith("Host V2:") for s in steps):
        for item in ("host/opencode2/sync_models.py", "host/opencode2/sync_apm.py"):
            if not (REPO / item).is_file():
                raise SyncStopped(f"Host V2 sync component missing: {item}")
        for item in ("sync_models.py", "sync_apm.py"):
            result = subprocess.run(
                [sys.executable, str(REPO / "host/opencode2" / item), "--check"],
                cwd=REPO, text=True, capture_output=True, check=False,
            )
            if result.returncode != 0:
                raise SyncStopped(f"Host V2 {item} --check rejected: {result.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true", help="read-only plan and compatibility checks")
    actions.add_argument("--apply", action="store_true", help="explicitly apply to enabled installed environments")
    args = parser.parse_args(argv)
    home = Path(os.environ.get("HOME", ""))
    apm = os.environ.get("HOST_V2_APM_BIN", "apm")
    try:
        targets = source_targets()
        steps, skipped = build_steps(targets, home, apm)
        print("SSOT: apm.yml; enabled targets:", ", ".join(sorted(targets)), flush=True)
        for name, why in skipped.items():
            print(f"SKIPPED [{name}]: {why}", flush=True)
        for step in steps:
            print(f"PLANNED [{step.name}]", flush=True)
        preflight(targets, steps, home, apm)
        if args.check:
            print(f"CHECK_PASS: {len(steps)} steps planned, no writes, no provider or MCP calls", flush=True)
            return 0
        for i, step in enumerate(steps):
            print(f"RUN [{i+1}/{len(steps)}] {step.name}", flush=True)
            proc = subprocess.run(step.command, cwd=REPO, check=False)
            if proc.returncode != 0:
                print(f"FAILED [{step.name}]: exit={proc.returncode}", file=sys.stderr, flush=True)
                print(f"PARTIAL: {i} completed; {len(steps)-i-1} NOT_RUN; no automatic rollback", file=sys.stderr, flush=True)
                return 1
            print(f"APPLIED [{step.name}]", flush=True)
        print(f"SYNC_COMPLETE: {len(steps)} steps succeeded; skipped targets listed above", flush=True)
        return 0
    except (OSError, SyncStopped, ValueError) as exc:
        print(f"SYNC_APM_ALL_STOP: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
