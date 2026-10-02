import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "_scripts" / "generate-claude-settings.py"
SPEC = importlib.util.spec_from_file_location("generate_claude_settings", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_settings)


def test_stdio_server_resolves_relative_command_with_repository_cwd() -> None:
    servers = generate_settings.build_mcp_servers(
        {
            "dependencies": {
                "mcp": [
                    {
                        "name": "relative-path",
                        "command": "./_scripts/server",
                        "cwd": ".",
                    },
                    {
                        "name": "bare-command",
                        "command": "uvx",
                        "cwd": ".",
                    },
                    {
                        "name": "absolute-command",
                        "command": "/usr/bin/python",
                        "cwd": ".",
                    },
                ]
            }
        }
    )

    assert servers["relative-path"]["command"] == str(PROJECT_ROOT / "_scripts/server")
    assert servers["bare-command"]["command"] == "uvx"
    assert servers["absolute-command"]["command"] == "/usr/bin/python"
    assert all(server["cwd"] == str(PROJECT_ROOT) for server in servers.values())
