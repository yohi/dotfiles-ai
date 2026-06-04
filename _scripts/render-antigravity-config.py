import yaml
import json
import os
import re
import sys
import shutil
from pathlib import Path

def resolve_binary(cmd):
    if cmd in ["uvx", "npx"]:
        path = shutil.which(cmd)
        return path if path else cmd
    return cmd

def expand_placeholders(text):
    if not isinstance(text, str):
        return text
    
    home = str(Path.home())
    repo_root = str(Path(__file__).parent.parent.resolve())
    
    res = text.replace("__HOME__", home).replace("__REPO_ROOT__", repo_root)
    
    # ${env:VAR} or ${env:VAR:-DEFAULT}
    pattern = re.compile(r'\${env:([^:}]+)(?::-([^}]*))?}')
    def replace_env(match):
        var_name = match.group(1)
        default_value = match.group(2)
        return os.environ.get(var_name, default_value if default_value is not None else '')
    
    res = pattern.sub(replace_env, res)
    return res

def process_item(item):
    if isinstance(item, dict):
        return {k: process_item(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [process_item(v) for v in item]
    elif isinstance(item, str):
        return expand_placeholders(item)
    return item

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    apm_file = repo_root / 'apm.yml'
    if not apm_file.exists():
        print(f"Error: {apm_file} not found")
        sys.exit(1)

    with open(apm_file, 'r') as f:
        config = yaml.safe_load(f)

    mcp_servers = {}
    dependencies = config.get('dependencies', {})
    gateway_url = "http://localhost:10888/sse" # Default gateway

    for mcp in dependencies.get('mcp', []):
        name = mcp.get('name')
        if not name:
            continue
        
        standalone = mcp.get('standalone', False)
        transport = mcp.get('transport', 'stdio')
        
        server_config = {}
        
        if not standalone and (transport == 'stdio' or mcp.get('type') == 'stdio'):
            # Bridge to gateway
            server_config["serverUrl"] = f"{gateway_url}?server={name}"
        elif transport == 'sse' or mcp.get('type') == 'sse' or name == 'docker-mcp':
            # Remote SSE
            url = mcp.get('url', gateway_url)
            server_config["serverUrl"] = process_item(url)
            if 'headers' in mcp:
                server_config["headers"] = process_item(mcp['headers'])
        else:
            # Local stdio (Standalone)
            cmd = mcp.get('command')
            if not cmd:
                print(f"Error: Standalone Local stdio MCP server '{name}' is missing a 'command' field.", file=sys.stderr)
                sys.exit(1)
            server_config["command"] = resolve_binary(cmd)
            
            args = mcp.get('args')
            if args:
                server_config["args"] = process_item(args)
            
            env = mcp.get('env')
            if env:
                server_config["env"] = process_item(env)

        mcp_servers[name] = server_config

    output = {"mcpServers": mcp_servers}
    
    output_path = repo_root / 'antigravity' / 'mcp_config.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Generated {output_path}")

if __name__ == "__main__":
    main()
