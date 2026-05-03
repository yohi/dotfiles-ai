#!/usr/bin/env python3
import importlib.util
import sys
import unittest
import tempfile
import os
import json
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
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_home = Path(self.tmp_dir.name)

        # Create a fake repo structure
        self.fake_repo = (self.tmp_home / "fake_repo").resolve()
        self.fake_repo.mkdir(parents=True, exist_ok=True)
        # Create a dummy script file to make resolve() happy
        (self.fake_repo / "_scripts").mkdir(parents=True, exist_ok=True)
        (self.fake_repo / "_scripts" / "render-mcp-configs.py").write_text(
            "", encoding="utf-8"
        )

        self.mcp_dir = self.fake_repo / "mcp"
        self.mcp_dir.mkdir(parents=True, exist_ok=True)
        (self.mcp_dir / "catalogs").mkdir(parents=True, exist_ok=True)
        (self.mcp_dir / "docker-mcp-gateway.service").write_text("", encoding="utf-8")
        (self.mcp_dir / "mcp-watchdog.service").write_text("", encoding="utf-8")

    def robust_mock_path(self, *args):
        if not args:
            return Path(".")
        p_str = str(args[0])
        if "render-mcp-configs.py" in p_str:
            return self.fake_repo / "_scripts" / "render-mcp-configs.py"
        return Path(*args)

    def test_load_client_config(self):
        config = render_mcp_configs.load_client_config()
        self.assertIsInstance(config, dict)

    def test_replace_placeholders(self):
        data = {
            "url": "__GATEWAY_URL__",
            "home": "__HOME__",
            "repo": "__REPO_ROOT__",
            "env": "${TEST_VAR:-default}",
        }
        os.environ["TEST_VAR"] = "value"
        try:
            expanded = render_mcp_configs.replace_placeholders(data, self.gateway_url)
            self.assertEqual(expanded["url"], self.gateway_url)
            self.assertEqual(expanded["env"], "value")
            self.assertTrue(len(expanded["home"]) > 0)
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_deploy_systemd_service(self):
        src_file = self.tmp_home / "test.service"
        src_file.write_text(
            "root: __REPO_ROOT__\nservers: __ENABLED_SERVERS__", encoding="utf-8"
        )
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
        mock_config = {
            "config": {"defaults": {}, "agents": ["not a dict"]},
            "dependencies": {"mcp_servers": []},
        }

        with patch.object(
            render_mcp_configs, "load_client_config", return_value=mock_config
        ):
            with patch.object(render_mcp_configs, "deploy_systemd_service"):
                with patch.object(
                    render_mcp_configs.Path, "home", return_value=self.tmp_home
                ):
                    with patch.object(
                        render_mcp_configs, "Path", side_effect=self.robust_mock_path
                    ) as MockPath:
                        MockPath.home.return_value = self.tmp_home
                        exit_code = render_mcp_configs.main()
                        self.assertEqual(exit_code, 0)

    def test_gemini_command_quoting(self):
        mock_config = {
            "config": {
                "defaults": {"gateway_url": "http://localhost:10888/sse"},
                "agents": {
                    "gemini": {
                        "path": "gemini/test_settings.json",
                        "servers": {
                            "my_server": {"inherit": "server with space"},
                            "auth_server": {"inherit": "secure_server"},
                        },
                    },
                    "opencode": {
                        "path": "opencode/opencode.jsonc",
                        "format": "opencode_jsonc",
                        "servers": {"auth_server": {"inherit": "secure_server"}},
                    },
                },
            },
            "dependencies": {
                "mcp_servers": [
                    {
                        "name": "server with space",
                        "type": "local",
                        "command": "/path/with space/bin/mcp",
                        "args": ["arg with space", "--verbose"],
                    },
                    {
                        "name": "secure_server",
                        "type": "sse",
                        "url": "http://secure/sse",
                        "headers": {"Authorization": "Bearer __AUTH_TOKEN__"},
                    },
                ]
            },
        }

        # Create config files in fake_repo
        fake_gemini_json = self.fake_repo / "gemini" / "test_settings.json"
        fake_gemini_json.parent.mkdir(parents=True, exist_ok=True)
        fake_gemini_json.write_text('{"mcpServers": {}}', encoding="utf-8")

        fake_opencode_json = self.fake_repo / "opencode" / "opencode.jsonc"
        fake_opencode_json.parent.mkdir(parents=True, exist_ok=True)
        fake_opencode_json.write_text('{"mcpServers": {}}', encoding="utf-8")

        with patch.object(
            render_mcp_configs, "load_client_config", return_value=mock_config
        ):
            with patch.object(render_mcp_configs, "deploy_systemd_service"):
                with patch.object(
                    render_mcp_configs.Path, "home", return_value=self.tmp_home
                ):
                    with patch.object(
                        render_mcp_configs, "Path", side_effect=self.robust_mock_path
                    ) as MockPath:
                        MockPath.home.return_value = self.tmp_home
                        render_mcp_configs.main()

        # Check Gemini output
        gemini_data = json.loads(fake_gemini_json.read_text(encoding="utf-8"))
        self.assertEqual(
            gemini_data["mcpServers"]["auth_server"]["headers"]["Authorization"],
            "Bearer ${MCP_GATEWAY_TOKEN}",
        )
        self.assertIn("my_server", gemini_data["mcpServers"])
        url = gemini_data["mcpServers"]["my_server"]["url"]
        self.assertIn("http://localhost:10888/sse?server=my_server", url)

        # Check Opencode output
        opencode_data = json.loads(fake_opencode_json.read_text(encoding="utf-8"))
        self.assertEqual(
            opencode_data["mcpServers"]["auth_server"]["headers"]["Authorization"],
            "Bearer {env:MCP_GATEWAY_TOKEN}",
        )


if __name__ == "__main__":
    unittest.main()
