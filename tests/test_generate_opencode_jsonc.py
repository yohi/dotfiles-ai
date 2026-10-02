import importlib.util
from pathlib import Path

import yaml


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "_scripts" / "generate-opencode-jsonc.py"
SPEC = importlib.util.spec_from_file_location("generate_opencode_jsonc", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_opencode_jsonc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_opencode_jsonc)


def test_main_does_not_rewrite_project_root_opencode_config(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path
    output = repo_root / "opencode" / "opencode.jsonc"
    output.parent.mkdir()
    output.write_text("{}\n", encoding="utf-8")
    project_config = repo_root / "opencode.json"
    original_config = '{"mcp":{"local-only":{"enabled":false}}}\n'
    project_config.write_text(original_config, encoding="utf-8")
    (repo_root / "apm.yml").write_text(
        "dependencies:\n  mcp: []\n", encoding="utf-8"
    )
    monkeypatch.setattr(generate_opencode_jsonc, "REPO_ROOT", repo_root)
    monkeypatch.setattr(generate_opencode_jsonc, "APM_YML", repo_root / "apm.yml")
    monkeypatch.setattr(generate_opencode_jsonc, "OUTPUT", output)

    generate_opencode_jsonc.main()

    assert project_config.read_text(encoding="utf-8") == original_config


def test_build_config_skips_registry_string_mcp_entries() -> None:
    config = generate_opencode_jsonc.build_config(
        {
            "dependencies": {
                "mcp": [
                    "com.atlassian/atlassian-mcp-server",
                    {"name": "codegraph", "command": "codegraph"},
                ]
            }
        }
    )

    assert set(config["mcp"]) == {"codegraph"}


def test_convert_mcp_entry_keeps_opencode_env_syntax_for_filesystem_path() -> None:
    _, converted = generate_opencode_jsonc._convert_mcp_entry(
        {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "${env:PWD}"],
        }
    )

    assert converted["command"][-1] == "{env:PWD}"


def test_build_config_uses_python_313_for_semgrep() -> None:
    apm = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "apm.yml").read_text(encoding="utf-8")
    )
    config = generate_opencode_jsonc.build_config(apm)
    converted = config["mcp"]["semgrep"]

    assert converted["command"] == [
        "uvx",
        "--python",
        "3.13",
        "semgrep-mcp",
        "-t",
        "stdio",
        "--semgrep-path",
        "{env:HOME}/.local/bin/semgrep",
    ]


def test_build_config_resolves_codegraph_cwd_to_repository_root() -> None:
    apm = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "apm.yml").read_text(encoding="utf-8")
    )
    config = generate_opencode_jsonc.build_config(apm)

    assert config["mcp"]["codegraph"]["cwd"] == str(
        Path(__file__).resolve().parents[1]
    )


def test_build_config_uses_native_superpowers_plugin() -> None:
    apm = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "apm.yml").read_text(encoding="utf-8")
    )
    config = generate_opencode_jsonc.build_config(apm)

    assert "superpowers@git+https://github.com/obra/superpowers.git#v6.4.2" in config["plugin"]
    assert config["instructions"] == ["global-rules/AGENTS.global.md"]
