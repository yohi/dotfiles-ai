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


def parse_jsonc(text: str, filename: str = "<string>") -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json5.loads(text))
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSONC in {filename}: {e}") from e


def _resolve_program_placeholder(val: str) -> str:
    """__PROGRAM__ プレースホルダのスマート置換を行う。
    ~/program/path と ~/program/private/path のうち、存在する方を優先する。"""
    if "__PROGRAM__" not in val:
        return val

    home = Path.home()
    # __PROGRAM__/project/path -> project/path
    rel_path = val.replace("__PROGRAM__", "").lstrip("/")

    # プロジェクトのルートディレクトリ(rel_pathの最初のセグメント)で存在確認
    project_name = rel_path.split("/")[0] if rel_path else ""
    if project_name:
        if (home / "program" / "private" / project_name).is_dir():
            return val.replace("__PROGRAM__", str(home / "program" / "private"))
        else:
            return val.replace("__PROGRAM__", str(home / "program"))
    else:
        # パスが空の場合はデフォルトとして ~/program を使用
        return val.replace("__PROGRAM__", str(home / "program"))


def replace_placeholders(value: Any, gateway_url: str, expand_paths: bool = True) -> Any:
    if isinstance(value, str):
        # 置換対象のマップ
        val = value

        # ${VAR} または ${VAR:-default} 形式の環境変数を探し、展開する
        def env_replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_val = match.group(2)

            val_env = os.environ.get(var_name)
            if val_env is not None:
                return val_env

            # Fallback for renamed MCP token
            if var_name == "MCP_GATEWAY_TOKEN":
                auth_token = os.environ.get("MCP_AUTH_TOKEN")
                if auth_token is not None:
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

        if expand_paths:
            # プレースホルダの置換
            placeholders = {
                "__GATEWAY_URL__": gateway_url,
                "__HOME__": str(Path.home()),
                "__REPO_ROOT__": str(REPO_ROOT),
            }

            # __PROGRAM__ プレースホルダのスマート置換
            val = _resolve_program_placeholder(val)

            # チルダ展開 (~/ で始まる場合)
            if val.startswith("~/"):
                val = str(Path(val).expanduser())

            for k, v in placeholders.items():
                val = val.replace(k, v)

        return val

    if isinstance(value, list):
        return [replace_placeholders(item, gateway_url, expand_paths) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_placeholders(item, gateway_url, expand_paths)
            for key, item in value.items()
        }
    return value


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """再帰的に辞書をマージする。"""
    for key, value in update.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def write_json_file(path: Path, root_key: str, servers: dict[str, Any], project_key: str | None = None) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_content: str | None = None
    data: dict[str, Any] = {}
    if path.exists():
        existing_content = path.read_text(encoding="utf-8")
        data = parse_jsonc(existing_content, path.name)

    if project_key:
        if "projects" not in data:
            data["projects"] = {}
        if project_key not in data["projects"]:
            data["projects"][project_key] = {}
        
        # 指定されたプロジェクト配下の root_key を完全に置換
        data["projects"][project_key][root_key] = servers
        # 重複を防ぐため、トップレベルに同名のキーがあれば削除
        if root_key in data:
            del data[root_key]
    else:
        # トップレベルの root_key を完全に置換
        data[root_key] = servers

    new_content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if existing_content is not None and existing_content == new_content:
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


def to_toml_inline_table(val: dict[str, Any]) -> str:
    """辞書を TOML インラインテーブル形式 { k = "v" } に変換する。"""
    parts = []
    for k, v in val.items():
        if isinstance(v, str):
            v_str = json.dumps(v)
        elif isinstance(v, (int, float, bool)):
            v_str = str(v).lower() if isinstance(v, bool) else str(v)
        elif isinstance(v, list):
            items = []
            for i in v:
                if isinstance(i, str):
                    items.append(json.dumps(i))
                elif isinstance(i, bool):
                    items.append(str(i).lower())
                else:
                    items.append(str(i))
            v_str = "[" + ", ".join(items) + "]"
        elif isinstance(v, dict):
            v_str = to_toml_inline_table(v)
        else:
            v_str = json.dumps(str(v))
        parts.append(f'{k} = {v_str}')
    return "{ " + ", ".join(parts) + " }"


