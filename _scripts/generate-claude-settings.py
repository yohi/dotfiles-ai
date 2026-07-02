"""Generate/update Claude settings files (.claude.json and claude/settings.json) from apm.yml.

This script filters out SSE/HTTP transport servers and only includes stdio servers
in the mcpServers configuration to comply with Claude Desktop's validation schema.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import yaml


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


def update_claude_json(mcp_servers: dict[str, Any]) -> None:
    target_path = ".claude.json"
    data: dict[str, Any]
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warning] Failed to parse existing {target_path}: {e}")
        data = {"mcpServers": {}}

    data["mcpServers"] = mcp_servers

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"[ok] Updated: {target_path}")
    except OSError as e:
        print(f"[error] Failed to write {target_path}: {e}")
        sys.exit(1)


def update_settings_json(mcp_servers: dict[str, Any]) -> None:
    target_dir = "claude"
    target_path = "claude/settings.json"
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        print(f"[error] Failed to create directory {target_dir}: {e}")
        sys.exit(1)

    data: dict[str, Any]
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warning] Failed to parse existing {target_path}: {e}")
        data = {"mcpServers": {}}

    data["mcpServers"] = mcp_servers

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"[ok] Updated: {target_path}")
    except OSError as e:
        print(f"[error] Failed to write {target_path}: {e}")
        sys.exit(1)


def main() -> None:
    apm_yml_path = "apm.yml"
    try:
        with open(apm_yml_path, "r", encoding="utf-8") as f:
            apm = yaml.safe_load(f)
    except OSError as e:
        print(f"[error] apm.yml not found or failed to read: {e}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[error] Failed to parse apm.yml: {e}")
        sys.exit(1)

    mcp_servers = build_mcp_servers(apm)

    update_claude_json(mcp_servers)
    update_settings_json(mcp_servers)


if __name__ == "__main__":
    main()
