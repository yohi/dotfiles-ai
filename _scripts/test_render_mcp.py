#!/usr/bin/env python3
import importlib.util
import sys
import os
import shutil
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

def test_gateway_config_loading_and_rendering():
    print("Testing gateway configuration loading and rendering...")
    config = load_config()
    if not config:
        raise AssertionError("Configuration is empty. servers.yaml must exist for testing.")
    
    if "servers" not in config:
        raise AssertionError("Key 'servers' missing in config")
    print("PASS: Configuration loaded correctly.")

    # Execution of the main renderer
    print("Running render_mcp_configs.main()...")
    exit_code = render_mcp_configs.main()
    if exit_code != 0:
        raise AssertionError(f"render_mcp_configs.main() returned non-zero exit code: {exit_code}")
    
    # Verification of artifacts
    dot_docker_mcp = Path.home() / ".docker" / "mcp"
    config_yaml = dot_docker_mcp / "config.yaml"
    custom_catalog = dot_docker_mcp / "catalogs" / "custom.yaml"
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    service_file = systemd_dir / "docker-mcp-gateway.service"

    if not config_yaml.exists():
        raise AssertionError(f"Generated config.yaml missing at {config_yaml}")
    if not custom_catalog.exists():
        raise AssertionError(f"Generated custom.yaml missing at {custom_catalog}")
    if not service_file.exists():
        raise AssertionError(f"Service file missing at {service_file}")
    
    # Verify placeholder replacement in service file
    service_content = service_file.read_text()
    if "__REPO_ROOT__" in service_content:
        raise AssertionError("Placeholder __REPO_ROOT__ found in deployed service file")
    
    print("PASS: Rendering and deployment verified.")

if __name__ == "__main__":
    try:
        test_placeholders()
        test_gateway_config_loading_and_rendering()
        print("\n🎉 All specific verification points passed!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
