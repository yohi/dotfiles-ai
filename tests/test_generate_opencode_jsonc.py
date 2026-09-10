import importlib.util
from pathlib import Path

import yaml


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "_scripts" / "generate-opencode-jsonc.py"
SPEC = importlib.util.spec_from_file_location("generate_opencode_jsonc", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_opencode_jsonc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_opencode_jsonc)


def test_apply_generated_fields_synchronizes_all_generated_values() -> None:
    current = {
        "mcp": {"old": {"enabled": False}},
        "agent": {"old": {"model": "old"}},
        "provider": {"old": {"name": "old"}},
        "enabled_providers": ["old"],
        "unrelated": "preserved",
    }
    config = {
        "mcp": {"new": {"enabled": True}},
        "agent": {"new": {"model": "new"}},
        "provider": {"new": {"name": "new"}},
        "enabled_providers": ["new"],
    }

    generate_opencode_jsonc._apply_generated_fields(current, config)

    assert current["mcp"] == config["mcp"]
    assert current["agent"] == config["agent"]
    assert current["provider"] == config["provider"]
    assert current["enabled_providers"] == config["enabled_providers"]
    assert current["unrelated"] == "preserved"


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
