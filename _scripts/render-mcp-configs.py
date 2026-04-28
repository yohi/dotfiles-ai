#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, cast, Match, Dict, List

import json5
import yaml


# --- Utilities ---

def get_gateway_token() -> str:
    """Retrieve the MCP gateway token from environment or .env file."""
    token = os.environ.get("MCP_GATEWAY_TOKEN")
    if not token:
        repo_root = Path(__file__).parent.parent.resolve()
        env_path = repo_root / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            # 行頭の空白や = 前後のスペースを許容する
            match = re.search(r"^\s*MCP_GATEWAY_TOKEN\s*=\s*(.+)$", content, re.MULTILINE)
            if match:
                token = match.group(1).strip().strip('"').strip("'")
    return token or ""


def load_client_config() -> dict[str, Any]:
    """Load and parse the servers.yaml configuration."""
    repo_root = Path(__file__).parent.parent.resolve()
    servers_yaml_path = repo_root / "mcp" / "servers.yaml"
    if not servers_yaml_path.exists():
        return {}
    with servers_yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if isinstance(data, dict):
            return cast(Dict[str, Any], data)
        return {}


def replace_placeholders(data: Any, gateway_url: str, expand_paths: bool = False) -> Any:
    """Recursively replace placeholders in strings."""
    home = str(Path.home())
    repo_root = str(Path(__file__).parent.parent.resolve())
    program_dir = os.environ.get("PROGRAM_DIR", str(Path.home() / "program" / "private"))

    if isinstance(data, dict):
        return {k: replace_placeholders(v, gateway_url, expand_paths) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_placeholders(v, gateway_url, expand_paths) for v in data]
    if isinstance(data, str):
        s = data.replace("__GATEWAY_URL__", gateway_url)
        s = s.replace("__HOME__", home)
        s = s.replace("__REPO_ROOT__", repo_root)
        s = s.replace("__PROGRAM__", program_dir)

        def _get_env(m: Match[str]) -> str:
            var_name = m.group(1)
            default_val = m.group(2)
            val = os.environ.get(var_name)
            if val is not None:
                return cast(str, val)
            if default_val is not None:
                return cast(str, default_val)
            raise ValueError(
                f"Required environment variable '${var_name}' is not set and has no default value."
            )

        s = re.sub(r"\${(\w+)(?::-([^}]+))?}", _get_env, s)

        if expand_paths:
            if s.startswith("/") or s.startswith("~"):
                s = str(Path(s).expanduser().resolve())
        return cast(str, s)
    return data


