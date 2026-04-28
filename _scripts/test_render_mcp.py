#!/usr/bin/env python3
import importlib.util
import sys
import unittest
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

class TestMCPRenderer(unittest.TestCase):
    def setUp(self):
        self.gateway_url = "http://localhost:10888/sse"
        self.config = render_mcp_configs.load_client_config()

    def test_placeholders(self):
        replace_placeholders = render_mcp_configs.replace_placeholders
        
        # 1. Verify __HOME__
        home_val = replace_placeholders("__HOME__", self.gateway_url)
        self.assertEqual(home_val, str(Path.home()))

        # 2. Verify __REPO_ROOT__
        repo_val = replace_placeholders("__REPO_ROOT__", self.gateway_url)
        self.assertEqual(repo_val, str(REPO_ROOT))

        # 3. Verify multiple placeholders
        multi_val = replace_placeholders("__REPO_ROOT__/__HOME__/__GATEWAY_URL__", self.gateway_url)
        expected = f"{REPO_ROOT}/{Path.home()}/{self.gateway_url}"
        self.assertEqual(multi_val, expected)

    def test_gateway_config_loading_and_rendering(self):
        self.assertTrue(self.config, "Configuration is empty. servers.yaml must exist for testing.")
        self.assertIn("servers", self.config, "Key 'servers' missing in config")

        # Execution of the main renderer
        exit_code = render_mcp_configs.main()
        self.assertEqual(exit_code, 0, "render_mcp_configs.main() returned non-zero exit code")
        
        # Verification of artifacts
        dot_docker_mcp = Path.home() / ".docker" / "mcp"
        config_yaml = dot_docker_mcp / "config.yaml"
        custom_catalog = dot_docker_mcp / "catalogs" / "custom.yaml"
        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        service_file = systemd_dir / "docker-mcp-gateway.service"

        self.assertTrue(config_yaml.exists(), f"Generated config.yaml missing at {config_yaml}")
        self.assertTrue(custom_catalog.exists(), f"Generated custom.yaml missing at {custom_catalog}")
        self.assertTrue(service_file.exists(), f"Service file missing at {service_file}")
        
        # Verify placeholder replacement in service file
        service_content = service_file.read_text()
        placeholders = ["__REPO_ROOT__", "__ENABLED_SERVERS__"]
        for ph in placeholders:
            self.assertNotIn(ph, service_content, f"Placeholder {ph} found in deployed service file")

if __name__ == "__main__":
    unittest.main()
