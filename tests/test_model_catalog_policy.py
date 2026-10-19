"""Regression checks for the curated OpenCode model catalog."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def test_curated_console_free_models() -> None:
    cfg = yaml.safe_load((ROOT / "apm.yml").read_text())
    assert set(cfg["provider"]["opencode"]["whitelist"]) == {
        "glm-5.3-flash-free", "deepseek-v4.1-flash-free",
        "minimax-m3.1-flash-free", "longcat-2.5-preview-free",
    }
    assert set(cfg["provider"]["opencode-go"]["whitelist"]) == {
        "kimi-k2.7-code", "kimi-k3", "glm-5.3-flash",
        "deepseek-v4.1-flash", "longcat-2.5-preview-free",
        "minimax-m3.1-flash-free", "beam-free",
    }
    assert "cloudflare-ai-gateway-dynamic" not in cfg["enabled_providers"]

def test_unwanted_custom_catalogs_are_absent() -> None:
    cfg = yaml.safe_load((ROOT / "apm.yml").read_text())
    names = cfg["provider"]["cloudflare-ai-gateway-custom"]["models"]
    forbidden = ("custom-aihubmix/", "custom-zenmax/", "custom-token-router/",
                 "custom-nvidia/", "custom-command-code/")
    assert not any(k.startswith(forbidden) for k in names)
    assert "custom-ollama-cloud/glm-5.3" in names

def test_free_models_are_manual_only() -> None:
    text = (ROOT / "opencode/omo.jsonc").read_text()
    head, catalog = text.split('  "models": {', 1)
    for model in ("glm-5.3-flash-free", "deepseek-v4.1-flash-free",
                  "minimax-m3.1-flash-free", "longcat-2.5-preview-free"):
        assert '"model": "opencode/' + model + '"' in catalog
        assert '"model": "opencode/' + model + '"' not in head
