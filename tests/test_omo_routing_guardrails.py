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


# Approved 2026-10-20 Personal table: do not turn OmO orchestration agents into Luna.
EXPECTED_PERSONAL = json.loads(r'''{"agents":{"sisyphus":{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code","fallback_models":["cloudflare-ai-gateway-custom/custom-sakura-ai/preview/Kimi-K2.7-Code","cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code"],"ultrawork":{"model":"openai/gpt-6.1-sol","reasoning":"high"}},"hephaestus":{"disable":false,"model":"openai/gpt-6.1-sol","reasoning":"high","fallback_models":[{"model":"cloudflare-ai-gateway-octg/gpt-6-sol","reasoning":"high"}]},"oracle":{"model":"openai/gpt-6.1-sol","reasoning":"xhigh","fallback_models":[{"model":"cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro","reasoning":"high"}]},"librarian":{"model":"openai/gpt-6-luna","reasoning":"low","fallback_models":[{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"low"}]},"explore":{"model":"openai/gpt-6-luna","reasoning":"low","fallback_models":[{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"low"}]},"multimodal-looker":{"model":"openai/gpt-6.1-sol","reasoning":"low","fallback_models":[{"model":"cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro","reasoning":"high"}]},"justice-review-controller":{"model":"openai/gpt-6.1-sol","reasoning":"high"},"justice-review-worker":{"model":"openai/gpt-6.1-sol","reasoning":"high"},"prometheus":{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code","fallback_models":["cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code"]},"metis":{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code","fallback_models":["cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code"]},"momus":{"model":"cloudflare-ai-gateway-octg/gpt-5.6-terra","reasoning":"high","fallback_models":[{"model":"openai/gpt-6.1-sol","reasoning":"xhigh"}]},"atlas":{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code","fallback_models":["cloudflare-ai-gateway-custom/custom-sakura-ai/preview/Kimi-K2.7-Code","cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code"]}},"categoryChains":{"sp-mechanical":[{"model":"openai/gpt-6-luna","reasoning":"low"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"low"}],"sp-implementation":[{"model":"openai/gpt-6-luna","reasoning":"max"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/glm-5.3-flash","reasoning":"high"},{"model":"openai/gpt-6.1-sol","reasoning":"high"},{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/glm-5.3-flash","reasoning":"high"}],"sp-integration":[{"model":"openai/gpt-6-luna","reasoning":"max"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/glm-5.3-flash","reasoning":"high"},{"model":"openai/gpt-6.1-sol","reasoning":"high"},{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/glm-5.3-flash","reasoning":"high"}],"sp-deep":[{"model":"cloudflare-ai-gateway-octg/gpt-5.6-terra","reasoning":"high"},{"model":"openai/gpt-6.1-sol","reasoning":"high"}],"sp-architecture":[{"model":"openai/gpt-6-luna","reasoning":"max"},{"model":"openai/gpt-6.1-sol","reasoning":"max"},{"model":"cloudflare-ai-gateway-octg/gpt-5.6-terra","reasoning":"high"}],"sp-review":[{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"max"},{"model":"openai/gpt-6.1-sol","reasoning":"high"},{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/deepseek-v4.1-flash","reasoning":"max"}],"sp-final-review":[{"model":"openai/gpt-6.1-sol","reasoning":"max"}],"ultrabrain":[{"model":"openai/gpt-6.1-sol","reasoning":"max"},{"model":"cloudflare-ai-gateway-octg/gpt-5.6-terra","reasoning":"high"}],"deep":[{"model":"openai/gpt-6.1-sol","reasoning":"high"},{"model":"cloudflare-ai-gateway-octg/gpt-5.6-terra","reasoning":"high"}],"quick":[{"model":"openai/gpt-6-luna","reasoning":"low"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"low"}],"writing":[{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code"},{"model":"cloudflare-ai-gateway-custom/custom-sakura-ai/preview/Kimi-K2.7-Code"},{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code"}],"unspecified-low":[{"model":"openai/gpt-6-luna","reasoning":"medium"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/deepseek-v4.1-flash","reasoning":"low"}],"unspecified-high":[{"model":"openai/gpt-6-luna","reasoning":"max"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code"},{"model":"openai/gpt-6.1-sol","reasoning":"high"},{"model":"cloudflare-ai-gateway-custom/custom-opencode-go/kimi-k2.7-code"}],"visual-engineering":[{"model":"cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro","reasoning":"high"},{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code"},{"model":"openai/gpt-6-luna","reasoning":"max"}],"artistry":[{"model":"cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code"},{"model":"cloudflare-ai-gateway-custom/custom-sakura-ai/preview/Kimi-K2.7-Code"},{"model":"cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro","reasoning":"high"}]},"justice":"openai/gpt-6.1-sol"}''')

def test_personal_agent_routes_exact():
    config = roots(load_config())["personal"]
    assert config["agents"] == EXPECTED_PERSONAL["agents"]
    assert "sisyphus-junior" not in config["agents"]

def test_personal_category_routes_exact():
    categories = roots(load_config())["personal"]["categories"]
    assert set(categories) == set(EXPECTED_PERSONAL["categoryChains"])
    for name, chain in EXPECTED_PERSONAL["categoryChains"].items():
        assert categories[name]["model"] == chain[0]["model"], name
        assert categories[name]["models"] == chain, name
        assert categories[name]["fallback_models"] == chain[1:], name

def test_no_octg_standard_category_primary_or_review_fallback():
    config = roots(load_config())["personal"]
    for name, category in config["categories"].items():
        assert not category["model"].startswith("cloudflare-ai-gateway-octg/gpt-6-"), name
    assert config["categories"]["sp-final-review"]["fallback_models"] == []
    assert config["command"]["justice-review-gate"]["model"] == EXPECTED_PERSONAL["justice"]
