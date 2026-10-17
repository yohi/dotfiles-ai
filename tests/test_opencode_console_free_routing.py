"""Offline regression checks for opt-in OpenCode Console Free candidates.

No calls are made to Cloudflare, OpenCode Console, or other paid services.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
APM = yaml.safe_load((ROOT / "apm.yml").read_text(encoding="utf-8"))
OMO_SOURCE = (ROOT / "opencode" / "omo.jsonc").read_text(encoding="utf-8")
PROVIDER_ID = "cloudflare-ai-gateway-console-free"
UPSTREAM_IDS = {"glm-5.3-flash-free", "deepseek-v4.1-flash-free"}
ALIASES = {
    "glm-53-flash-console-free": PROVIDER_ID + "/glm-5.3-flash-free",
    "deepseek-v41-console-free": PROVIDER_ID + "/deepseek-v4.1-flash-free",
}


def _parse_jsonc(source: str) -> dict:
    """Strip // comments outside strings, then trailing commas."""
    chars: list[str] = []
    in_string = escaped = in_comment = False
    pos = 0
    while pos < len(source):
        ch = source[pos]
        if in_comment:
            if ch == "\n":
                chars.append(ch)
                in_comment = False
        elif in_string:
            chars.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            chars.append(ch)
        elif ch == "/" and source[pos : pos + 2] == "//":
            in_comment = True
            pos += 1
        else:
            chars.append(ch)
        pos += 1
    cleaned = re.sub(r",\s*([}\]])", r"\1", "".join(chars))
    return json.loads(cleaned)


OMO = _parse_jsonc(OMO_SOURCE)


def test_console_free_is_a_separate_provider() -> None:
    assert PROVIDER_ID in APM["enabled_providers"]
    assert PROVIDER_ID in APM["provider"]
    assert APM["provider"][PROVIDER_ID]["npm"] == "@ai-sdk/openai-compatible"
    assert "custom-opencode-go/" not in APM["provider"][PROVIDER_ID]["options"]["baseURL"]


def test_only_explicit_free_models_are_exposed() -> None:
    models = APM["provider"][PROVIDER_ID]["models"]
    assert set(models) == UPSTREAM_IDS
    assert all(name.endswith("-free") for name in models)
    assert "glm-5.3-flash" not in models
    assert "deepseek-v4.1-flash" not in models


def test_console_free_uses_correct_cloudflare_to_upstream_mapping() -> None:
    url = APM["provider"][PROVIDER_ID]["options"]["baseURL"]
    assert url == (
        "https://gateway.ai.cloudflare.com/v1/"
        "${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/"
        "custom-opencode-console-free/inference/openai/v1"
    )
    # When the Cloudflare Custom Provider base_url is https://opencode.ai,
    # this path maps to https://opencode.ai/inference/openai/v1/chat/completions.
    assert url.endswith("/custom-opencode-console-free/inference/openai/v1")


def test_no_upstream_billing_credentials_or_retry_fallback() -> None:
    options = APM["provider"][PROVIDER_ID]["options"]
    assert options["apiKey"] == ""
    headers = options["headers"]
    assert headers["Authorization"] == ""
    assert headers["cf-aig-authorization"] == "Bearer ${env:OC_CF_API_TOKEN}"
    assert headers["cf-aig-max-attempts"] == "1"
    assert headers["cf-aig-skip-cache"] == "true"
    assert headers["cf-aig-collect-log-payload"] == "false"


def test_free_candidates_are_opt_in_and_not_live_routing() -> None:
    aliases = OMO["models"]
    for name, model in ALIASES.items():
        assert aliases[name]["model"] == model

    core = OMO["[opencode]"]
    for name, agent in core["agents"].items():
        assert PROVIDER_ID not in json.dumps(agent), name
    for name, category in core["categories"].items():
        assert PROVIDER_ID not in json.dumps(category), name
        assert category["model"] == category["models"][0]["model"], name
        assert category["fallback_models"] == category["models"][1:], name
    assert PROVIDER_ID not in json.dumps(core["command"])


def test_no_regression_to_expensive_or_unavailable_routes() -> None:
    for name, category in OMO["[opencode]"]["categories"].items():
        models = [model["model"] for model in category["models"]]
        assert all("custom-command-code/" not in model for model in models), name
        assert all(not model.endswith("/glm-5.3") for model in models), name
    # GLM full remains available for explicit manual selection only.
    assert OMO["models"]["glm-53"]["model"].endswith("/glm-5.3")


def test_work_remains_bedrock_only() -> None:
    work = OMO["profiles"]["work"]["[opencode]"]
    for name, category in work["categories"].items():
        assert category["model"].startswith("amazon-bedrock/"), name
        if name.startswith("sp-"):
            assert category["fallback_models"] == category["models"][1:], name
        assert all(m["model"].startswith("amazon-bedrock/") for m in category["models"]), name
    for name, agent in work["agents"].items():
        assert PROVIDER_ID not in json.dumps(agent), name
    assert PROVIDER_ID not in json.dumps(work["command"])