def write_opencode_jsonc(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    """Update OpenCode JSONC configuration with [MCP] / [LSP] markers."""
    marker_pattern = re.compile(
        r"^(\s*)// \[MCP\]\r?\n.*?^(\s*)// \[LSP\]", re.MULTILINE | re.DOTALL
    )
    if not path.exists():
        initial_text = (
            f"// vim: ft=jsonc\n{{\n  // [MCP]\n  \"{root_key}\": {{}},\n  // [LSP]\n}}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(initial_text, encoding="utf-8")

    text = path.read_text(encoding="utf-8")
    if not marker_pattern.search(text):
        last_brace = text.rfind("}")
        if last_brace != -1:
            insertion = (
                f',\n  // [MCP]\n  "{root_key}": {{}},\n  // [LSP]\n'
            )
            text = text[:last_brace].rstrip() + insertion + text[last_brace:]
            path.write_text(text, encoding="utf-8")

    mcp_json = json.dumps(servers, indent=2, ensure_ascii=False)
    mcp_json_indented = "\n".join("  " + line for line in mcp_json.splitlines())
    inner_json = mcp_json_indented.strip().lstrip("{").rstrip("}").strip()
    replacement = f'  // [MCP]\n  "{root_key}": {{\n  {inner_json}\n  }},\n  // [LSP]'
    new_text = marker_pattern.sub(replacement, text)

    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def write_json_config(
    path: Path, root_key: str, servers: dict[str, Any], project_key: str | None = None
) -> bool:
    """Update standard JSON configuration."""
    if not path.exists():
        data: dict[str, Any] = {root_key: servers}
    else:
        try:
            content = path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError) as e:
            print(f"❌ File error reading {path}: {e}", file=sys.stderr)
            return False
            
        try:
            data = cast(Dict[str, Any], json5.loads(content))
        except (ValueError, json.JSONDecodeError) as e:
            # json5.loads typically raises ValueError on parse error
            print(f"❌ JSON parse error in {path}: {e}", file=sys.stderr)
            return False

    if project_key:
        if "projects" not in data:
            data["projects"] = {}

        if project_key not in data["projects"]:
            data["projects"][project_key] = {}

        data["projects"][project_key][root_key] = servers
    else:
        data[root_key] = servers

    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == new_text:
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True


def write_toml_config(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    """Update standard TOML configuration."""
    lines = []
    lines.append(f"[{root_key}]")
    for name, srv in servers.items():
        # Sub-sections should also use root_key and follow the expected hierarchy
        lines.append(f"  [{root_key}.mcp.{name}]")
        if "url" in srv:
            lines.append(f"  url = \"{srv['url']}\"")
        else:
            cmd = srv.get("command")
            if isinstance(cmd, list):
                cmd = cmd[0]
            lines.append(f"  command = \"{cmd}\"")
            if "args" in srv:
                args_str = ", ".join(f'"{a}"' for a in srv["args"])
                lines.append(f"  args = [{args_str}]")
        
        env = srv.get("env")
        if env:
            lines.append(f"  [{root_key}.mcp.{name}.env]")
            for k, v in env.items():
                lines.append(f"    {k} = \"{v}\"")
        
        headers = srv.get("headers")
        if headers:
            lines.append(f"  [{root_key}.mcp.{name}.headers]")
            for k, v in headers.items():
                lines.append(f"    {k} = \"{v}\"")
    
    new_text = "\n".join(lines) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == new_text:
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    repo_root = Path(__file__).parent.parent.resolve()
    servers_yaml_path = repo_root / "mcp" / "servers.yaml"
    token = get_gateway_token()

    config = load_client_config()
    if not config:
        print(f"Error: {servers_yaml_path} not found or empty.")
        return 1

    defaults = cast(Dict[str, Any], config.get("defaults", {}))
    gateway_url = cast(str, defaults.get("gateway_url", "http://127.0.0.1:10888/sse"))

    all_servers_raw = cast(Dict[str, Any], config.get("servers", {}))
    gateway_servers_raw = cast(
        Dict[str, Any], replace_placeholders(all_servers_raw, gateway_url)
    )
    gateway_servers: dict[str, Any] = {}
    for name, cfg in gateway_servers_raw.items():
        if isinstance(cfg, dict) and cfg.get("type") in ["server", "local"]:
            srv = {k: v for k, v in cfg.items() if k not in ["title", "description"]}
            gateway_servers[name] = srv

    gateway_config = {
        "mcpServers": gateway_servers,
        "gateway": {"enabled_servers": list(gateway_servers.keys())},
    }
    config_yaml_path = repo_root / "mcp" / "config.yaml"
    config_yaml_path.write_text(
        yaml.dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    catalog_servers: dict[str, Any] = {}
    enabled_servers = cast(List[str], gateway_config["gateway"]["enabled_servers"])
    for name in enabled_servers:
        if name in all_servers_raw:
            catalog_servers[name] = replace_placeholders(
                all_servers_raw[name], gateway_url, expand_paths=True
            )

    catalog_config = {
        "version": 3,
        "name": "custom",
        "displayName": "Custom Servers",
        "registry": catalog_servers,
    }
    registry = cast(Dict[str, Any], catalog_config["registry"])
    for name, cfg in registry.items():
        if isinstance(cfg, dict):
            if "title" not in cfg:
                cfg["title"] = name.capitalize()
            if "description" not in cfg:
                cfg["description"] = f"Custom MCP server: {name}"

    catalog_yaml_path = repo_root / "mcp" / "catalogs" / "custom.yaml"
    catalog_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_yaml_path.write_text(
        yaml.dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    agents_dict = cast(Dict[str, Any], config.get("agents", {}))
    for agent_name, agent_cfg_raw in agents_dict.items():
        if not isinstance(agent_cfg_raw, dict):
            continue
        agent_cfg: dict[str, Any] = agent_cfg_raw

        # パスの存在確認とバリデーション
        agent_path_raw = agent_cfg.get("path")
        if not agent_path_raw or not isinstance(agent_path_raw, str):
            print(f"⚠️  Skipping agent '{agent_name}': 'path' is missing or not a string")
            continue

        path = repo_root / cast(str, replace_placeholders(agent_path_raw, gateway_url))
        fmt = cast(str, agent_cfg.get("format", "json"))
        root_key = cast(str, agent_cfg.get("root_key", "mcpServers"))
        project_key = cast(Any, agent_cfg.get("project_key"))
        if project_key == "__REPO_ROOT__":
            project_key = str(repo_root)

        agent_servers: dict[str, Any] = {}
        srv_map = cast(Dict[str, Any], agent_cfg.get("servers", {}))
        for srv_name, srv_opts_raw in srv_map.items():
            if not isinstance(srv_opts_raw, dict):
                continue
            srv_opts: dict[str, Any] = srv_opts_raw
            inherit_name = cast(str, srv_opts.get("inherit", srv_name))
            if inherit_name not in gateway_servers_raw:
                continue
            srv_def = cast(
                Dict[str, Any],
                replace_placeholders(gateway_servers_raw[inherit_name], gateway_url),
            )
            url_key = cast(str, srv_opts.get("url_key", "url"))
            final_srv: dict[str, Any] = {}
            if srv_def.get("type") == "sse":
                final_srv["type"] = "remote" if fmt == "opencode_jsonc" else "sse"
                final_srv[url_key] = srv_def.get("url")
                if token:
                    final_srv["headers"] = {"Authorization": f"Bearer {token}"}
                else:
                    print(f"⚠️  Warning: No token available for SSE server '{srv_name}' (agent: {agent_name})", file=sys.stderr)
            else:
                cmd_raw = srv_def.get("command")
                if isinstance(cmd_raw, list):
                    final_srv["command"] = cmd_raw[0]
                    final_srv["args"] = cast(List[Any], cmd_raw[1:]) + cast(List[Any], srv_def.get("args", []))
                else:
                    final_srv["command"] = cmd_raw
                    final_srv["args"] = cast(List[Any], srv_def.get("args", []))

                flattened_args: list[Any] = []
                for a in cast(List[Any], final_srv.get("args", [])):
                    if isinstance(a, list):
                        flattened_args.extend(a)
                    else:
                        flattened_args.append(a)
                final_srv["args"] = flattened_args

                final_srv["env"] = {}
                if "env" in srv_def:
                    env_def = srv_def["env"]
                    if isinstance(env_def, list):
                        for item in env_def:
                            if isinstance(item, dict):
                                final_srv["env"][cast(str, item["name"])] = item["value"]
                    else:
                        final_srv["env"] = cast(Dict[str, Any], env_def)

                if fmt == "opencode_jsonc":
                    final_srv["type"] = "local"

            if fmt == "opencode_jsonc":
                final_srv["enabled"] = True
            agent_servers[srv_name] = final_srv

        if fmt == "opencode_jsonc":
            updated = write_opencode_jsonc(path, root_key, agent_servers)
        elif fmt == "toml":
            updated = write_toml_config(path, root_key, agent_servers)
        else:
            updated = write_json_config(path, root_key, agent_servers, cast(str | None, project_key))

        if updated:
            print(f"rendered {agent_name}: {path.relative_to(repo_root)}")
        else:
            print(f"Skipped {agent_name} (no changes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
