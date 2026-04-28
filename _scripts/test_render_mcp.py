#!/usr/bin/env python3
import importlib.util
import sys
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

def test_gateway_config_loading():
    print("Testing gateway configuration loading...")
    config = load_config()
    if not config:
        print("Warning: config is empty, but this might be normal if servers.yaml is missing.")
    else:
        if "servers" not in config:
            raise AssertionError("Key 'servers' missing in config")
        print("PASS: Configuration loaded correctly.")

if __name__ == "__main__":
    try:
        test_placeholders()
        test_gateway_config_loading()
        print("\n🎉 All specific verification points passed!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
