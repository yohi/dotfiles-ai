#!/usr/bin/env python3

from __future__ import annotations

import os
import json
import json5
import re
import sys
from pathlib import Path
from typing import Any

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
            match = re.search(r"^MCP_GATEWAY_TOKEN=(.+)$", content, re.MULTILINE)
            if match:
                token = match.group(1).strip().strip('"').strip("'")
    return token or ""

def replace_placeholders(data: Any, gateway_url: str, expand_paths: bool = False) -> Any:
    """Recursively replace placeholders in strings."""
    home = str(Path.home())
    repo_root = str(Path(__file__).parent.parent.resolve())
    program_dir = os.environ.get("PROGRAM_DIR", str(Path.home() / "program" / "private"))

    if isinstance(data, dict):
        return {k: replace_placeholders(v, gateway_url, expand_paths) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_placeholders(v, gateway_url, expand_paths) for v in data]
    elif isinstance(data, str):
        s = data.replace("__GATEWAY_URL__", gateway_url)
        s = s.replace("__HOME__", home)
        s = s.replace("__REPO_ROOT__", repo_root)
        s = s.replace("__PROGRAM__", program_dir)
        s = re.sub(r"\${(\w+)(?::-([^}]+))?}", lambda m: os.environ.get(m.group(1), m.group(2) or ""), s)
        if expand_paths:
            if s.startswith("/") or s.startswith("~"):
                s = str(Path(s).expanduser().resolve())
        return s
    return data

