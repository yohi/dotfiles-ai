"""Generate/update Claude settings files (.claude.json and claude/settings.json) from apm.yml.

This script filters out SSE/HTTP transport servers and only includes stdio servers
in the mcpServers configuration to comply with Claude Desktop's validation schema.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import yaml


def expand_env_vars(val: Any) -> Any:
    if isinstance(val, str):

        def repl(match: re.Match[str]) -> str:
            var_part = match.group(1)
            if ":-" in var_part:
                var_name, default_val = var_part.split(":-", 1)
                return os.environ.get(var_name, default_val)
            return os.environ.get(var_part, "")

        return re.sub(r"\$\{env:([^}]+)\}", repl, val)
    elif isinstance(val, list):
        return [expand_env_vars(x) for x in val]
    elif isinstance(val, dict):
        return {k: expand_env_vars(v) for k, v in val.items()}
    return val


def build_mcp_servers(apm: dict[str, Any]) -> dict[str, Any]:
    mcp_entries = (apm.get("dependencies") or {}).get("mcp") or []
    mcp_servers: dict[str, Any] = {}

    for entry in mcp_entries:
        if not entry.get("enabled", True):
            continue
        transport = entry.get("transport", "stdio")
        name = str(entry["name"])

        # Convert remote SSE / HTTP transport servers to stdio using mcp-remote bridge for Claude
        if transport in ("sse", "http", "streamable-http"):
            url = entry.get("url")
            if not url:
                print(
                    f"[warning] Skipping MCP server '{name}': url is missing for sse transport."
                )
                continue
            expanded_url = expand_env_vars(str(url))
            args = ["-y", "mcp-remote", expanded_url]

            headers = entry.get("headers")
            if headers:
                for k, v in headers.items():
                    args.extend(["--header", f"{k}:{v}"])

            remote_cfg: dict[str, Any] = {
                "type": "stdio",
                "command": "npx",
                "args": args,
            }
            if entry.get("env"):
                remote_cfg["env"] = {
                    k: expand_env_vars(str(v)) for k, v in entry["env"].items()
                }

            mcp_servers[name] = remote_cfg
            continue

        command = entry.get("command")
        if not command:
            print(
                f"[warning] Skipping MCP server '{name}': command is missing or empty."
            )
            continue

        server_cfg: dict[str, Any] = {
            "type": "stdio",
            "command": expand_env_vars(str(command)),
            "args": [expand_env_vars(str(arg)) for arg in (entry.get("args") or [])],
        }
        if entry.get("env"):
            server_cfg["env"] = {
                k: expand_env_vars(str(v)) for k, v in entry["env"].items()
            }

        mcp_servers[name] = server_cfg

    return mcp_servers


def save_settings(
    target_path: str, mcp_servers: dict[str, Any], create_dir: bool = False
) -> None:
    if create_dir:
        target_dir = os.path.dirname(target_path)
        if target_dir:
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

    save_settings(".claude.json", mcp_servers)
    save_settings("claude/settings.json", mcp_servers, create_dir=True)


if __name__ == "__main__":
    main()
