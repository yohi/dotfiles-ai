"""Generate opencode/opencode.jsonc from apm.yml (SSOT).

Usage:
    python _scripts/generate-opencode-jsonc.py [--dry-run] [--check]

Options:
    --dry-run   Print generated output without writing file
    --check     Exit 1 if generated output differs from existing file (CI use)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
APM_YML = REPO_ROOT / "apm.yml"
OUTPUT = REPO_ROOT / "opencode" / "opencode.jsonc"


# ---------------------------------------------------------------------------
# MCP format conversion: apm.yml dependencies.mcp -> OpenCode mcp object
# ---------------------------------------------------------------------------
def _convert_mcp_entry(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Convert a single apm.yml MCP entry to OpenCode mcp format."""
    name = str(entry["name"])
    transport = entry.get("transport", "stdio")
    enabled = entry.get("enabled", True)

    if transport in ("sse", "http", "streamable-http"):
        result: dict[str, Any] = {
            "type": "remote",
            "url": entry["url"],
            "enabled": enabled,
        }
        if "headers" in entry:
            # Convert ${env:VAR} -> {env:VAR}
            result["headers"] = {
                k: _normalize_env_syntax(v)
                for k, v in entry["headers"].items()
            }
    else:
        # stdio
        cmd_str = entry.get("command", "")
        args = entry.get("args", [])
        full_cmd = [cmd_str, *[str(a) for a in args]] if cmd_str else []
        result = {
            "type": "local",
            "enabled": enabled,
            "command": full_cmd,
        }
        if "env" in entry:
            result["environment"] = {
                k: _normalize_env_syntax(str(v))
                for k, v in entry["env"].items()
            }

    return name, result


def _normalize_env_syntax(value: str) -> str:
    """Normalize ${env:VAR} (apm.yml) -> {env:VAR} (OpenCode).
    If it already matches {env:VAR}, keep it as is.
    """
    if re.match(r"^{env:[^}]+}$", value):
        return value
    return re.sub(r"\$\{(env:[^}]+)\}", r"{\1}", value)


def _build_mcp_section(mcp_entries: list[dict[str, Any]]) -> dict[str, Any]:
    mcp: dict[str, Any] = {}
    for entry in mcp_entries:
        name, converted = _convert_mcp_entry(entry)
        mcp[name] = converted
    return mcp





# ---------------------------------------------------------------------------
# sakura provider: apm.yml uses simplified models dict, convert to full form
# ---------------------------------------------------------------------------
def _normalize_sakura(sakura: dict[str, Any]) -> dict[str, Any]:
    models_raw = sakura.get("models", {})
    models_out: dict[str, Any] = {}
    for key, val in models_raw.items():
        if isinstance(val, dict):
            models_out[key] = val
        else:
            models_out[key] = {"name": str(val)}
    return {
        "npm": sakura.get("npm", "@ai-sdk/openai-compatible"),
        "name": sakura.get("name", ""),
        "options": sakura.get("options", {}),
        "models": models_out,
    }