def write_opencode_jsonc(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    """Update OpenCode JSONC configuration with [MCP] / [LSP] markers."""
    marker_pattern = re.compile(r"^(\s*)// \[MCP\]\r?\n.*?^(\s*)// \[LSP\]", re.MULTILINE | re.DOTALL)
    if not path.exists():
        initial_text = f"// vim: ft=jsonc\n{{\n  // [MCP]\n  \"{root_key}\": {{}},\n  // [LSP]\n}}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(initial_text, encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    if not marker_pattern.search(text):
        last_brace = text.rfind("}")
        if last_brace != -1:
            text = text[:last_brace].rstrip() + f',\n  // [MCP]\n  "{root_key}": {{}},\n  // [LSP]\n' + text[last_brace:]
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

def write_json_config(path: Path, root_key: str, servers: dict[str, Any], project_key: str | None = None) -> bool:
    """Update standard JSON configuration."""
    if not path.exists(): data = {root_key: servers}
    else:
        try: data = json5.loads(path.read_text(encoding="utf-8"))
        except Exception as e: print(f"Error reading {path}: {e}"); return False
    if project_key:
        if "projects" not in data: data["projects"] = {}
        if project_key not in data["projects"]: data["projects"][project_key] = {}
        data["projects"][project_key][root_key] = servers
        if root_key in data: del data[root_key]
    else: data[root_key] = servers
    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == new_text: return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True

def write_toml_config(path: Path, root_key: str, servers: dict[str, Any]) -> bool:
    """Update standard TOML configuration."""
    lines = []
    lines.append(f"[{root_key}]")
    for name, srv in servers.items():
        lines.append(f"  [mcp_servers.{name}]")
        if "url" in srv: lines.append(f"  url = \"{srv['url']}\"")
        else:
            cmd = srv.get("command")
            if isinstance(cmd, list): cmd = cmd[0]
            lines.append(f"  command = \"{cmd}\"")
            if "args" in srv:
                args_str = ", ".join(f'"{a}"' for a in srv["args"])
                lines.append(f"  args = [{args_str}]")
        if "env" in srv and srv["env"]:
            lines.append(f"  [mcp_servers.{name}.env]")
            for k, v in srv["env"].items(): lines.append(f"    {k} = \"{v}\"")
        if "headers" in srv and srv["headers"]:
            lines.append(f"  [mcp_servers.{name}.headers]")
            for k, v in srv["headers"].items(): lines.append(f"    {k} = \"{v}\"")
    new_text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True

def main() -> int:
    REPO_ROOT = Path(__file__).parent.parent.resolve()
    servers_yaml_path = REPO_ROOT / "mcp" / "servers.yaml"
    token = get_gateway_token()
    if not servers_yaml_path.exists(): print(f"Error: {servers_yaml_path} not found."); return 1
    with servers_yaml_path.open(encoding="utf-8") as f: config = yaml.safe_load(f)
    defaults = config.get("defaults", {})
    gateway_url = defaults.get("gateway_url", "http://127.0.0.1:10888/sse")
    all_servers_raw = config.get("servers", {})
    gateway_servers_raw = replace_placeholders(all_servers_raw, gateway_url)
    gateway_servers = {}
    for name, cfg in gateway_servers_raw.items():
        if cfg.get("type") in ["server", "local"]:
            srv = {k: v for k, v in cfg.items() if k not in ["title", "description"]}
            gateway_servers[name] = srv
    gateway_config = { "mcpServers": gateway_servers, "gateway": { "enabled_servers": list(gateway_servers.keys()) } }
    config_yaml_path = REPO_ROOT / "mcp" / "config.yaml"
    config_yaml_path.write_text(yaml.dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True), encoding="utf-8")
    catalog_servers = {}
    for name in gateway_config["gateway"]["enabled_servers"]:
        if name in all_servers_raw: catalog_servers[name] = replace_placeholders(all_servers_raw[name], gateway_url, expand_paths=True)
    catalog_config = { "version": 3, "name": "custom", "displayName": "Custom Servers", "registry": catalog_servers }
    for name, cfg in catalog_config["registry"].items():
        if "title" not in cfg: cfg["title"] = name.capitalize()
        if "description" not in cfg: cfg["description"] = f"Custom MCP server: {name}"
    catalog_yaml_path = REPO_ROOT / "mcp" / "catalogs" / "custom.yaml"
    catalog_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_yaml_path.write_text(yaml.dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True), encoding="utf-8")

    for agent_name, agent_cfg in config.get("agents", {}).items():
        path = REPO_ROOT / replace_placeholders(agent_cfg.get("path"), gateway_url)
        fmt = agent_cfg.get("format", "json")
        root_key = agent_cfg.get("root_key", "mcpServers")
        project_key = agent_cfg.get("project_key")
        if project_key == "__REPO_ROOT__": project_key = str(REPO_ROOT)
        agent_servers = {}
        for srv_name, srv_opts in agent_cfg.get("servers", {}).items():
            inherit_name = srv_opts.get("inherit", srv_name)
            if inherit_name not in gateway_servers_raw: continue
            srv_def = replace_placeholders(gateway_servers_raw[inherit_name], gateway_url)
            url_key = srv_opts.get("url_key", "url")
            final_srv = {}
            if srv_def.get("type") == "sse":
                final_srv["type"] = "remote" if fmt == "opencode_jsonc" else "sse"
                final_srv[url_key] = srv_def.get("url")
                if token: final_srv["headers"] = { "Authorization": f"Bearer {token}" }
            else:
                cmd_raw = srv_def.get("command")
                if isinstance(cmd_raw, list): final_srv["command"] = cmd_raw[0]; final_srv["args"] = cmd_raw[1:] + srv_def.get("args", [])
                else: final_srv["command"] = cmd_raw; final_srv["args"] = srv_def.get("args", [])
                flattened_args = []
                for a in final_srv.get("args", []):
                    if isinstance(a, list): flattened_args.extend(a)
                    else: flattened_args.append(a)
                final_srv["args"] = flattened_args
                final_srv["env"] = {}
                if "env" in srv_def:
                    if isinstance(srv_def["env"], list):
                        for item in srv_def["env"]: final_srv["env"][item["name"]] = item["value"]
                    else: final_srv["env"] = srv_def["env"]
                if fmt == "opencode_jsonc": final_srv["type"] = "local"
            if fmt == "opencode_jsonc": final_srv["enabled"] = True
            agent_servers[srv_name] = final_srv

        if fmt == "opencode_jsonc": updated = write_opencode_jsonc(path, root_key, agent_servers)
        elif fmt == "toml": updated = write_toml_config(path, root_key, agent_servers)
        else: updated = write_json_config(path, root_key, agent_servers, project_key)
        if updated: print(f"rendered {agent_name}: {path.relative_to(REPO_ROOT)}")
        else: print(f"Skipped {agent_name} (no changes)")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        raise SystemExit(1) from exc
