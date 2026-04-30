#!/usr/bin/env python3

from __future__ import annotations
import os
import json
import re
import sys
import shutil
from pathlib import Path
from typing import Any, cast, Match, Dict
import yaml

try:
    import json5
except ImportError:
    json5 = None

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

def deploy_systemd_service(src_path: Path, dest_dir: Path, repo_root: str, enabled_servers: str) -> None:
    if not src_path.exists():
        print(f"Error: systemd unit template not found at {src_path}", file=sys.stderr)
        sys.exit(1)
    
    content = src_path.read_text(encoding="utf-8")
    content = content.replace("__REPO_ROOT__", repo_root)
    content = content.replace("__ENABLED_SERVERS__", enabled_servers)
    
    dest_path = dest_dir / src_path.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding="utf-8")
    print(f"  -> Deployed {src_path.name} to {dest_path}")

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
    
    # Filter candidates for Gateway (containerized only)
    gateway_candidates = {
        name: cfg for name, cfg in all_servers_raw.items()
        if isinstance(cfg, dict) and cfg.get("type") == "server"
    }
    gateway_servers_expanded = cast(Dict[str, Any], replace_placeholders(gateway_candidates, gateway_url, expand_paths=True))
    
    gateway_servers: dict[str, Any] = {}
    for name, cfg in gateway_servers_expanded.items():
        srv = {k: v for k, v in cfg.items() if k not in ["title", "description"]}
        gateway_servers[name] = srv

    enabled_servers_list = list(gateway_servers.keys())
    gateway_config = {
        "mcpServers": gateway_servers,
        "gateway": {"enabled_servers": enabled_servers_list},
    }
    
    # Render config.yaml
    config_yaml_path = repo_root / "mcp" / "config.yaml"
    config_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    config_yaml_path.write_text(
        yaml.safe_dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Render catalogs/custom.yaml
    catalog_servers: dict[str, Any] = {}
    for name in enabled_servers_list:
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
        yaml.safe_dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    print("✅ Gateway backend configuration rendered locally.")

    # Deployment to ~/.docker/mcp
    dot_docker_mcp = Path.home() / ".docker" / "mcp"
    dot_docker_mcp.mkdir(parents=True, exist_ok=True)
    
    # Copy config.yaml
    shutil.copy2(config_yaml_path, dot_docker_mcp / "config.yaml")
    
    # Catalogs directory symlink/setup
    dot_docker_catalogs = dot_docker_mcp / "catalogs"
    dot_docker_catalogs.mkdir(parents=True, exist_ok=True)
    
    # Create symlink for custom.yaml
    custom_catalog_dest = dot_docker_catalogs / "custom.yaml"
    if custom_catalog_dest.is_symlink() or custom_catalog_dest.exists():
        custom_catalog_dest.unlink()
    custom_catalog_dest.symlink_to(catalog_yaml_path)
    
    # Bootstrap symlink if it exists in repo
    bootstrap_src = repo_root / "mcp" / "catalogs" / "bootstrap.yaml"
    bootstrap_dest = dot_docker_catalogs / "bootstrap.yaml"
    if bootstrap_src.exists():
        if bootstrap_dest.is_symlink() or bootstrap_dest.exists():
            bootstrap_dest.unlink()
        bootstrap_dest.symlink_to(bootstrap_src)
    else:
        if bootstrap_dest.is_symlink() or bootstrap_dest.exists():
            bootstrap_dest.unlink()

    print(f"✅ Configs deployed to {dot_docker_mcp}")

    # Deploy systemd services
    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    enabled_servers_str = ",".join(enabled_servers_list)
    
    deploy_systemd_service(
        repo_root / "mcp" / "docker-mcp-gateway.service",
        systemd_user_dir,
        str(repo_root),
        enabled_servers_str
    )
    deploy_systemd_service(
        repo_root / "mcp" / "mcp-watchdog.service",
        systemd_user_dir,
        str(repo_root),
        enabled_servers_str
    )

    # Update AI Agent configs
    agents_config = cast(Dict[str, Any], config.get("agents", {}))
    for agent_name, agent_cfg in agents_config.items():
        path_str = agent_cfg.get("path")
        if not path_str:
            continue
        
        # Path might contain placeholders
        path_str = replace_placeholders(path_str, gateway_url, expand_paths=True)
        config_path = repo_root / path_str
        if not config_path.exists():
            # Try absolute path or relative to home
            config_path = Path(path_str).expanduser()
            if not config_path.exists():
                print(f"  [SKIP] Agent config not found: {path_str}")
                continue

        format_type = agent_cfg.get("format", "json")
        root_key = agent_cfg.get("root_key", "mcpServers")
        mapped_servers = agent_cfg.get("servers", {})
        
        # Prepare server definitions for this agent
        agent_mcp_servers: dict[str, Any] = {}
        for srv_name, mapping in mapped_servers.items():
            inherit_name = mapping.get("inherit", srv_name)
            if inherit_name in all_servers_raw:
                srv_def = all_servers_raw[inherit_name].copy()
                # Expand placeholders and paths
                srv_def = replace_placeholders(srv_def, gateway_url, expand_paths=True)
                # Clean up metadata
                srv_def.pop("title", None)
                srv_def.pop("description", None)
                srv_def.pop("_generated_by", None)
                
                # Special handling for type: local -> stdio
                if srv_def.get("type") == "local":
                    srv_def["type"] = "stdio"
                
                # Standardize command/args for stdio
                if srv_def.get("type") == "stdio" and isinstance(srv_def.get("command"), list):
                    cmd_list = srv_def["command"]
                    if cmd_list:
                        srv_def["command"] = cmd_list[0]
                        new_args = cmd_list[1:] + srv_def.get("args", [])
                        if new_args:
                            srv_def["args"] = new_args
                        else:
                            srv_def.pop("args", None)

                # Handle args/env format differences if necessary
                if "env" in srv_def and isinstance(srv_def["env"], list):
                    env_dict = {}
                    for e in srv_def["env"]:
                        if isinstance(e, dict) and "name" in e and "value" in e:
                            env_dict[e["name"]] = e["value"]
                    srv_def["env"] = env_dict

                agent_mcp_servers[srv_name] = srv_def

        # Adjust format for specific agents
        if agent_name == "gemini":
            # Gemini CLI expects command to be a string
            for srv in agent_mcp_servers.values():
                if srv.get("type") == "stdio" and isinstance(srv.get("command"), list):
                    full_cmd = srv["command"] + srv.get("args", [])
                    srv["command"] = " ".join(full_cmd)
                    srv.pop("args", None)

        if agent_name in ["opencode", "oh-my-opencode"]:
            # OpenCode expects type: remote instead of sse, and needs enabled: true
            for srv in agent_mcp_servers.values():
                if srv.get("type") == "sse":
                    srv["type"] = "remote"
                srv["enabled"] = True

        # Load, update, and save
        try:
            content = config_path.read_text(encoding="utf-8")
            if format_type in ["json", "opencode_jsonc"]:
                if json5 and (format_type == "opencode_jsonc" or "//" in content):
                    data = json5.loads(content)
                else:
                    data = json.loads(content)
                
                # Update mcpServers
                if root_key not in data:
                    data[root_key] = {}
                
                # Replace exactly what's in servers.yaml for this agent
                data[root_key] = agent_mcp_servers
                
                # Save
                with config_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  ✅ Updated agent config: {config_path}")
            
            elif format_type == "toml":
                import toml
                data = toml.loads(content)
                data[root_key] = agent_mcp_servers
                with config_path.open("w", encoding="utf-8") as f:
                    toml.dump(data, f)
                print(f"  ✅ Updated agent config (TOML): {config_path}")

        except Exception as e:
            print(f"  ❌ Failed to update agent config {config_path}: {e}")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
