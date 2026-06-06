import json
import os
import re
import shutil
import sys
import yaml

def replace_env_vars(val):
    if isinstance(val, str):
        # Match both ${env:VAR} and $VAR or ${VAR}
        matches = re.findall(r"\$\{env:([^}]+)\}", val)
        for var in matches:
            val = val.replace(f"${{env:{var}}}", os.environ.get(var, ""))
        # Standard env expansion
        val = os.path.expandvars(val)
    elif isinstance(val, dict):
        return {k: replace_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [replace_env_vars(x) for x in val]
    return val

def convert_lockfile(lockfile_path, output_path):
    if not os.path.exists(lockfile_path):
        raise FileNotFoundError(f"Error: {lockfile_path} not found.")
        
    with open(lockfile_path, "r", encoding="utf-8") as f:
        lock_data = yaml.safe_load(f)
        
    mcp_configs = lock_data.get("mcp_configs", {})
    mcp_servers = {}
    
    for name, cfg in mcp_configs.items():
        # Clean config representation for Antigravity
        server_cfg = {}
        if "command" in cfg:
            server_cfg["command"] = cfg["command"]
        if "args" in cfg:
            server_cfg["args"] = cfg["args"]
        if "env" in cfg:
            server_cfg["env"] = cfg["env"]
        if "url" in cfg:
            server_cfg["serverUrl"] = cfg["url"]
        if "headers" in cfg:
            server_cfg["headers"] = cfg["headers"]
            
        # Standardize command path resolving for typical environment executables
        if "command" in server_cfg and server_cfg["command"] == "uvx":
            # Resolve standard system uvx path if it exists
            resolved_path = shutil.which("uvx")
            if resolved_path:
                server_cfg["command"] = resolved_path
            else:
                for path in [os.path.expanduser("~/.local/bin/uvx"), "/usr/local/bin/uvx", "/usr/bin/uvx"]:
                    if os.path.exists(path):
                        server_cfg["command"] = path
                        break
        elif "command" in server_cfg and server_cfg["command"] == "npx":
            resolved_path = shutil.which("npx")
            if resolved_path:
                server_cfg["command"] = resolved_path
            else:
                for path in [os.path.expanduser("~/.linuxbrew/bin/npx"), "/usr/local/bin/npx", "/usr/bin/npx"]:
                    if os.path.exists(path):
                        server_cfg["command"] = path
                        break
                    
        # Apply environment variable replacement
        mcp_servers[name] = replace_env_vars(server_cfg)
        
    output_data = {"mcpServers": mcp_servers}
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"Successfully generated {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lockfile", default="apm.lock.yaml")
    parser.add_argument("--output", default="antigravity/mcp_config.json")
    args = parser.parse_args()
    try:
        convert_lockfile(args.lockfile, args.output)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
