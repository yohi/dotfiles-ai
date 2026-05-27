import yaml
import json
import os
import re
import sys

def expand_env_vars(text):
    if not isinstance(text, str):
        return text
    # ${env:VAR} or ${env:VAR:-DEFAULT}
    pattern = re.compile(r'\${env:([^:}]+)(?::-([^}]*))?}')
    def replace(match):
        var_name = match.group(1)
        default_value = match.group(2)
        return os.environ.get(var_name, default_value if default_value is not None else '')
    
    # Also handle simple $VAR or ${VAR} if necessary,
    # but based on apm.yml, the above format is used.
    return pattern.sub(replace, text)

def process_item(item):
    if isinstance(item, dict):
        return {k: process_item(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [process_item(v) for v in item]
    elif isinstance(item, str):
        # Special case for PWD in this project context
        text = item.replace("${env:PWD}", os.getcwd())
        return expand_env_vars(text)
    return item

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    apm_file = os.path.join(repo_root, 'apm.yml')
    if not os.path.exists(apm_file):
        print(f"Error: {apm_file} not found")
        sys.exit(1)

    with open(apm_file, 'r') as f:
        config = yaml.safe_load(f)

    mcp_servers = {}
    dependencies = config.get('dependencies', {})
    for mcp in dependencies.get('mcp', []):
        name = mcp.get('name')
        if not name:
            continue
        
        # Antigravity contract expects serverUrl for SSE Gateway
        # Default to the unified gateway URL if not explicitly provided
        server_url = mcp.get('serverUrl')
        if server_url:
            server_url = process_item(server_url)
        else:
            server_url = f"http://localhost:10888/sse?server={name}"
            
        server_config = {
            "serverUrl": server_url
        }
        mcp_servers[name] = server_config

    output = {"mcpServers": mcp_servers}
    
    output_path = os.path.join(repo_root, '.agents/mcp_config.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Generated {output_path}")

if __name__ == "__main__":
    main()
