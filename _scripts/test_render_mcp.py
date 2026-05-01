#!/usr/bin/env python3
import importlib.util
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

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
        # Create a temporary directory to isolate home
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_home = Path(self.tmp_dir.name)

    def test_placeholders(self):
        replace_placeholders = render_mcp_configs.replace_placeholders
        
        with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
            # 1. Verify __HOME__
            home_val = replace_placeholders("__HOME__", self.gateway_url)
            self.assertEqual(home_val, str(self.tmp_home))

            # 2. Verify __REPO_ROOT__
            repo_val = replace_placeholders("__REPO_ROOT__", self.gateway_url)
            self.assertEqual(repo_val, str(REPO_ROOT))

            # 3. Verify multiple placeholders
            multi_val = replace_placeholders("__REPO_ROOT__/__HOME__/__GATEWAY_URL__", self.gateway_url)
            expected = f"{REPO_ROOT}/{self.tmp_home}/{self.gateway_url}"
            self.assertEqual(multi_val, expected)

    def test_gateway_config_loading_and_rendering(self):
        self.assertTrue(self.config, "Configuration is empty. servers.yaml must exist for testing.")
        self.assertIn("servers", self.config, "Key 'servers' missing in config")

        # Execution of the main renderer with mocked Path.home
        with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
            exit_code = render_mcp_configs.main()
        
        self.assertEqual(exit_code, 0, "render_mcp_configs.main() returned non-zero exit code")
        
        # Verification of artifacts under temporary home
        dot_docker_mcp = self.tmp_home / ".docker" / "mcp"
        config_yaml = dot_docker_mcp / "config.yaml"
        custom_catalog = dot_docker_mcp / "catalogs" / "custom.yaml"
        systemd_dir = self.tmp_home / ".config" / "systemd" / "user"
        service_file = systemd_dir / "docker-mcp-gateway.service"

        self.assertTrue(config_yaml.exists(), f"Generated config.yaml missing at {config_yaml}")
        self.assertTrue(custom_catalog.exists(), f"Generated custom.yaml missing at {custom_catalog}")
        self.assertTrue(service_file.exists(), f"Service file missing at {service_file}")
        
        # Verify placeholder replacement in service file
        service_content = service_file.read_text()
        placeholders = ["__REPO_ROOT__", "__ENABLED_SERVERS__"]
        for ph in placeholders:
            self.assertNotIn(ph, service_content, f"Placeholder {ph} found in deployed service file")

    def test_bootstrap_yaml_deployment(self):
        dot_docker_catalogs = self.tmp_home / ".docker" / "mcp" / "catalogs"
        bootstrap_dest = dot_docker_catalogs / "bootstrap.yaml"
        bootstrap_src = REPO_ROOT / "mcp" / "catalogs" / "bootstrap.yaml"

        # Case 1: bootstrap.yaml exists in repo
        with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
            render_mcp_configs.main()
        
        if bootstrap_src.exists():
            self.assertTrue(bootstrap_dest.exists(), "bootstrap.yaml should be deployed when it exists in repo")
        
        # Case 2: bootstrap.yaml does NOT exist in repo (simulated)
        # We patch the instance method Path.exists via the class with autospec=True
        original_exists = render_mcp_configs.Path.exists
        def mock_exists(path_obj):
            if str(path_obj).endswith("bootstrap.yaml"):
                return False
            return original_exists(path_obj)

        with patch.object(render_mcp_configs.Path, "exists", autospec=True, side_effect=mock_exists):
            with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
                render_mcp_configs.main()
        
        self.assertFalse(bootstrap_dest.exists(), "bootstrap.yaml should be removed from dest if it doesn't exist in repo")

    def test_guards(self):
        # 1. Test when 'agents' is not a dict
        mock_config = {"defaults": {}, "servers": {}, "agents": ["not a dict"]}
        with patch.object(render_mcp_configs, "load_client_config", return_value=mock_config):
            with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
                # Redirect stdout to capture the error message
                from io import StringIO
                with patch("sys.stdout", new=StringIO()) as fake_out:
                    exit_code = render_mcp_configs.main()
                    self.assertEqual(exit_code, 1)
                    self.assertIn("must be a mapping", fake_out.getvalue())

        # 2. Test when agent_cfg is not a dict
        mock_config = {"defaults": {}, "servers": {}, "agents": {"gemini": "not a dict"}}
        with patch.object(render_mcp_configs, "load_client_config", return_value=mock_config):
            with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
                with patch("sys.stdout", new=StringIO()) as fake_out:
                    exit_code = render_mcp_configs.main()
                    self.assertEqual(exit_code, 0)
                    self.assertIn("[SKIP] Invalid config for agent gemini", fake_out.getvalue())

    def test_gemini_command_quoting(self):
        import json
        import shlex
        from typing import Any
        
        mock_config: dict[str, Any] = {
            "defaults": {"gateway_url": "http://localhost:10888/sse"},
            "servers": {
                "server with space": {
                    "type": "local",
                    "command": "/path/with space/bin/mcp",
                    "args": ["arg with space", "--verbose"]
                }
            },
            "agents": {
                "gemini": {
                    "path": "gemini/test_settings.json",
                    "servers": {"my_server": {"inherit": "server with space"}}
                }
            }
        }
        
        # Create a temporary config file for gemini in the isolated home
        test_gemini_json = self.tmp_home / "gemini" / "test_settings.json"
        test_gemini_json.parent.mkdir(parents=True, exist_ok=True)
        test_gemini_json.write_text('{"mcpServers": {}}', encoding="utf-8")
        
        # Update path to be absolute for the test
        mock_config["agents"]["gemini"]["path"] = str(test_gemini_json)
        
        try:
            with patch.object(render_mcp_configs, "load_client_config", return_value=mock_config):
                with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
                    exit_code = render_mcp_configs.main()
                    self.assertEqual(exit_code, 0)
            
            # Verify result
            data = json.loads(test_gemini_json.read_text(encoding="utf-8"))
            cmd = data["mcpServers"]["my_server"]["command"]
            
            expected = shlex.join(["/path/with space/bin/mcp", "arg with space", "--verbose"])
            self.assertEqual(cmd, expected)
            self.assertNotIn("args", data["mcpServers"]["my_server"])
            
        finally:
            if test_gemini_json.exists():
                test_gemini_json.unlink()

if __name__ == "__main__":
    unittest.main()