# ---------------------------------------------------------------------------
# Permission: convert apm.yml (unquoted keys) -> OpenCode (quoted keys)
# apm.yml stores bash sub-permissions as nested dict under "bash"
# ---------------------------------------------------------------------------
def _build_permission(perm: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in perm.items():
        if isinstance(v, dict):
            out[k] = _build_permission(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Build the full opencode config dict from apm.yml
# ---------------------------------------------------------------------------
def build_config(apm: dict[str, Any]) -> dict[str, Any]:
    cfg: dict[str, Any] = {}

    # --- Scalar fields ---
    cfg["$schema"] = "https://opencode.ai/config.json"
    cfg["default_agent"] = apm.get("default_agent", "sisyphus")
    cfg["shell"] = apm.get("shell", "bash")
    cfg["snapshot"] = apm.get("snapshot", True)

    # --- Plugin ([Plugin] anchor) ---
    cfg["plugin"] = apm.get("plugin", [])

    # --- disabled_providers ---
    if "disabled_providers" in apm:
        cfg["disabled_providers"] = apm["disabled_providers"]

    # --- Permission ---
    if "permission" in apm:
        cfg["permission"] = _build_permission(apm["permission"])

    # --- Compaction ---
    if "compaction" in apm:
        cfg["compaction"] = apm["compaction"]

    # --- Share ---
    if "share" in apm:
        cfg["share"] = apm["share"]

    # --- LSP ---
    if "lsp" in apm:
        cfg["lsp"] = apm["lsp"]

    # --- Instructions ---
    if "instructions" in apm:
        cfg["instructions"] = apm["instructions"]

    # --- Watcher ---
    if "watcher" in apm:
        cfg["watcher"] = apm["watcher"]

    # --- enabled_providers ---
    if "enabled_providers" in apm:
        cfg["enabled_providers"] = apm["enabled_providers"]

    # --- provider (extracted from apm.yml with sakura normalization) ---
    providers: dict[str, Any] = {}
    for name, prov in (apm.get("provider") or {}).items():
        if name == "sakura":
            providers[name] = _normalize_sakura(prov)
        else:
            providers[name] = prov

    if providers:
        cfg["provider"] = providers

    # --- experimental ---
    if "experimental" in apm:
        cfg["experimental"] = apm["experimental"]

    # --- MCP ([MCP] anchor) ---
    mcp_entries = (apm.get("dependencies") or {}).get("mcp") or []
    if mcp_entries:
        cfg["mcp"] = _build_mcp_section(mcp_entries)

    return cfg


# ---------------------------------------------------------------------------
# Serialise to JSONC with section headers
# ---------------------------------------------------------------------------
_SECTION_COMMENTS: dict[str, str] = {
    "plugin": "// [Plugin] - エコシステム設定\n  // [Plugin]",
    "permission": "// Permission - 権限とガードレール",
    "compaction": "// Compaction & Lifecycle",
    "lsp": "// LSP - 言語サーバー設定",
    "instructions": "// Instructions",
    "watcher": "// Watcher",
    "enabled_providers": "// Providers & Models",
    "experimental": "// Experimental",
    "mcp": "// [MCP] - サーバー設定\n  // [MCP]",
}

_SEP = "  // " + "-" * 74


def _serialise(cfg: dict[str, Any]) -> str:
    """Produce JSONC string from config dict."""
    lines: list[str] = []
    lines.append("// vim: ft=jsonc")
    lines.append("// AUTO-GENERATED by _scripts/generate-opencode-jsonc.py")
    lines.append("// Source: apm.yml (SSOT)")
    lines.append("// Regenerate: make sync-opencode")
    lines.append("// DO NOT EDIT DIRECTLY.")
    lines.append("")
    lines.append("{")

    items = list(cfg.items())
    for idx, (key, val) in enumerate(items):
        is_last = idx == len(items) - 1
        comma = "" if is_last else ","

        # Section comment
        if key in _SECTION_COMMENTS:
            lines.append("")
            lines.append(_SEP)
            for cline in _SECTION_COMMENTS[key].splitlines():
                lines.append(f"  {cline}")
            lines.append(_SEP)

        # Serialise value with 2-space indent
        raw = json.dumps({key: val}, ensure_ascii=False, indent=2)
        # raw is like '{\n  "key": ...\n}'
        inner = raw[2:-2]  # strip outer '{\n' and '\n}'
        # inner starts with '  "key": ...' already indented by json.dumps
        lines.append(f"{inner}{comma}")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    dry_run = "--dry-run" in sys.argv
    check_mode = "--check" in sys.argv

    if not APM_YML.exists():
        raise SystemExit(f"[error] apm.yml not found: {APM_YML}")
    apm = yaml.safe_load(APM_YML.read_text(encoding="utf-8"))
    cfg = build_config(apm)
    output = _serialise(cfg)

    if dry_run:
        print(output)
        return

    if check_mode:
        if not OUTPUT.exists():
            print("[check] FAIL: opencode.jsonc does not exist. Run: make sync-opencode")
            sys.exit(1)
        current = OUTPUT.read_text(encoding="utf-8")
        if current != output:
            print("[check] FAIL: opencode.jsonc is out of sync with apm.yml. Run: make sync-opencode")
            sys.exit(1)
        print("[check] OK: opencode.jsonc is up to date.")
        return

    OUTPUT.write_text(output, encoding="utf-8")
    print(f"[ok] Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
