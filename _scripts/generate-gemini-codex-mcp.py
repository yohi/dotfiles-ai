"""Generate Gemini and Codex MCP server sections from apm.yml (SSOT).

This script updates the tracked configuration files so they stay in sync with
apm.yml without manually editing each client config.
"""

from __future__ import annotations

import json
import re
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
APM_YML = REPO_ROOT / "apm.yml"
GEMINI_PATH = REPO_ROOT / "gemini" / "settings.json"
CODEX_PATH = REPO_ROOT / "codex" / "config.toml"


def _convert_env_syntax(value: str) -> str:
    """Convert apm.yml ${env:VAR} syntax to generic ${VAR} syntax."""
    return re.sub(r"\$\{(env:([^}]+))\}", r"${\2}", value)


def _convert_value(value: Any) -> Any:
    if isinstance(value, str):
        return _convert_env_syntax(value)
    if isinstance(value, list):
        return [_convert_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert_value(v) for k, v in value.items()}
    return value


def _mcp_entries(apm: dict[str, Any]) -> list[dict[str, Any]]:
    entries = (apm.get("dependencies") or {}).get("mcp") or []
    return [e for e in entries if e.get("enabled", True)]


def _build_mcp_server(entry: dict[str, Any]) -> dict[str, Any]:
    transport = entry.get("transport", "stdio")
    if transport in ("sse", "http", "streamable-http"):
        server: dict[str, Any] = {
            "url": _convert_value(entry["url"]),
            "type": "sse",
        }
        if "headers" in entry:
            server["headers"] = _convert_value(entry["headers"])
    command = entry.get("command")
    if not command:
        print(
            f"[warning] Skipping MCP server '{entry.get('name', '?')}': command is missing for stdio transport."
        )
        raise KeyError("command")

    server = {
        "command": _convert_value(command),
        "args": _convert_value(entry.get("args") or []),
        "type": "stdio",
    }
    if "env" in entry:
        server["env"] = _convert_value(entry["env"])
    return server



def _toml_escape(value: str) -> str:
    """Return a TOML double-quoted basic string for simple values."""
    return json.dumps(value, ensure_ascii=True)


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _toml_escape(key)


def _toml_dump_table(key_path: list[str], data: dict[str, Any], lines: list[str]) -> None:
    table_header = ".".join(_toml_key(k) for k in key_path)
    lines.append(f"[{table_header}]")
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        if isinstance(value, list):
            escaped = ", ".join(_toml_escape(str(v)) for v in value)
            lines.append(f"{key} = [{escaped}]")
        elif isinstance(value, str):
            lines.append(f"{key} = {_toml_escape(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")
    for key, value in data.items():
        if isinstance(value, dict):
            _toml_dump_table(key_path + [key], value, lines)
            lines.append("")


def _dump_mcp_servers(mcp_servers: dict[str, Any], lines: list[str]) -> None:
    if mcp_servers:
        lines.append("")
        lines.append("[mcp_servers]")
        lines.append("")
        for server_name, server_cfg in mcp_servers.items():
            _toml_dump_table(["mcp_servers", server_name], server_cfg, lines)
            lines.append("")


def _dump_codex_config(data: dict[str, Any], trailing_comments: list[str]) -> str:
    lines: list[str] = []
    mcp_servers = data.get("mcp_servers", {})
    for key, value in data.items():
        if key == "mcp_servers":
            _dump_mcp_servers(mcp_servers, lines)
            continue
        if isinstance(value, dict):
            lines.append("")
            _toml_dump_table([key], value, lines)
            lines.append("")
        elif isinstance(value, list):
            escaped = ", ".join(_toml_escape(str(v)) for v in value)
            lines.append(f"{key} = [{escaped}]")
        elif isinstance(value, str):
            lines.append(f"{key} = {_toml_escape(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")

    if trailing_comments:
        lines.extend(trailing_comments)

    return "\n".join(lines).rstrip() + "\n"



def _extract_trailing_comments(text: str) -> list[str]:
    lines = text.splitlines()
    comments: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            comments.insert(0, line)
            continue
        if stripped.startswith("#"):
            comments.insert(0, line)
        else:
            break
    return comments


def update_gemini(apm: dict[str, Any]) -> None:
    entries = _mcp_entries(apm)
    mcp_servers = {str(e["name"]): _build_mcp_server(e) for e in entries}

    data: dict[str, Any]
    if GEMINI_PATH.exists():
        with open(GEMINI_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["mcpServers"] = mcp_servers

    with open(GEMINI_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")
    print(f"[ok] Updated: {GEMINI_PATH}")


def update_codex(apm: dict[str, Any]) -> None:
    entries = _mcp_entries(apm)
    mcp_servers = {str(e["name"]): _build_mcp_server(e) for e in entries}

    original_text = ""
    if CODEX_PATH.exists():
        with open(CODEX_PATH, "r", encoding="utf-8") as f:
            original_text = f.read()
    trailing_comments = _extract_trailing_comments(original_text)

    data: dict[str, Any]
    if CODEX_PATH.exists():
        data = tomllib.loads(original_text)
    else:
        data = {}

    data["mcp_servers"] = mcp_servers

    with open(CODEX_PATH, "w", encoding="utf-8") as f:
        f.write(_dump_codex_config(data, trailing_comments))
    print(f"[ok] Updated: {CODEX_PATH}")


def main() -> int:
    try:
        apm = yaml.safe_load(APM_YML.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"[error] Failed to read {APM_YML}: {exc}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"[error] Failed to parse {APM_YML}: {exc}", file=sys.stderr)
        return 1

    update_gemini(apm)
    update_codex(apm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
