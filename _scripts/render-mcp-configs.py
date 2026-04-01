#!/usr/bin/env python3

from __future__ import annotations

import os
import json
import json5
import re
import sys
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "mcp" / "servers.yaml"


def load_config() -> dict[str, Any]:
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Malformed config at {CONFIG_PATH}: expected a mapping at the top level"
        )
    return loaded


def parse_jsonc(text: str) -> dict[str, Any]:
    return cast(dict[str, Any], json5.loads(text))


def replace_placeholders(value: Any, gateway_url: str) -> Any:
    if isinstance(value, str):
        # __GATEWAY_URL__ を置換
        val = value.replace("__GATEWAY_URL__", gateway_url)

        # ${VAR} 形式の環境変数を探し、存在を確認する
        # (os.path.expandvars は未定義の変数を空文字に変換してしまうため)
        env_vars = re.findall(r"\$\{([^}]+)\}", val)
        for var in env_vars:
            if var not in os.environ:
                raise ValueError(
                    f"Required environment variable '{var}' is not set. "
                    "Please check your .env file or environment."
                )

        # すべて存在することが確認できたら展開
        return os.path.expandvars(val)
    if isinstance(value, list):
        return [replace_placeholders(item, gateway_url) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_placeholders(item, gateway_url)
            for key, item in value.items()
        }
    return value


def write_json_file(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_content: str | None = None
    data: dict[str, Any] = {}
    if path.exists():
        existing_content = path.read_text(encoding="utf-8")
        data = parse_jsonc(existing_content)
    data[root_key] = servers

    new_content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if existing_content is not None and existing_content == new_content:
        print(f"Skipped {path.name} (no changes)")
        return False

    path.write_text(new_content, encoding="utf-8")
    return True


def write_opencode_jsonc(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)

    text = ""
    if path.exists():
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

    if text:
        updated, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"Failed to update MCP block in {path}")

        if text == updated:
            print(f"Skipped {path.name} (no changes)")
            return False
    else:
        updated = f"{{\n{replacement}\n}}\n"

    path.write_text(updated, encoding="utf-8")
    return True


def find_object_span(text: str, open_brace_index: int) -> tuple[int, int]:
    i = open_brace_index
    depth = 0
    in_string = False
    escape = False

    while i < len(text):
        char = text[i]
        next_char = text[i + 1] if i + 1 < len(text) else ""

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == "/" and next_char == "/":
            i += 2
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        if char == '"':
            in_string = True
            i += 1
            continue

        if char == "{":
            depth += 1
            i += 1
            continue

        if char == "}":
            depth -= 1
            i += 1
            if depth == 0:
                return open_brace_index, i
            continue

        i += 1

    raise RuntimeError("Object closing brace not found")


def write_jsonc_object_key(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf'"{re.escape(root_key)}"\s*:\s*\{{', text)
    if not match:
        raise RuntimeError(f"Key '{root_key}' not found in {path}")

    open_brace_index = text.find("{", match.start())
    _, object_end = find_object_span(text, open_brace_index)

    line_start = text.rfind("\n", 0, match.start()) + 1
    top_level_indent_match = re.search(r'^(\s*)"[^"\n]+"\s*:', text, re.MULTILINE)
    indent = top_level_indent_match.group(1) if top_level_indent_match else "    "

    raw_block = json.dumps(servers, indent=2, ensure_ascii=False)
    block_lines = raw_block.splitlines()
    block = block_lines[0]
    if len(block_lines) > 1:
        block += "\n" + "\n".join(f"{indent}{line}" for line in block_lines[1:])

    replacement = f'{indent}"{root_key}": {block}'
    updated = text[:line_start] + replacement + text[object_end:]

    if text == updated:
        print(f"Skipped {path.name} (no changes)")
        return False

    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    config = load_config()
    defaults = config.get("defaults", {})
    gateway_url = defaults.get("gateway_url")
    if not gateway_url:
        raise RuntimeError(
            f"Missing required 'gateway_url' in {CONFIG_PATH} under defaults"
        )

    for agent_name, agent_config in config.get("agents", {}).items():
        path = REPO_ROOT / agent_config["path"]
        format_name = agent_config["format"]
        root_key = agent_config["root_key"]
        servers = replace_placeholders(agent_config["servers"], gateway_url)

        changed = False
        if format_name in {"json", "generated_json"}:
            changed = write_json_file(path, root_key, servers)
        elif format_name == "jsonc":
            path.parent.mkdir(parents=True, exist_ok=True)
            changed = write_jsonc_object_key(path, root_key, servers)
        elif format_name == "opencode_jsonc":
            changed = write_opencode_jsonc(path, root_key, servers)
        else:
            raise RuntimeError(
                f"Unsupported render format '{format_name}' for {agent_name}"
            )

        if changed:
            print(f"rendered {agent_name}: {path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
