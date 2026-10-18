"""Personal routing provider policy and free-model activation gates.

This is an offline configuration test: it does not verify any live API,
billing, privacy, or model capability.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
APM = yaml.safe_load((ROOT / "apm.yml").read_text(encoding="utf-8"))


def _parse_jsonc(source: str) -> dict:
    output: list[str] = []
    in_string = escaped = in_comment = False
    pos = 0
    while pos < len(source):
        ch = source[pos]
        if in_comment:
            if ch == "\n":
                output.append(ch)
                in_comment = False
        elif in_string:
            output.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            output.append(ch)
        elif source[pos:pos + 2] == "//":
            in_comment = True
            pos += 1
        else:
            output.append(ch)
        pos += 1
    cleaned = re.sub(r",\s*([}\]])", r"\1", "".join(output))
    return json.loads(cleaned)


OMO = _parse_jsonc(
    (ROOT / "opencode" / "omo.jsonc").read_text(encoding="utf-8")
)
PERSONAL = OMO["[opencode]"]
WORK = OMO["profiles"]["work"]["[opencode]"]
ALLOWED_AUTO_PREFIXES = (
    "openai/",
    "cloudflare-ai-gateway-octg/",
    "cloudflare-ai-gateway/google-ai-studio/",
    "cloudflare-ai-gateway-custom/custom-ollama-cloud/",
    "cloudflare-ai-gateway-custom/custom-opencode-go/",
    "cloudflare-ai-gateway-custom/custom-sakura-ai/",
)
BLOCKED_AUTO_TOKENS = (
    "custom-command-code/",
    "custom-aihubmix/",
    "custom-zenmax/",
    "custom-token-router/",
    "custom-nvidia/",
    "custom-opencode-free/",
    "cloudflare-ai-gateway-opencode-free/",
    "opencode/glm-5.3-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "longcat-2.5-preview-free",
    "beam-free",
)


def _models_in(value: object) -> list[str]:
    """Collect full model IDs from agent/category route records only."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "model" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_models_in(child))
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str) and "/" in child:
                found.append(child)
            else:
                found.extend(_models_in(child))
    return found


def test_native_console_free_catalog_is_direct_and_never_auto() -> None:
    assert "opencode" in APM["enabled_providers"]
    assert OMO["models"]["glm-53-flash-opencode-free"]["model"] == (
        "opencode/glm-5.3-flash-free"
    )
    assert OMO["models"]["deepseek-v41-opencode-free"]["model"] == (
        "opencode/deepseek-v4.1-flash-free"
    )
    # Console Free must not be a Cloudflare custom/provider entry.
    assert not any(
        "opencode-free" in model for model in APM["provider"]
    )
    automatic = json.dumps({
        "agents": PERSONAL["agents"],
        "categories": PERSONAL["categories"],
        "command": PERSONAL["command"],
    })
    assert "opencode/glm-5.3-flash-free" not in automatic
    assert "opencode/deepseek-v4.1-flash-free" not in automatic


def test_go_free_candidates_are_catalog_only() -> None:
    models = APM["provider"]["cloudflare-ai-gateway-custom"]["models"]
    expected = {
        "longcat-25-go-free": "custom-opencode-go/longcat-2.5-preview-free",
        "beam-go-free": "custom-opencode-go/beam-free",
    }
    for alias, go_id in expected.items():
        assert go_id in models
        assert OMO["models"][alias]["model"] == "cloudflare-ai-gateway-custom/" + go_id
        assert go_id not in json.dumps(PERSONAL)


def test_personal_auto_routes_are_only_approved_providers() -> None:
    model_ids = _models_in({
        "agents": PERSONAL["agents"],
        "categories": PERSONAL["categories"],
        "command": PERSONAL["command"],
    })
    assert model_ids
    assert all(m.startswith(ALLOWED_AUTO_PREFIXES) for m in model_ids)
    for model in model_ids:
        assert not any(token in model for token in BLOCKED_AUTO_TOKENS)
        # Exclude full GLM without falsely excluding GLM-5.3 Flash.
        assert not model.endswith("/glm-5.3")
    # GLM-5.3 full remains selectable manually but is never routed automatically.
    assert OMO["models"]["glm-53"]["model"].endswith("/glm-5.3")


def test_personal_category_fallback_mirror() -> None:
    for name, category in PERSONAL["categories"].items():
        assert category["models"], name
        assert category["model"] == category["models"][0]["model"], name
        assert category["fallback_models"] == category["models"][1:], name


def test_sakura_and_google_stay_in_personal_routes() -> None:
    agents = PERSONAL["agents"]
    categories = PERSONAL["categories"]
    assert agents["multimodal-looker"]["model"] == (
        "cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro"
    )
    assert categories["writing"]["model"].startswith(
        "cloudflare-ai-gateway-custom/custom-sakura-ai/"
    )
    assert categories["visual-engineering"]["model"].startswith(
        "cloudflare-ai-gateway/google-ai-studio/"
    )
    assert categories["artistry"]["model"].startswith(
        "cloudflare-ai-gateway/google-ai-studio/"
    )


def test_justice_review_categories_stay_active() -> None:
    for name in ("sp-review", "sp-final-review"):
        assert PERSONAL["categories"][name]["models"]
        assert PERSONAL["categories"][name]["fallback_models"]
        assert WORK["categories"][name]["models"]
        assert WORK["categories"][name]["fallback_models"]


def test_work_keeps_bedrock_only() -> None:
    assert OMO["profiles"]["personal"] == {}
    for model in _models_in({
        "models": WORK["models"],
        "agents": WORK["agents"],
        "categories": WORK["categories"],
        "command": WORK["command"],
    }):
        assert model.startswith("amazon-bedrock/"), model
