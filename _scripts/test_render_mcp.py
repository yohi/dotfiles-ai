#!/usr/bin/env python3
import os
import json
import json5
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT / "_scripts"))

import importlib.util

# Load the module with hyphens
spec = importlib.util.spec_from_file_location("render_mcp_configs", str(REPO_ROOT / "_scripts/render-mcp-configs.py"))
render_mcp_configs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_mcp_configs)
replace_placeholders = render_mcp_configs.replace_placeholders
load_config = render_mcp_configs.load_config

def test_placeholders():
    print("Testing placeholders...")
    gateway_url = "http://localhost:10888/sse"
    
    # 1. Verify __HOME__
    home_val = replace_placeholders("__HOME__", gateway_url)
    assert home_val == str(Path.home()), f"Expected {Path.home()}, got {home_val}"
    print("PASS: __HOME__ replacement")

    # 2. Verify __REPO_ROOT__
    repo_val = replace_placeholders("__REPO_ROOT__", gateway_url)
    assert repo_val == str(REPO_ROOT), f"Expected {REPO_ROOT}, got {repo_val}"
    print("PASS: __REPO_ROOT__ replacement")

    # 3. Verify multiple placeholders
    multi_val = replace_placeholders("__REPO_ROOT__/__HOME__/__GATEWAY_URL__", gateway_url)
    expected = f"{REPO_ROOT}/{Path.home()}/{gateway_url}"
    assert multi_val == expected, f"Expected {expected}, got {multi_val}"
    print("PASS: Multiple placeholders replacement")

def test_chronos_graph_rendering():
    print("Testing chronos-graph rendering in output files...")
    config = load_config()
    agents = config.get("agents", {})
    
    for agent_name, agent_config in agents.items():
        path = REPO_ROOT / agent_config["path"]
        if not path.exists():
            print(f"SKIP: {agent_name} output file {path} not found.")
            continue
            
        content = path.read_text(encoding="utf-8")
        # Handle different formats
        if agent_config["format"] in {"json", "generated_json"}:
            data = json.loads(content)
        elif agent_config["format"] == "jsonc":
            data = json5.loads(content)
        elif agent_config["format"] == "opencode_jsonc":
            # Just check for existence as a quick test
            assert '"chronos-graph": {' in content, f"chronos-graph missing in {agent_name}"
            print(f"PASS: {agent_name} (opencode_jsonc) contains chronos-graph")
            continue
            
        root_key = agent_config["root_key"]
        servers = data.get(root_key, {})
        assert "chronos-graph" in servers, f"chronos-graph missing in {agent_name} ({path})"
        
        # Verify the content matches expected (uv tool run ...)
        chronos = servers["chronos-graph"]
        assert chronos["command"] == "uv", f"Invalid command in {agent_name}"
        assert "git+https://github.com/yohi/chronos-graph.git" in "".join(chronos["args"]), f"Invalid args in {agent_name}"
        print(f"PASS: {agent_name} rendered correctly.")

if __name__ == "__main__":
    try:
        test_placeholders()
        test_chronos_graph_rendering()
        print("\n🎉 All specific verification points passed!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
