#!/usr/bin/env python3

from __future__ import annotations
import os
import re
import sys
from pathlib import Path
from typing import Any, cast, Match, Dict, List
import yaml

def get_gateway_token() -> str:
    token = os.environ.get("MCP_GATEWAY_TOKEN")
    if not token:
        repo_root = Path(__file__).parent.parent.resolve()
        env_path = repo_root / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            match = re.search(r"^\s*MCP_GATEWAY_TOKEN\s*=\s*(.+)$", content, re.MULTILINE)
            if match:
                token = match.group(1).strip().strip('"').strip("'")
    return token or ""

def load_client_config() -> dict[str, Any]:
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
            raise ValueError(f"Required environment variable '${var_name}' is not set and has no default value.")

        s = re.sub(r"\${(\w+)(?::-([^}]+))?}", _get_env, s)

        if expand_paths:
            if s.startswith("/") or s.startswith("~"):
                s = str(Path(s).expanduser().resolve())
        return cast(str, s)
    return data

def main() -> int:
    repo_root = Path(__file__).parent.parent.resolve()
    servers_yaml_path = repo_root / "mcp" / "servers.yaml"
    
    config = load_client_config()
    if not config:
        print(f"Error: {servers_yaml_path} not found or empty.")
        return 1

    defaults = cast(Dict[str, Any], config.get("defaults", {}))
    gateway_url = cast(str, defaults.get("gateway_url", "http://127.0.0.1:10888/sse"))

    all_servers_raw = cast(Dict[str, Any], config.get("servers", {}))
    gateway_servers_raw = cast(Dict[str, Any], replace_placeholders(all_servers_raw, gateway_url))
    
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
    config_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    config_yaml_path.write_text(
        yaml.dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    catalog_servers: dict[str, Any] = {}
    enabled_servers = cast(List[str], gateway_config["gateway"]["enabled_servers"])
    for name in enabled_servers:
        if name in all_servers_raw:
            catalog_servers[name] = replace_placeholders(all_servers_raw[name], gateway_url, expand_paths=True)

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

    print("✅ Gateway backend configuration rendered successfully.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
