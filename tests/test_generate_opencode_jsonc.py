import importlib.util
from pathlib import Path


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
