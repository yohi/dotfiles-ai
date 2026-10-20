"""OmO routing invariants on top of the curated provider catalog."""
import json
import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "opencode" / "omo.jsonc"

def load_config():
    raw = CONFIG.read_text(encoding="utf-8")
    out, i = [], 0
    quoted = escape = line = block = False
    while i < len(raw):
        c, n = raw[i], raw[i + 1] if i + 1 < len(raw) else ""
        if line:
            if c == "\n":
                line = False
                out.append(c)
            i += 1
            continue
        if block:
            if c == "*" and n == "/":
                block = False
                i += 2
            else:
                i += 1
            continue
        if quoted:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                quoted = False
            i += 1
            continue
        if c == '"':
            quoted = True
            out.append(c)
            i += 1
            continue
        if c == "/" and n == "/":
            line = True
            i += 2
            continue
        if c == "/" and n == "*":
            block = True
            i += 2
            continue
        out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))

def roots(config):
    return {
        "personal": config["[opencode]"],
        "work": config["profiles"]["work"]["[opencode]"],
    }

def test_category_primary_and_fallback_mirror():
    for profile, cfg in roots(load_config()).items():
        for name, category in cfg["categories"].items():
            assert category["model"] == category["models"][0]["model"], (profile, name)
            assert category["fallback_models"] == category["models"][1:], (profile, name)

def test_work_is_bedrock_only():
    work = roots(load_config())["work"]
    for name, category in work["categories"].items():
        assert category["model"].startswith("amazon-bedrock/"), name
        assert all(x["model"].startswith("amazon-bedrock/") for x in category["fallback_models"]), name
    for name, agent in work["agents"].items():
        if agent.get("model"):
            assert agent["model"].startswith("amazon-bedrock/"), name
    assert work["command"]["justice-review-gate"]["model"].startswith("amazon-bedrock/")

def test_suspended_or_temporary_models_are_not_automatically_routed():
    for profile, cfg in roots(load_config()).items():
        names = []
        for agent in cfg["agents"].values():
            if agent.get("model"):
                names.append(agent["model"])
            names.extend(x if isinstance(x, str) else x["model"] for x in agent.get("fallback_models", []))
        for cat in cfg["categories"].values():
            names.extend(x if isinstance(x, str) else x["model"] for x in cat["models"])
        assert not any("custom-command-code/" in x for x in names), profile
        assert not any(x.startswith("opencode/") and x.endswith("-free") for x in names), profile
        assert not any(x.endswith("/glm-5.3") for x in names), profile

def test_justice_pins_are_preserved():
    cfg = roots(load_config())
    for root, pinned in (
        (cfg["personal"], "openai/gpt-6.1-sol"),
        (cfg["work"], "amazon-bedrock/global.anthropic.claude-opus-5-5"),
    ):
        assert root["agents"]["justice-review-controller"]["model"] == pinned
        assert root["agents"]["justice-review-worker"]["model"] == pinned
        assert root["command"]["justice-review-gate"]["model"] == pinned
