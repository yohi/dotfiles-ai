#!/usr/bin/env python3
import subprocess
import sys
import re
import os

def run_cmd(cmd, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["PAGER"] = "cat"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=full_env)
    return res.stdout, res.returncode

def main():
    env = {"DOCKER_MCP_USE_CE": "true"}
    
    # 1. List catalogs
    stdout, code = run_cmd("docker mcp catalog list", env=env)
    if code != 0:
        print("[x] Failed to list docker mcp catalogs. Make sure docker-mcp CLI is installed.")
        sys.exit(1)
        
    refs = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("Reference"):
            continue
        parts = line.split()
        if parts:
            refs.append(parts[0])
            
    # 2. Extract OAuth servers from catalogs
    oauth_servers = []
    for ref in refs:
        show_stdout, show_code = run_cmd(f"docker mcp catalog show {ref}", env=env)
        if show_code != 0:
            continue
            
        try:
            import yaml
            data = yaml.safe_load(show_stdout)
            if data and "servers" in data:
                for s in data["servers"]:
                    server_info = s.get("snapshot", {}).get("server", {})
                    if not server_info:
                        server_info = s.get("server", {})
                    if server_info and "oauth" in server_info:
                        name = server_info.get("name")
                        if name and name not in oauth_servers:
                            oauth_servers.append(name)
        except ImportError:
            current_name = None
            for line in show_stdout.split("\n"):
                name_match = re.search(r'^\s*name:\s*([\w\-]+)', line)
                if name_match:
                    current_name = name_match.group(1)
                elif "oauth:" in line and current_name:
                    if current_name not in oauth_servers:
                        oauth_servers.append(current_name)
                        
    # 3. Extract remote-type servers from current profile
    profile_stdout, profile_code = run_cmd("docker mcp profile server ls", env=env)
    if profile_code == 0:
        for line in profile_stdout.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                server_type = parts[1].strip()
                server_id = parts[2].strip()
                if server_type == "remote" and server_id not in oauth_servers:
                    oauth_servers.append(server_id)

    if not oauth_servers:
        print("[!] No OAuth-enabled MCP servers found.")
        sys.exit(0)
        
    print("[i] Available OAuth-enabled MCP servers:")
    for idx, server in enumerate(oauth_servers, 1):
        print(f"  {idx}) {server}")
        
    try:
        choice = input("\nSelect a server to authorize (1-%d): " % len(oauth_servers))
        choice_idx = int(choice.strip()) - 1
        if choice_idx < 0 or choice_idx >= len(oauth_servers):
            raise ValueError()
    except (ValueError, KeyboardInterrupt, EOFError):
        print("\n[!] Invalid choice or operation canceled.")
        sys.exit(1)
        
    target_server = oauth_servers[choice_idx]
    import webbrowser

    cmd = ["docker", "mcp", "oauth", "authorize", target_server]
    print(f"[*] Executing: {' '.join(cmd)}")
    
    auth_env = os.environ.copy()
    auth_env["DOCKER_MCP_USE_CE"] = "true"
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=auth_env
    )
    
    url_pattern = re.compile(r'(https?://[^\s\)]+)')
    browser_opened = False
    
    for line in iter(process.stdout.readline, ''):
        # Capture authorization URL and open it with parameters stripped if sentry-remote
        if "oauth/authorize" in line:
            match = url_pattern.search(line)
            if match and not browser_opened:
                url = match.group(1)
                if target_server == "sentry-remote":
                    # Strip resource parameter
                    clean_url = re.sub(r'&resource=[^&\s]+', '', url)
                    line = line.replace(url, clean_url)
                    url = clean_url
                
                print(line, end="")
                try:
                    webbrowser.open(url)
                    browser_opened = True
                    print("[*] Automatically opened browser with patched URL (stripped resource parameter).")
                except Exception as e:
                    print(f"[!] Failed to open browser automatically: {e}")
                continue
        print(line, end="")
        
    process.wait()
    returncode = process.returncode
    
    if returncode == 0:
        print(f"\n[+] Authorization successful for '{target_server}'!")
    else:
        print(f"\n[x] Authorization failed for '{target_server}' (Exit code: {returncode})")

if __name__ == "__main__":
    main()
