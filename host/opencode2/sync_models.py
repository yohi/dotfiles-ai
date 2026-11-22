#!/usr/bin/env python3
"""Sync the selected APM SSOT models into the isolated OpenCode V2 host config."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import yaml

REPO = Path(__file__).resolve().parents[2]
PROVIDERS = ("openai", "cloudflare-ai-gateway-custom")
CUSTOM = "cloudflare-ai-gateway-custom"
SOURCE_URL = "https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat"
SOURCE_TOKEN = "Bearer ${env:OC_CF_API_TOKEN}"
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
    ids = selected.get("allowed_models")
    default = selected.get("default_model")
    if not (isinstance(ids, list) and ids and all(isinstance(x, str) for x in ids)
            and len(ids) == len(set(ids)) and isinstance(default, str) and default in ids):
        stop("invalid V2 allowed_models or default_model")
    if selected.get("deny_provider_fallback") is not True or selected.get("deny_guest_auth") is not True:
        stop("V2 SSOT model safety requirements changed")
    declarations = selected.get("providers")
    if not isinstance(declarations, dict) or set(declarations) != set(PROVIDERS):
        stop("unexpected V2 provider selection")
    for provider, auth in (("openai", "docker_openai_oauth"), (CUSTOM, "docker_custom_secret")):
        config = declarations[provider]
        if not isinstance(config, dict) or config.get("enabled") is not True or config.get("auth_method") != auth:
            stop(f"unexpected SSOT provider setting: {provider}")
    for model in ids:
        provider, sep, name = model.partition("/")
        if not sep or not name or provider not in PROVIDERS:
            stop(f"unapproved V2 model/provider: {model}")
        entry = catalog.get(provider)
        if not isinstance(entry, dict):
            stop(f"missing provider catalog for {provider}")
        known = entry.get("whitelist") if provider == "openai" else entry.get("models")
        if provider == "openai":
            if not isinstance(known, list) or name not in known:
                stop(f"V2 model missing from OpenAI catalog: {model}")
        elif not isinstance(known, dict) or name not in known:
            stop(f"V2 model missing from Custom provider catalog: {model}")
    cloud = catalog[CUSTOM]
    opts = cloud.get("options")
    if not isinstance(opts, dict) or not isinstance(opts.get("headers"), dict):
        stop("Cloudflare provider options missing")
    headers = opts["headers"]
    if (cloud.get("npm") != "@ai-sdk/openai-compatible"
            or opts.get("baseURL") != SOURCE_URL or opts.get("apiKey") != ""
            or headers.get("Authorization") != ""
            or headers.get("cf-aig-authorization") != SOURCE_TOKEN):
        stop("Cloudflare endpoint/authentication contract changed; manual review required")
    safe_headers = {"Authorization": "", "cf-aig-authorization": "Bearer {env:OC_CF_API_TOKEN}"}
    for key in ("cf-aig-collect-log-payload", "cf-aig-max-attempts", "cf-aig-skip-cache"):
        value = headers.get(key)
        if not isinstance(value, str) or value not in ("true", "false", "1"):
            stop(f"unexpected Cloudflare setting: {key}")
        safe_headers[key] = value
    models = {}
    for identifier in ids:
        provider, _, name = identifier.partition("/")
        if provider == CUSTOM:
            info = cloud["models"][name]
            if not isinstance(info, dict) or not isinstance(info.get("name"), str):
                stop("missing Custom model metadata")
            models[name] = {"name": info["name"], "modelID": name}
    output = {
        "model": default,
        "providers": {
            CUSTOM: {
                "name": cloud.get("name", "Cloudflare AI Gateway (Custom)"),
                "env": ["OC_CF_API_TOKEN"],
                "package": "@opencode/ai/providers/openai-compatible",
                "settings": {
                    "baseURL": "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
                    # A non-secret placeholder. The actual token is used only in
                    # the cf-aig-authorization header; never copy V1 credentials.
                    "apiKey": "cloudflare-custom-provider",
                },
                "headers": safe_headers,
                "models": models,
            }
        },
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            *({"action": "provider.use", "resource": p, "effect": "allow"} for p in PROVIDERS),
        ],
    }
    return output


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
    print(f"Host V2 model={expected['model']}; custom models={len(expected['providers'][CUSTOM]['models'])}")
    if args.check:
        print("CHECK_ONLY: Host V2 settings are compatible; no changes made")
        return 0
    updated = {**current, **expected}
    state = {"source": "apm.yml:opencode_v2", "managed_sha256": fingerprint(expected)}
    atomic_json(config_path, updated)
    atomic_json(state_path, state)
    print("Host V2 model settings applied. Sign in to OpenAI separately; no credentials were copied.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MODEL_HOST_V2_STOP: {exc}", file=sys.stderr)
        sys.exit(1)
