import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "_scripts" / "generate-claude-settings.py"
SPEC = importlib.util.spec_from_file_location("generate_claude_settings", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_claude = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_claude)


def test_build_mcp_servers_skips_registry_string_entries() -> None:
    servers = generate_claude.build_mcp_servers(
        {
            "dependencies": {
                "mcp": [
                    "com.atlassian/atlassian-mcp-server",
                    {
                        "name": "codegraph",
                        "command": "codegraph",
                        "args": ["serve", "--mcp"],
                    },
                ]
            }
        }
    )

    assert set(servers) == {"codegraph"}