def write_toml_file(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 簡易的な TOML 書き出し (Codex の mcp_servers 形式に特化)
    lines = []
    for name, cfg in servers.items():
        lines.append(f"[{root_key}.{name}]")
        for k, v in cfg.items():
            if isinstance(v, str):
                lines.append(f'{k} = {json.dumps(v)}')
            elif isinstance(v, (int, float, bool)):
                v_str = str(v).lower() if isinstance(v, bool) else str(v)
                lines.append(f"{k} = {v_str}")
            elif isinstance(v, list):
                items = []
                for i in v:
                    if isinstance(i, str):
                        items.append(json.dumps(i))
                    elif isinstance(i, bool):
                        items.append(str(i).lower())
                    else:
                        items.append(str(i))
                v_str = ", ".join(items)
                lines.append(f"{k} = [{v_str}]")
            elif isinstance(v, dict):
                v_str = to_toml_inline_table(v)
                lines.append(f"{k} = {v_str}")
            else:
                raise TypeError(f"Unsupported value type {type(v)} for key '{k}' in TOML writer")
        lines.append("")

    sections_block = "\n".join(lines).strip()
    
    existing_content = None
    if path.exists():
        existing_content = path.read_text(encoding="utf-8")
        if f"[{root_key}." in existing_content:
            # 既存の同一ルートキーセクションを置換 (行頭の [ または EOF まで)
            pattern = re.compile(rf"^\[{re.escape(root_key)}\..*?(?=\n^\[|\Z)", re.DOTALL | re.MULTILINE)
            new_content = pattern.sub("", existing_content).strip()
            if new_content:
                new_content += "\n\n" + sections_block
            else:
                new_content = sections_block
        else:
            new_content = existing_content.strip() + "\n\n" + sections_block
    else:
        new_content = sections_block

    new_content = new_content.strip() + "\n"

    if existing_content == new_content:
        print(f"Skipped {path.name} (no changes)")
        return False

    path.write_text(new_content, encoding="utf-8")
    return True


def _normalize_opencode_remote(server_cfg: dict[str, Any]):
    """OpenCode 用にリモートサーバー設定を正規化する"""
    server_cfg["type"] = "remote"
    server_cfg["enabled"] = True


def main() -> int:
    config = load_client_config()
    defaults = config.get("defaults", {})
    gateway_url = defaults.get("gateway_url")
    if not gateway_url:
        raise RuntimeError(
            f"Missing required 'gateway_url' in {CLIENT_CONFIG_PATH} under defaults"
        )

    # 1. Generate mcp/config.yaml (Gateway config)
    # プレースホルダを維持したまま (expand_paths=False) ゲートウェイ用のサーバー定義を取得
    gateway_servers_raw = replace_placeholders(config.get("servers", {}), gateway_url, expand_paths=False)
    
    # ゲートウェイ用には "server" タイプのサーバーのみを抽出
    gateway_servers = {
        name: cfg for name, cfg in gateway_servers_raw.items()
        if cfg.get("type") == "server"
    }

    gateway_config = {
        "mcpServers": gateway_servers,
        "gateway": {
            "enabled_servers": list(gateway_servers.keys())
        }
    }
    config_yaml_path = REPO_ROOT / "mcp" / "config.yaml"
    config_yaml_path.write_text(
        yaml.dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8"
    )
    print(f"Generated gateway config: {config_yaml_path.relative_to(REPO_ROOT)}")

    # 2. Generate mcp/catalogs/custom.yaml (Catalog config)
    # カタログには全てのサーバー (sse, local 等含む) を展開済みパス (expand_paths=True) で含める
    catalog_servers = replace_placeholders(config.get("servers", {}), gateway_url, expand_paths=True)
    catalog_config = {
        "version": 3,
        "name": "custom",
        "displayName": "Custom Servers",
        "registry": catalog_servers
    }
    # Catalog 用に title と description が欠けている場合に補完する
    for name, cfg in catalog_config["registry"].items():
        if "title" not in cfg:
            cfg["title"] = name.capitalize()
        if "description" not in cfg:
            cfg["description"] = f"{cfg['title']} MCP server"

    custom_yaml_path = REPO_ROOT / "mcp" / "catalogs" / "custom.yaml"
    custom_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    custom_yaml_path.write_text(
        yaml.dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8"
    )
    print(f"Generated catalog config: {custom_yaml_path.relative_to(REPO_ROOT)}")

    # 3. Render each agent's config
    for agent_name, agent_config in config.get("agents", {}).items():
        path = REPO_ROOT / agent_config["path"]
        format_name = agent_config["format"]
        root_key = agent_config["root_key"]
        project_key = agent_config.get("project_key")
        # project_key のプレースホルダ置換
        if project_key:
            project_key = replace_placeholders(project_key, gateway_url)
        url_key = agent_config.get("url_key", "url")
        
        # 継承(inherit)を展開する
        raw_servers = agent_config.get("servers", {})
        processed_servers = {}
        for s_name, s_cfg in raw_servers.items():
            if "inherit" in s_cfg:
                base_name = s_cfg["inherit"]
                if base_name not in config.get("servers", {}):
                    raise RuntimeError(
                        f"Undefined inherit target '{base_name}' referenced by agent '{agent_name}' server '{s_name}'"
                    )
                base_cfg = config.get("servers", {})[base_name]
                
                # 個別の url_key 指定があれば優先する
                actual_url_key = s_cfg.get("url_key", url_key)

                if base_cfg.get("type") == "local":
                    # ローカル実行サーバーはそのままコピー
                    env_data = {e["name"]: e["value"] for e in base_cfg.get("env", [])} if "env" in base_cfg else {}
                    processed_servers[s_name] = {
                        "command": base_cfg.get("command", []),
                        "args": base_cfg.get("args", []),
                    }
                    
                    # 共通: args キーがなければ空リストで初期化
                    processed_servers[s_name].setdefault("args", [])

                    # OpenCode 用の調整
                    if format_name == "opencode_jsonc":
                        processed_servers[s_name]["environment"] = env_data
                        processed_servers[s_name]["enabled"] = True
                        processed_servers[s_name]["type"] = "local"
                        # OpenCode は command 配列に全て含める必要がある
                        full_command = []
                        orig_command = processed_servers[s_name].get("command", [])
                        if isinstance(orig_command, list):
                            full_command.extend(orig_command)
                        else:
                            full_command.append(orig_command)
                        
                        full_command.extend(processed_servers[s_name].get("args", []))
                        processed_servers[s_name]["command"] = full_command
                        # args キーを削除
                        processed_servers[s_name].pop("args", None)
                    else:
                        processed_servers[s_name]["env"] = env_data

                    # OpenCode 以外: command がリストなら先頭をコマンド名、残りを引数にする
                    if format_name != "opencode_jsonc":
                        c = processed_servers[s_name].get("command", [])
                        a = processed_servers[s_name].get("args", [])
                        if isinstance(c, list) and len(c) > 0:
                            processed_servers[s_name]["command"] = c[0]
                            # 既存の args があれば、command の残りの要素を先頭に追加
                            new_args = c[1:]
                            if a:
                                new_args.extend(a)
                            processed_servers[s_name]["args"] = new_args
                elif any(key in base_cfg for key in ["url", "httpUrl", "serverUrl"]):
                    # 基底定義に既にURLがある場合はそれを使用 (例: Atlassian 直接接続)
                    processed_servers[s_name] = base_cfg.copy()
                    
                    # 元の値を抽出
                    url_val = base_cfg.get("url") or base_cfg.get("httpUrl") or base_cfg.get("serverUrl")
                    
                    # 既存のURL関連キーを一旦削除
                    for k in ["url", "httpUrl", "serverUrl"]:
                        processed_servers[s_name].pop(k, None)
                    
                    processed_servers[s_name][actual_url_key] = url_val
                    
                    if format_name == "opencode_jsonc":
                        _normalize_opencode_remote(processed_servers[s_name])
                    elif "type" not in processed_servers[s_name]:
                        processed_servers[s_name]["type"] = "sse"
                    
                    # 基底定義で明示的にゲートウェイ認証が必要とされている場合
                    if base_cfg.get("_generated_by") == "gateway":
                        processed_servers[s_name]["_generated_by"] = "gateway"
                else:
                    # ゲートウェイ経由のSSE設定を構築
                    if format_name == "toml":
                        # Codex の SSE 形式: npx mcp-remote を推奨 (curl は永続接続に不向き)
                        processed_servers[s_name] = {
                            "command": "npx",
                            "args": ["-y", "mcp-remote", f"{gateway_url}?server={s_name}"]
                        }
                    else:
                        processed_servers[s_name] = {
                            actual_url_key: f"{gateway_url}?server={s_name}",
                        }
                        
                        # エージェントの形式に合わせて type を設定
                        if format_name == "opencode_jsonc":
                            _normalize_opencode_remote(processed_servers[s_name])
                        elif format_name in {"json", "jsonc"}:
                            # Gemini, Claude, VSCode, Cursor, Antigravity 等
                            processed_servers[s_name]["type"] = "sse"
                        
                        # 明示的にゲートウェイ経由であることをマーク (内部判定用)
                        processed_servers[s_name]["_generated_by"] = "gateway"
                    
                # Authorization ヘッダーが必要な場合
                gateway_token = (
                    os.environ.get('MCP_GATEWAY_AUTH_TOKEN') or
                    os.environ.get('MCP_GATEWAY_TOKEN') or
                    os.environ.get('MCP_AUTH_TOKEN')
                )
                
                if gateway_token and processed_servers[s_name].get("_generated_by") == "gateway":
                    if format_name != "toml":
                        processed_servers[s_name].setdefault("headers", {})
                        processed_servers[s_name]["headers"]["Authorization"] = f"Bearer {gateway_token}"
                    else:
                        # Codex/mcp-remote の場合は引数に追加
                        processed_servers[s_name].setdefault("args", [])
                        processed_servers[s_name]["args"].extend(["-H", f"Authorization: Bearer {gateway_token}"])
                
                # エージェント側の個別設定で上書き (inherit, url_key 以外)
                overrides = {k: v for k, v in s_cfg.items() if k not in {"inherit", "url_key"}}
                if overrides:
                    deep_merge(processed_servers[s_name], overrides)
                
                # 正規化 (Normalization): deep_merge による意図しない上書きを防止
                if format_name == "opencode_jsonc":
                    if processed_servers[s_name].get("_generated_by") == "gateway" or \
                       any(key in base_cfg for key in ["url", "httpUrl", "serverUrl"]):
                        _normalize_opencode_remote(processed_servers[s_name])
            else:
                # 静的エントリにも url_key 変換を適用する
                processed_servers[s_name] = s_cfg.copy()
                # url_key 指定があれば、既存の url 関連キーをそのキーに置換する
                url_val = s_cfg.get("url") or s_cfg.get("httpUrl") or s_cfg.get("serverUrl")
                if url_val:
                    for k in ["url", "httpUrl", "serverUrl"]:
                        processed_servers[s_name].pop(k, None)
                    processed_servers[s_name][url_key] = url_val

        # Identify if the gateway is used by this agent
        uses_gateway = any(
            s_name in {"docker-mcp", "docker-mcp-local"}
            for s_name in raw_servers.keys()
        )

        # Gateway-hosted servers are those with type "server" in the main config
        gateway_hosted_servers = {
            name for name, cfg in catalog_servers.items() if isinstance(cfg, dict) and cfg.get("type") == "server"
        }

        # Deduplicate: if gateway is used, remove servers that the gateway already provides
        if uses_gateway:
            servers_to_remove = []
            for s_name in processed_servers.keys():
                # Don't remove the gateway itself
                if s_name in {"docker-mcp", "docker-mcp-local"}:
                    continue
                # If the server is hosted by the gateway AND it was generated by the gateway (no user overrides that changed its origin), mark for removal
                if s_name in gateway_hosted_servers and processed_servers[s_name].get("_generated_by") == "gateway":
                    servers_to_remove.append(s_name)
                    print(f"Skipping '{s_name}' for agent '{agent_name}' because it is provided by the Gateway and has no custom overrides.")
            
            for s_name in servers_to_remove:
                processed_servers.pop(s_name, None)

        # プレースホルダ置換
        servers = replace_placeholders(processed_servers, gateway_url)

        # 不要なキー (title, description 等) を削除してクライアントをクリーンに保つ
        standard_keys = {
            "command", "args", "env", "type", "url", "httpUrl", "serverUrl",
            "headers", "enabled", "environment", "timeout", "root_key"
        }
        # エージェント固有の url_key も許可リストに加える
        allowed_keys = standard_keys | {url_key}

        for s_name, s_cfg in servers.items():
            if isinstance(s_cfg, dict):
                # 内部判定用キーを削除
                s_cfg.pop("_generated_by", None)
                filtered_cfg = {k: v for k, v in s_cfg.items() if k in allowed_keys}
                servers[s_name] = filtered_cfg

        changed = False
        if format_name in {"json", "generated_json"}:
            changed = write_json_file(path, root_key, servers, project_key=project_key)
        elif format_name == "toml":
            changed = write_toml_file(path, root_key, servers)
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
