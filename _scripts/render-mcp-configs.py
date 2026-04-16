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
CLIENT_CONFIG_PATH = REPO_ROOT / "mcp" / "servers.yaml"


def load_yaml_config(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Malformed config at {path}: expected a mapping at the top level"
        )
    return loaded


def load_client_config() -> dict[str, Any]:
    return load_yaml_config(CLIENT_CONFIG_PATH)


def parse_jsonc(text: str) -> dict[str, Any]:
    return cast(dict[str, Any], json5.loads(text))


def replace_placeholders(value: Any, gateway_url: str) -> Any:
    if isinstance(value, str):
        # 置換対象のマップ
        val = value

        # ${VAR} または ${VAR:-default} 形式の環境変数を探し、展開する
        def env_replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_val = match.group(2)

            val_env = os.environ.get(var_name)
            if val_env:
                return val_env

            # Fallback for renamed MCP token
            if var_name == "MCP_GATEWAY_TOKEN":
                auth_token = os.environ.get("MCP_AUTH_TOKEN")
                if auth_token:
                    return auth_token

            if default_val is not None:
                return default_val

            raise ValueError(
                f"Required environment variable '{var_name}' is not set and no default provided. "
                "Please check your .env file or environment."
            )

        # ${VAR:-default} 形式にマッチする正規表現
        env_pattern = re.compile(r"\$\{([^}:-]+)(?::-(.*))?\}")
        val = env_pattern.sub(env_replacer, val)

        # プレースホルダの置換
        placeholders = {
            "__GATEWAY_URL__": gateway_url,
            "__HOME__": str(Path.home()),
            "__REPO_ROOT__": str(REPO_ROOT),
        }

        # __PROGRAM__ プレースホルダのスマート置換
        # ~/program/path と ~/program/private/path のうち、存在する方を優先する
        if "__PROGRAM__" in val:
            home = Path.home()
            # __PROGRAM__/project/path -> project/path
            rel_path = val.replace("__PROGRAM__", "").lstrip("/")
            
            # 候補1: ~/program/project/path
            cand1 = home / "program" / rel_path
            # 候補2: ~/program/private/project/path
            cand2 = home / "program" / "private" / rel_path
            
            # プロジェクトのルートディレクトリ（rel_pathの最初のセグメント）で存在確認
            project_name = rel_path.split("/")[0] if rel_path else ""
            if project_name:
                if (home / "program" / "private" / project_name).is_dir():
                    val = val.replace("__PROGRAM__", str(home / "program" / "private"))
                else:
                    val = val.replace("__PROGRAM__", str(home / "program"))
            else:
                # パスが空の場合はデフォルトとして ~/program を使用
                val = val.replace("__PROGRAM__", str(home / "program"))

        for k, v in placeholders.items():
            val = val.replace(k, v)

        return val

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


def _ensure_jsonc_key_exists(
    path: Path, root_key: str, template_content: str, search_pattern: str | re.Pattern[str]
) -> str:
    """JSONCファイルにキーまたはマーカーが存在することを確認し、なければ挿入する。更新後のテキストを返す。"""
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    if isinstance(search_pattern, str):
        match = re.search(search_pattern, text)
    else:
        match = search_pattern.search(text)

    if not match:
        if not text:
            # ファイルが空または存在しない場合
            text = f"{{\n{template_content}\n}}\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif text.strip().endswith("}"):
            # 末尾の中括弧の前に挿入
            pos = text.rfind("}")
            last_char = text[:pos].rstrip()[-1:] if text[:pos].rstrip() else ""
            prefix = "" if last_char in ("{", ",") else ",\n"
            text = text[:pos] + f"{prefix}{template_content}\n" + text[pos:]
            path.write_text(text, encoding="utf-8")

        # 再度検索
        if isinstance(search_pattern, str):
            match = re.search(search_pattern, text)
        else:
            match = search_pattern.search(text)

        if not match:
            raise RuntimeError(f"Could not ensure existence of pattern in {path}")

    return text


def write_opencode_jsonc(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    marker_pattern = re.compile(
        r"^(\s*)// \[MCP\]\r?\n.*?^(\s*)// \[LSP\]",
        re.MULTILINE | re.DOTALL,
    )
    template = f'  // [MCP]\n  "{root_key}": {{}},\n  // [LSP]'
    text = _ensure_jsonc_key_exists(path, root_key, template, marker_pattern)
    match = marker_pattern.search(text)
    if not match:
        raise RuntimeError(f"Marker // [MCP] ... // [LSP] not found in {path}")

    # インデントの検出 (デフォルトは 2 スペース)
    indent = match.group(1) if match else "  "

    raw_block = json.dumps(servers, indent=2, ensure_ascii=False)
    block_lines = raw_block.splitlines()
    block = block_lines[0]
    if len(block_lines) > 1:
        # 各行にインデントを付与 (既存の 2 スペース + 検出されたインデント)
        block += "\n" + "\n".join(f"{indent}{line}" for line in block_lines[1:])

    # 置換文字列を作成 (末尾カンマ付き)
    replacement = f'{indent}// [MCP]\n{indent}"{root_key}": {block},\n{indent}// [LSP]'

    updated = text[: match.start()] + replacement + text[match.end() :]
    if text == updated:
        print(f"Skipped {path.name} (no changes)")
        return False

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
    key_pattern = rf'"{re.escape(root_key)}"\s*:\s*\{{'
    template = f'  "{root_key}": {{}}'
    text = _ensure_jsonc_key_exists(path, root_key, template, key_pattern)
    match = re.search(key_pattern, text)
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
    config = load_client_config()
    defaults = config.get("defaults", {})
    gateway_url = defaults.get("gateway_url")
    if not gateway_url:
        raise RuntimeError(
            f"Missing required 'gateway_url' in {CLIENT_CONFIG_PATH} under defaults"
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
