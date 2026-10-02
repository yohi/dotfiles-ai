import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "_scripts" / "generate-claude-settings.py"
SPEC = importlib.util.spec_from_file_location("generate_claude_settings", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_claude = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_claude)


def test_build_mcp_servers_resolves_relative_cwd_to_repository_root() -> None:
    servers = generate_claude.build_mcp_servers(
        {
            "dependencies": {
                "mcp": [
                    {
                        "name": "codegraph",
                        "transport": "stdio",
                        "command": "_scripts/codegraph-bootstrap.sh",
                        "args": ["serve", "--mcp"],
                        "cwd": ".",
                    }
                ]
            }
        }
    )

    assert servers["codegraph"]["cwd"] == str(PROJECT_ROOT)


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


def test_main_does_not_create_project_root_claude_settings(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "apm.yml").write_text(
        "dependencies:\n  mcp: []\n", encoding="utf-8"
    )

    generate_claude.main()

    assert not (tmp_path / ".claude.json").exists()
    assert (tmp_path / "claude" / "settings.json").exists()
