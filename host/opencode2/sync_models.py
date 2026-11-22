#!/usr/bin/env python3
"""Sync the V1-enabled provider/model catalog into the isolated OpenCode V2 Host."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import yaml

REPO = Path(__file__).resolve().parents[2]
# V1 enabled_providers is authoritative for Host V2 parity. Do not reuse the
# narrower opencode_v2.providers selection, which belongs to the OC2 Sandbox.
PROVIDERS = (
    "openai", "cloudflare-ai-gateway", "cloudflare-ai-gateway-custom",
    "cloudflare-ai-gateway-octg", "opencode", "ollama-cloud",
    "opencode-go", "amazon-bedrock", "google",
)
CUSTOM = "cloudflare-ai-gateway-custom"
UNIFIED = "cloudflare-ai-gateway"
OCTG = "cloudflare-ai-gateway-octg"
BUILTIN_WHITELIST = ("openai", "opencode", "opencode-go", "amazon-bedrock", "google")
SOURCE_URL = "https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat"
SOURCE_TOKEN = "Bearer ${env:OC_CF_API_TOKEN}"
OCTG_URL = "https://gateway.ai.cloudflare.com/v1/${env:OCTG_CF_ACCOUNT_ID}/${env:OCTG_CF_GATEWAY_ID}/custom-octg/v1"
OCTG_TOKEN = "Bearer ${env:OCTG_CF_API_TOKEN}"
MANAGED_KEYS = ("model", "providers", "policies")


def stop(message: str) -> None:
    raise RuntimeError(message)


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        stop(f"missing or unsafe JSON file: {path}")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        stop(f"JSON root must be an object: {path}")
    return result


def _str_list(value: object, label: str) -> list[str]:
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) or not item for item in value)
            or len(value) != len(set(value))):
        stop(f"{label} must be a unique list of nonempty strings")
    return value


def _variants(info: dict, name: str) -> dict:
    if not isinstance(info, dict) or not isinstance(info.get("name"), str):
        stop(f"invalid model metadata for {name}")
    if set(info) - {"name", "variants"}:
        stop(f"unrecognized source model fields for {name}")
    result = {"name": info["name"]}
    if "variants" not in info:
        return result
    variants = info["variants"]
    if not isinstance(variants, dict) or not variants:
        stop(f"invalid source model variants for {name}")
    entries = []
    for variant_id, fields in variants.items():
        if (not isinstance(variant_id, str) or not variant_id
                or not isinstance(fields, dict) or set(fields) - {"reasoningEffort", "body"}):
            stop(f"unrecognized model variant shape for {name}")
        if "reasoningEffort" in fields and fields["reasoningEffort"] not in {
                "none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            stop(f"unsupported reasoning effort in {name}")
        entry = {}
        if "reasoningEffort" in fields:
            entry["settings"] = {"reasoningEffort": fields["reasoningEffort"]}
        if "body" in fields:
            body = fields["body"]
            if (not isinstance(body, dict) or set(body) != {"thinking"}
                    or not isinstance(body["thinking"], dict)
                    or set(body["thinking"]) != {"type"}
                    or body["thinking"]["type"] not in {"enabled", "disabled"}):
                stop(f"unsupported model body in {name}")
            entry["body"] = body
        if variant_id == "default":
            result.update(entry)
        else:
            entries.append({"id": variant_id, **entry})
    if entries:
        result["variants"] = entries
    return result


def _catalog_models(info: dict, label: str) -> dict:
    raw = info.get("models")
    if not isinstance(raw, dict) or not raw:
        stop(f"missing configured models for {label}")
    if any(not isinstance(key, str) or not key for key in raw):
        stop(f"invalid model key in {label}")
    return {key: _variants(value, f"{label}/{key}") for key, value in raw.items()}


def _gateway_headers(options: dict, token: str, label: str) -> dict:
    headers = options.get("headers")
    if not isinstance(headers, dict):
        stop(f"missing {label} headers")
    required = {
        "Authorization": "",
        "cf-aig-authorization": token,
        "cf-aig-collect-log-payload": "true",
        "cf-aig-max-attempts": "1",
        "cf-aig-skip-cache": "true",
    }
    if headers != required:
        stop(f"{label} endpoint/authentication contract changed; manual review required")
    return {key: value.replace("${env:", "{env:") for key, value in headers.items()}


def _cloudflare_provider(catalog: dict, provider: str) -> dict:
    source = catalog.get(provider)
    if not isinstance(source, dict) or not isinstance(source.get("options"), dict):
        stop(f"missing {provider} catalog/options")
    options = source["options"]
    if provider == UNIFIED:
        expected = {"accountId": "${env:OC_CF_ACCOUNT_ID}",
                    "gatewayId": "${env:OC_CF_GATEWAY_ID}",
                    "apiKey": "${env:OC_CF_API_TOKEN}"}
        if source.get("npm") != "ai-gateway-provider" or options != expected:
            stop("Unified Cloudflare gateway contract changed; manual review required")
        # The V1 ai-gateway-provider package has no verified V2-native adapter;
        # use the documented generic /compat endpoint for the same model IDs.
        return {
            "name": "Cloudflare AI Gateway",
            "package": "@opencode/ai/providers/openai-compatible",
            "env": ["OC_CF_API_TOKEN"],
            "settings": {"baseURL": SOURCE_URL.replace("${env:", "{env:"),
                         "apiKey": "cloudflare-custom-provider"},
            "headers": {"Authorization": "", "cf-aig-authorization": SOURCE_TOKEN.replace("${env:", "{env:")},
            "models": _catalog_models(source, provider),
        }
    if provider == CUSTOM:
        if (source.get("npm") != "@ai-sdk/openai-compatible"
                or options.get("baseURL") != SOURCE_URL or options.get("apiKey") != ""
                or set(options) != {"baseURL", "apiKey", "headers"}):
            stop("Cloudflare Custom endpoint/authentication contract changed; manual review required")
        return {
            "name": source.get("name", "Cloudflare AI Gateway (Custom)"),
            "package": "@opencode/ai/providers/openai-compatible",
            "env": ["OC_CF_API_TOKEN"],
            "settings": {"baseURL": SOURCE_URL.replace("${env:", "{env:"),
                         "apiKey": "cloudflare-custom-provider"},
            "headers": _gateway_headers(options, SOURCE_TOKEN, provider),
            "models": _catalog_models(source, provider),
        }
    if provider == OCTG:
        if (source.get("npm") != "@ai-sdk/openai"
                or options.get("baseURL") != OCTG_URL
                or options.get("apiKey") != "cloudflare-custom-provider"
                or set(options) != {"apiKey", "baseURL", "headers"}):
            stop("Cloudflare OCTG endpoint/authentication contract changed; manual review required")
        return {
            "name": source.get("name", "Cloudflare AI Gateway (OCTG)"),
            "package": "@opencode/ai/providers/openai/responses",
            "env": ["OCTG_CF_API_TOKEN"],
            "settings": {"baseURL": OCTG_URL.replace("${env:", "{env:"),
                         "apiKey": "cloudflare-custom-provider"},
            "headers": _gateway_headers(options, OCTG_TOKEN, provider),
            "models": _catalog_models(source, provider),
        }
    stop(f"unknown Cloudflare provider: {provider}")


def expected_config() -> dict:
    source = REPO / "apm.yml"
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        stop("source apm.yml must be a regular file <= 2 MiB")
    try:
        root = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        stop(f"invalid source apm.yml: {exc}")
    if not isinstance(root, dict):
        stop("APM manifest is not a mapping")
    selected = root.get("opencode_v2")
    catalog = root.get("provider")
    if not isinstance(selected, dict) or not isinstance(catalog, dict):
        stop("APM V2 model selection or catalog missing")
    ids = _str_list(selected.get("allowed_models"), "opencode_v2.allowed_models")
    default = selected.get("default_model")
    if not isinstance(default, str) or default not in ids:
        stop("V2 default_model is absent from allowed_models")
    if selected.get("deny_provider_fallback") is not True or selected.get("deny_guest_auth") is not True:
        stop("V2 SSOT model safety requirements changed")
    # Sandbox selection remains independent and explicitly unchanged.
    declarations = selected.get("providers")
    if not isinstance(declarations, dict) or set(declarations) != {"openai", CUSTOM}:
        stop("unexpected Sandbox V2 provider selection")
    for provider, auth in (("openai", "docker_openai_oauth"), (CUSTOM, "docker_custom_secret")):
        item = declarations[provider]
        if not isinstance(item, dict) or item.get("enabled") is not True or item.get("auth_method") != auth:
            stop(f"unexpected Sandbox SSOT provider setting: {provider}")
    enabled = _str_list(root.get("enabled_providers"), "enabled_providers")
    if set(enabled) != set(PROVIDERS) or len(enabled) != len(PROVIDERS):
        stop("Host V2 provider parity scope changed; explicit owner decision required")
    builtins = {}
    for provider in BUILTIN_WHITELIST:
        item = catalog.get(provider)
        if not isinstance(item, dict):
            stop(f"missing built-in provider catalog: {provider}")
        ids_for_provider = _str_list(item.get("whitelist"), f"provider.{provider}.whitelist")
        builtins[provider] = {"models": {key: {"modelID": key} for key in ids_for_provider}}
    for model in ids:
        provider, sep, name = model.partition("/")
        if not sep or provider not in ("openai", CUSTOM):
            stop(f"unapproved Sandbox model: {model}")
        if provider == "openai" and name not in builtins["openai"]["models"]:
            stop(f"V2 model missing from OpenAI catalog: {model}")
        if provider == CUSTOM:
            custom_catalog = catalog.get(CUSTOM)
            if not isinstance(custom_catalog, dict) or name not in custom_catalog.get("models", {}):
                stop(f"V2 model missing from Custom provider catalog: {model}")
    providers = dict(builtins)
    providers["ollama-cloud"] = {}  # Native V2 catalog; V1 does not define a whitelist.
    for provider in (UNIFIED, CUSTOM, OCTG):
        providers[provider] = _cloudflare_provider(catalog, provider)
    return {
        "model": default,
        "providers": providers,
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            *({"action": "provider.use", "resource": p, "effect": "allow"} for p in enabled),
        ],
    }


def target(home: Path) -> tuple[Path, Path]:
    directory = home / ".config/opencode-v2/opencode"
    if not directory.is_dir() or directory.is_symlink():
        stop("Host V2 configuration directory missing or unsafe")
    return directory / "opencode.json", directory / "model-host-sync-state.json"


def preflight(home: Path, expected: dict) -> tuple[dict, Path, Path]:
    config_path, state_path = target(home)
    current = json_file(config_path)
    prior = json_file(state_path) if state_path.exists() or state_path.is_symlink() else None
    existing = {key: current.get(key) for key in MANAGED_KEYS if key in current}
    if prior is None:
        if existing and existing != expected:
            stop("unmanaged V2 model/provider/policy settings already exist; refusing overwrite")
    elif fingerprint(existing) != prior.get("managed_sha256"):
        stop("Host V2 model/provider/policy settings changed after last sync; refusing overwrite")
    return current, config_path, state_path


def atomic_json(path: Path, data: dict) -> None:
    fd, temp = tempfile.mkstemp(prefix=".model-host-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true", help="read-only SSOT and target checks")
    actions.add_argument("--apply", action="store_true", help="write Host V2 model settings only")
    args = parser.parse_args(argv)
    home = Path(os.environ.get("HOME", ""))
    if not home.is_absolute() or not home.is_dir():
        stop("HOME must be an existing absolute directory")
    expected = expected_config()
    current, config_path, state_path = preflight(home, expected)
    print(f"Host V2 model={expected['model']}; providers={len(expected['providers'])}; "
          f"custom models={len(expected['providers'][CUSTOM]['models'])}")
    if args.check:
        print("CHECK_ONLY: Host V2 settings are compatible; no changes made")
        return 0
    updated = {**current, **expected}
    state = {"source": "apm.yml:opencode_v2", "managed_sha256": fingerprint(expected)}
    atomic_json(config_path, updated)
    atomic_json(state_path, state)
    print("Host V2 provider/model parity configured. Separate authentication is required for each provider; no credentials were copied.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MODEL_HOST_V2_STOP: {exc}", file=sys.stderr)
        sys.exit(1)
