#!/usr/bin/env python3
import importlib.util
import json
import json5
import sys
import toml  # type: ignore[import-untyped]
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT / "_scripts"))

# Load the module with hyphens
spec = importlib.util.spec_from_file_location(
    "render_mcp_configs", str(REPO_ROOT / "_scripts/render-mcp-configs.py")
)
if spec is None or spec.loader is None:
    raise ImportError("Could not load spec or loader for render_mcp_configs")

render_mcp_configs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_mcp_configs)

replace_placeholders = render_mcp_configs.replace_placeholders
load_config = render_mcp_configs.load_client_config

def test_placeholders():
    print("Testing placeholders...")
    gateway_url = "http://localhost:10888/sse"
    
    # 1. Verify __HOME__
    home_val = replace_placeholders("__HOME__", gateway_url)
    if home_val != str(Path.home()):
        raise AssertionError(f"Expected {Path.home()}, got {home_val}")
    print("PASS: __HOME__ replacement")

    # 2. Verify __REPO_ROOT__
    repo_val = replace_placeholders("__REPO_ROOT__", gateway_url)
    if repo_val != str(REPO_ROOT):
        raise AssertionError(f"Expected {REPO_ROOT}, got {repo_val}")
    print("PASS: __REPO_ROOT__ replacement")

    # 3. Verify multiple placeholders
    multi_val = replace_placeholders("__REPO_ROOT__/__HOME__/__GATEWAY_URL__", gateway_url)
    expected = f"{REPO_ROOT}/{Path.home()}/{gateway_url}"
    if multi_val != expected:
        raise AssertionError(f"Expected {expected}, got {multi_val}")
    print("PASS: Multiple placeholders replacement")

def test_jsonc_markers():
    print("Testing jsonc markers insertion...")
    import tempfile
    import json5
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.jsonc') as tmp:
        # Create a file without markers
        tmp.write('{\n  "existing": true\n}\n')
        tmp_path = Path(tmp.name)
    
    try:
        servers = {"test-server": {"command": "echo"}}
        # Call the actual function
        render_mcp_configs.write_opencode_jsonc(tmp_path, "mcp", servers)
        
        content = tmp_path.read_text(encoding="utf-8")
        if "// [MCP]" not in content:
            raise AssertionError("Missing [MCP] marker")
        if "// [LSP]" not in content:
            raise AssertionError("Missing [LSP] marker")
        if '"mcp": {' not in content:
            raise AssertionError("Missing root_key insertion")
        
        try:
            parsed = json5.loads(content)
        except Exception:
            print(f"Error parsing content: {content}")
            raise
        if parsed["mcp"]["test-server"]["command"] != "echo":
            raise AssertionError("JSONC parsed missing test-server command")
        
        # Test updating existing markers
        servers_updated = {"test-server": {"command": "echo2"}}
        render_mcp_configs.write_opencode_jsonc(tmp_path, "mcp", servers_updated)
        content_updated = tmp_path.read_text(encoding="utf-8")
        parsed_updated = json5.loads(content_updated)
        if parsed_updated["mcp"]["test-server"]["command"] != "echo2":
            raise AssertionError("Failed to update existing markers block")
        
        print("PASS: jsonc markers inserted and updated correctly.")
    finally:
        tmp_path.unlink(missing_ok=True)

def test_chronos_graph_rendering():
    print("Testing chronos-graph presence in output files...")
    config = load_config()
    agents = config.get("agents", {})
    if not agents:
        raise AssertionError("No agents found in configuration")
    
    # ゲートウェイURLを取得 (デフォルト値を使用)
    gateway_url = config.get("defaults", {}).get("gateway_url", "http://localhost:10888/sse")
    
    for agent_name, agent_config in agents.items():
        path = REPO_ROOT / agent_config["path"]
        if not path.exists():
            raise AssertionError(f"Output file {path} for {agent_name} not found")
            
        content = path.read_text(encoding="utf-8")
        # Handle different formats
        if agent_config["format"] in {"json", "generated_json"}:
            data = json.loads(content)
        elif agent_config["format"] in {"jsonc", "opencode_jsonc"}:
            data = json5.loads(content)
        elif agent_config["format"] == "toml":
            if toml:
                try:
                    data = toml.loads(content)
                except Exception as e:
                    raise AssertionError(f"Failed to parse rendered TOML for {agent_name} at {path}: {e}") from e

                # Walk the dict to find chronos-graph
                root_key = agent_config["root_key"]
                servers = data.get(root_key, {})
                if not any(k in servers for k in ["chronos-graph", "chronos_graph", "docker-mcp", "docker-mcp-local"]):
                    raise AssertionError(f"chronos-graph (or chronos_graph/gateway) missing in parsed TOML for {agent_name}")
                print(f"PASS: {agent_name} verified presence of chronos-graph via parsed TOML.")
                continue
            else:
                # Fallback to simple check if toml lib is missing
                if not any(k in content for k in ["chronos-graph", "chronos_graph", "docker-mcp", "docker-mcp-local"]):
                    raise AssertionError(f"chronos-graph (or chronos_graph/gateway) should be present in {agent_name} ({path})")
                print(f"PASS: {agent_name} verified presence of chronos-graph via text (toml lib missing).")
                continue
        else:
            raise ValueError(f"Unknown format '{agent_config['format']}' for {agent_name}")
            
        root_key = agent_config["root_key"]
        project_key = agent_config.get("project_key")
        
        if project_key:
            # Resolving project_key since it might contain placeholders like __REPO_ROOT__
            project_key = replace_placeholders(project_key, gateway_url)
            if "projects" not in data or project_key not in data["projects"] or root_key not in data["projects"][project_key]:
                raise AssertionError(f"root_key '{root_key}' missing under project '{project_key}' in {agent_name} ({path})")
            servers = data["projects"][project_key][root_key]
        else:
            if root_key not in data:
                raise AssertionError(f"root_key '{root_key}' missing in {agent_name} ({path})")
            servers = data[root_key]
        if not any(k in servers for k in ["chronos-graph", "chronos_graph", "docker-mcp", "docker-mcp-local"]):
            raise AssertionError(f"chronos-graph (or chronos_graph/gateway) should be present in {agent_name} ({path})")
        print(f"PASS: {agent_name} verified presence of chronos-graph via structured data.")

if __name__ == "__main__":
    try:
        test_placeholders()
        test_jsonc_markers()
        test_chronos_graph_rendering()
        print("\n🎉 All specific verification points passed!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
