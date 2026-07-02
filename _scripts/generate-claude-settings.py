"""Generate/update Claude settings files (.claude.json and claude/settings.json) from apm.yml.

This script filters out SSE/HTTP transport servers and only includes stdio servers
in the mcpServers configuration to comply with Claude Desktop's validation schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
APM_YML = REPO_ROOT / "apm.yml"
CLAUDE_JSON = REPO_ROOT / ".claude.json"
SETTINGS_JSON = REPO_ROOT / "claude" / "settings.json"


def build_mcp_servers(apm: dict[str, Any]) -> dict[str, Any]:
    mcp_entries = (apm.get("dependencies") or {}).get("mcp") or []
    mcp_servers: dict[str, Any] = {}

    for entry in mcp_entries:
        if not entry.get("enabled", True):
            continue
        transport = entry.get("transport", "stdio")
        # Filter out remote SSE / HTTP transport servers as Claude Desktop does not support them natively
        if transport in ("sse", "http", "streamable-http"):
            continue

        name = str(entry["name"])
        command = entry.get("command")
        if not command:
            print(f"[warning] Skipping MCP server '{name}': command is missing or empty.")
            continue

        server_cfg: dict[str, Any] = {
            "type": "stdio",
            "command": str(command),
            "args": [str(arg) for arg in (entry.get("args") or [])],
        }
        if entry.get("env"):
            server_cfg["env"] = {k: str(v) for k, v in entry["env"].items()}

        mcp_servers[name] = server_cfg

    return mcp_servers


def update_json_file(file_path: Path, mcp_servers: dict[str, Any]) -> None:
    if not file_path.exists():
        data = {"mcpServers": {}}
    else:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warning] Failed to parse existing {file_path.name}: {e}")
            data = {"mcpServers": {}}

    data["mcpServers"] = mcp_servers

    try:
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[ok] Updated: {file_path}")
    except OSError as e:
        print(f"[error] Failed to write {file_path}: {e}")
        sys.exit(1)


def main() -> None:
    if not APM_YML.exists():
        print(f"[error] apm.yml not found: {APM_YML}")
        sys.exit(1)

    try:
        apm = yaml.safe_load(APM_YML.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as e:
        print(f"[error] Failed to parse apm.yml: {e}")
        sys.exit(1)

    mcp_servers = build_mcp_servers(apm)

    update_json_file(CLAUDE_JSON, mcp_servers)
    update_json_file(SETTINGS_JSON, mcp_servers)


if __name__ == "__main__":
    main()
