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

    def test_load_client_config(self):
        # Testing if it returns a dict (might be empty if file doesn't exist)
        self.assertIsInstance(self.config, dict)

    def test_replace_placeholders(self):
        data = {
            "url": "__GATEWAY_URL__",
            "home": "__HOME__",
            "repo": "__REPO_ROOT__",
            "env": "${TEST_VAR:-default}"
        }
        import os
        os.environ["TEST_VAR"] = "value"
        try:
            expanded = render_mcp_configs.replace_placeholders(data, self.gateway_url)
            self.assertEqual(expanded["url"], self.gateway_url)
            self.assertEqual(expanded["env"], "value")
            self.assertTrue(len(expanded["home"]) > 0)
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_replace_placeholders_with_expansion(self):
        # Testing path expansion
        data = "~/test/path"
        with patch.object(render_mcp_configs, "Path") as mock_path:
            mock_path.return_value.expanduser.return_value.resolve.return_value = "/home/user/test/path"
            expanded = render_mcp_configs.replace_placeholders(data, self.gateway_url, expand_paths=True)
            self.assertEqual(str(expanded), "/home/user/test/path")

    def test_deploy_systemd_service(self):
        src_file = self.tmp_home / "test.service"
        src_file.write_text("root: __REPO_ROOT__\nservers: __ENABLED_SERVERS__", encoding="utf-8")
        
        dest_dir = self.tmp_home / "dest"
        
        render_mcp_configs.deploy_systemd_service(
            src_file, dest_dir, "/repo", "srv1,srv2"
        )
        
        dest_file = dest_dir / "test.service"
        self.assertTrue(dest_file.exists())
        content = dest_file.read_text(encoding="utf-8")
        self.assertIn("root: /repo", content)
        self.assertIn("servers: srv1,srv2", content)

    def test_guards(self):
        # 1. Test when 'agents' is not a dict
        mock_config = {"defaults": {}, "servers": {}, "agents": ["not a dict"]}
        fake_repo = self.tmp_home / "fake_repo"
        mcp_dir = fake_repo / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "docker-mcp-gateway.service").write_text("", encoding="utf-8")
        (mcp_dir / "mcp-watchdog.service").write_text("", encoding="utf-8")
        
        with patch.object(render_mcp_configs, "load_client_config", return_value=mock_config):
            with patch.object(render_mcp_configs, "deploy_systemd_service"):
                with patch.object(render_mcp_configs.Path, "home", return_value=self.tmp_home):
                    with patch.object(render_mcp_configs.Path, "resolve") as mock_resolve:
                        mock_resolve.side_effect = [
                            fake_repo / "_scripts" / "script.py", # for repo_root in main
                            fake_repo / "config_path" # for config_path.exists() check
                        ]
                        from io import StringIO
                        with patch("sys.stdout", new=StringIO()) as fake_out:
                            exit_code = render_mcp_configs.main()
                            self.assertEqual(exit_code, 1)
                            self.assertIn("must be a mapping", fake_out.getvalue())

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
        
        fake_repo = self.tmp_home / "fake_repo"
        mcp_dir = fake_repo / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "docker-mcp-gateway.service").write_text("", encoding="utf-8")
        (mcp_dir / "mcp-watchdog.service").write_text("", encoding="utf-8")
        
        test_gemini_json = self.tmp_home / "gemini" / "test_settings.json"
        test_gemini_json.parent.mkdir(parents=True, exist_ok=True)
        test_gemini_json.write_text('{"mcpServers": {}}', encoding="utf-8")
        
        # Update path to be absolute for the test
        mock_config["agents"]["gemini"]["path"] = str(test_gemini_json)
        
        try:
            with patch.object(render_mcp_configs, "load_client_config", return_value=mock_config):
                with patch.object(render_mcp_configs, "deploy_systemd_service"):
                    with patch.object(render_mcp_configs, "Path", wraps=Path) as mock_path:
                        mock_path.home.return_value = self.tmp_home
                        with patch.object(render_mcp_configs.Path, "resolve") as mock_resolve:
                            mock_resolve.side_effect = [
                                fake_repo / "_scripts" / "render-mcp-configs.py", # main: repo_root
                                test_gemini_json, # replace_placeholders: expand_paths=True
                                test_gemini_json  # config_path = repo_root / path_str
                            ]
                            exit_code = render_mcp_configs.main()
                            self.assertEqual(exit_code, 0)
            
            data = json.loads(test_gemini_json.read_text(encoding="utf-8"))
            cmd = data["mcpServers"]["my_server"]["command"]
            expected = shlex.join(["/path/with space/bin/mcp", "arg with space", "--verbose"])
            self.assertEqual(cmd, expected)
            
        finally:
            if test_gemini_json.exists():
                test_gemini_json.unlink()

if __name__ == "__main__":
    unittest.main()
