#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "mcp" / "servers.yaml"


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def parse_jsonc(text: str) -> dict[str, Any]:
    stripped: list[str] = []
    in_string = False
    escape = False
    i = 0

    while i < len(text):
        char = text[i]

        if in_string:
            stripped.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            stripped.append(char)
            i += 1
            continue

        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        stripped.append(char)
        i += 1

    normalized = re.sub(r",(\s*[}\]])", r"\1", "".join(stripped))
    return json.loads(normalized)


def replace_placeholders(value: Any, gateway_url: str) -> Any:
    if isinstance(value, str):
        return value.replace("__GATEWAY_URL__", gateway_url)
    if isinstance(value, list):
        return [replace_placeholders(item, gateway_url) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_placeholders(item, gateway_url)
            for key, item in value.items()
        }
    return value


def write_json_file(path: Path, root_key: str, servers: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data[root_key] = servers
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_opencode_jsonc(path: Path, root_key: str, servers: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8")
    raw_block = json.dumps(servers, indent=2, ensure_ascii=False)
    block_lines = raw_block.splitlines()
    block = block_lines[0]
    if len(block_lines) > 1:
        block += "\n" + "\n".join(f"  {line}" for line in block_lines[1:])
    replacement = f'  // [MCP]\n  "{root_key}": {block},\n  // [LSP]'
    pattern = re.compile(
        r'^  // \[MCP\]\n.*?^  // \[LSP\]',
        re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Failed to update MCP block in {path}")
    path.write_text(updated, encoding="utf-8")
def main() -> int:
    config = load_config()
    defaults = config.get("defaults", {})
    gateway_url = defaults["gateway_url"]

    for agent_name, agent_config in config.get("agents", {}).items():
        path = REPO_ROOT / agent_config["path"]
        format_name = agent_config["format"]
        root_key = agent_config["root_key"]
        servers = replace_placeholders(agent_config["servers"], gateway_url)

        if format_name in {"json", "generated_json"}:
            write_json_file(path, root_key, servers)
        elif format_name == "jsonc":
            path.parent.mkdir(parents=True, exist_ok=True)
            data = parse_jsonc(path.read_text(encoding="utf-8"))
            data[root_key] = servers
            path.write_text(
                json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        elif format_name == "opencode_jsonc":
            write_opencode_jsonc(path, root_key, servers)
        else:
            raise RuntimeError(
                f"Unsupported render format '{format_name}' for {agent_name}"
            )

        print(f"rendered {agent_name}: {path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        raise SystemExit(1)
