#!/usr/bin/env python3

from __future__ import annotations
import os
import json
import re
import sys
import shutil
import shlex
from pathlib import Path
from typing import Any, cast, Match, Dict
import yaml

json5: Any
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
    
    # Try to derive program_dir from environment or use default
    program_dir = os.environ.get("PROGRAM_DIR")
    if not program_dir:
        # Fallback to parent of CHRONOS_GRAPH_PATH if it exists in env
        cg_path = os.environ.get("CHRONOS_GRAPH_PATH")
        if cg_path:
            # Expand ~ if present (though .env should have absolute paths)
            cg_path_abs = Path(cg_path).expanduser()
            program_dir = str(cg_path_abs.parent)
        else:
            program_dir = str(Path.home() / "program" / "private")

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

        s = re.sub(r"\${(\w+)(?::-([^}]*))?}", _get_env, s)

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
    agents_config = config.get("agents", {})
    if not isinstance(agents_config, dict):
        print(f"Error: 'agents' section in config must be a mapping, got {type(agents_config).__name__}")
        return 1

    for agent_name, agent_cfg in agents_config.items():
        if not isinstance(agent_cfg, dict):
            print(f"  [SKIP] Invalid config for agent {agent_name} (expected dict)")
            continue

        path_str = agent_cfg.get("path")
        if not path_str:
            continue
        
        if not isinstance(path_str, str):
            print(f"  [WARN] 'path' for agent {agent_name} must be a string, got {type(path_str).__name__}")
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
        if not isinstance(mapped_servers, dict):
            print(f"  [SKIP] 'servers' for agent {agent_name} must be a mapping")
            continue
        
        # Prepare server definitions for this agent
        agent_mcp_servers: dict[str, Any] = {}
        for srv_name, mapping in mapped_servers.items():
            if not isinstance(mapping, dict):
                print(f"  [WARN] Invalid mapping for {srv_name} in {agent_name} (expected dict)")
                continue
                
            inherit_name_val = mapping.get("inherit", srv_name)
            if not isinstance(inherit_name_val, (str, type(None))):
                print(f"  [WARN] 'inherit' for {srv_name} in {agent_name} must be a string")
                continue
            inherit_name = cast(str, inherit_name_val if inherit_name_val is not None else srv_name)
            inherit_val = all_servers_raw.get(inherit_name)
            
            if isinstance(inherit_val, dict):
                srv_def = inherit_val.copy()
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

                # Expand 'uv' or 'uvx' to absolute path if it's the command
                if srv_def.get("type") == "stdio" and srv_def.get("command") in ["uv", "uvx"]:
                    cmd_name = cast(str, srv_def["command"])
                    abs_path = shutil.which(cmd_name)
                    if abs_path:
                        srv_def["command"] = abs_path

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
            # Gemini CLI supports both command string and args array.
            # No need to merge them into a single string.
            pass

        if agent_name in ["opencode", "oh-my-opencode"]:
            # OpenCode expects type: remote instead of sse, and needs enabled: true
            for srv in agent_mcp_servers.values():
                if srv.get("type") == "sse":
                    srv["type"] = "remote"
                srv["enabled"] = True

        # Load, update, and save
        try:
            try:
                content = config_path.read_text(encoding="utf-8")
            except OSError as e:
                print(f"  ❌ Failed to read config {config_path}: {e}")
                continue

            if format_type in ["json", "opencode_jsonc"]:
                try:
                    if format_type == "opencode_jsonc":
                        if json5:
                            data = json5.loads(content)
                        else:
                            raise ValueError(f"json5 library is required for {format_type}")
                    elif json5 and "//" in content:
                        data = json5.loads(content)
                    else:
                        data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  ❌ Failed to parse JSON config {config_path}: {e}")
                    continue
                
                # Update mcpServers
                if root_key not in data:
                    data[root_key] = {}
                
                # Replace exactly what's in servers.yaml for this agent
                data[root_key] = agent_mcp_servers
                
                # Save
                try:
                    with config_path.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"  ✅ Updated agent config: {config_path}")
                except OSError as e:
                    print(f"  ❌ Failed to write config {config_path}: {e}")
            
            elif format_type == "toml":
                try:
                    import toml
                    data = toml.loads(content)
                    data[root_key] = agent_mcp_servers
                    with config_path.open("w", encoding="utf-8") as f:
                        toml.dump(data, f)
                    print(f"  ✅ Updated agent config (TOML): {config_path}")
                except ImportError:
                    print(f"  ❌ toml library is required for {config_path}")
                except (toml.TomlDecodeError, OSError) as e:
                    print(f"  ❌ Failed to handle TOML config {config_path}: {e}")
            else:
                print(f"  [SKIP] Unsupported format type '{format_type}' for {config_path}")

        except Exception as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            # Catch-all for truly unexpected bugs, but now inner blocks catch specific IO/Parse errors
            print(f"  ❌ Unexpected error ({type(e).__name__}) updating {config_path}: {e}")
            import traceback
            traceback.print_exc()

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
