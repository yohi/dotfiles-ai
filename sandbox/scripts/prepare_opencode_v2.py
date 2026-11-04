#!/usr/bin/env python3
"""Prepare a secret-free OpenCode V2 config snapshot from the APM SSOT.

No sandbox provisioning, credential lookup, network access, or host config writes.
Only selected provider and model declarations are converted to the V2 schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

import yaml


VERSION = "v0.2"
OPENCODE_VERSION = "2.2.5"
MAX_APM_BYTES = 2 * 1024 * 1024
FILES = ("opencode.jsonc", "cli.json", "export-manifest.json")

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
AuthMethod: TypeAlias = Literal["docker_openai_oauth", "docker_custom_secret"]


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    provider_id: str
    enabled: bool
    auth_method: AuthMethod
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class APMConfig:
    shell: str
    snapshot: bool
    source_sha256: str
    v2_config: dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class V2Settings:
    default_model: str
    deny_provider_fallback: bool
    deny_guest_auth: bool
    providers: tuple[ProviderSelection, ...]


class ExportError(Exception):
    """A safe, non-sensitive export failure."""


def _json_bytes(value: JsonValue) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _normalize_yaml(value: JsonValue) -> JsonValue:
    match value:
        case str() | int() | float() | bool() | None:
            return value
        case list() as items:
            return [_normalize_yaml(item) for item in items]
        case dict() as items:
            normalized: dict[str, JsonValue] = {}
            for key, item in items.items():
                if not isinstance(key, str):
                    raise ExportError("APM mapping keys must be strings")
                normalized[key] = _normalize_yaml(item)
            return normalized
        case _:
            raise ExportError("apm.yml contains an unsupported YAML value")


def _mapping(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExportError(f"{label} must be a mapping")
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExportError(f"{label} must be a non-empty string")
    return value


def _model_ids(provider_id: str, source: dict[str, JsonValue]) -> tuple[str, ...]:
    if provider_id == "openai":
        raw_models = source.get("whitelist")
        if not isinstance(raw_models, list) or not raw_models:
            raise ExportError("provider.openai.whitelist must contain models")
        models = tuple(item for item in raw_models if isinstance(item, str) and item)
        if len(models) != len(raw_models):
            raise ExportError("provider.openai.whitelist contains an invalid model ID")
        return models

    models = _mapping(source.get("models"), f"provider.{provider_id}.models")
    if not models:
        raise ExportError(f"provider.{provider_id}.models must not be empty")
    return tuple(models)


def _parse_v2_settings(
    apm: dict[str, JsonValue], provider_catalog: dict[str, JsonValue],
) -> V2Settings | None:
    raw_settings = apm.get("opencode_v2")
    if raw_settings is None:
        return None
    settings = _mapping(raw_settings, "opencode_v2")
    default_model = _string(settings.get("default_model"), "opencode_v2.default_model")
    if settings.get("deny_provider_fallback") is not True:
        raise ExportError("opencode_v2 must deny provider fallback")
    if settings.get("deny_guest_auth") is not True:
        raise ExportError("opencode_v2 must deny Guest-side authentication")

    raw_providers = _mapping(settings.get("providers"), "opencode_v2.providers")
    selections: list[ProviderSelection] = []
    for provider_id, raw_selection in raw_providers.items():
        selection = _mapping(raw_selection, f"opencode_v2.providers.{provider_id}")
        enabled = selection.get("enabled")
        if type(enabled) is not bool:
            raise ExportError(f"opencode_v2.providers.{provider_id}.enabled must be boolean")
        raw_auth_method = selection.get("auth_method")
        if not isinstance(raw_auth_method, str):
            raise ExportError(f"opencode_v2.providers.{provider_id}.auth_method is required")
        match raw_auth_method:
            case "docker_openai_oauth":
                auth_method: AuthMethod = raw_auth_method
            case "docker_custom_secret":
                auth_method = raw_auth_method
            case _:
                raise ExportError(f"unsupported auth method for provider {provider_id}")
        expected_methods: dict[str, AuthMethod] = {
            "openai": "docker_openai_oauth",
            "cloudflare-ai-gateway-custom": "docker_custom_secret",
        }
        if auth_method != expected_methods.get(provider_id):
            raise ExportError(f"unsupported auth method for provider {provider_id}")
        source = _mapping(provider_catalog.get(provider_id), f"provider.{provider_id}")
        selections.append(
            ProviderSelection(
                provider_id=provider_id,
                enabled=enabled,
                auth_method=auth_method,
                model_ids=_model_ids(provider_id, source),
            )
        )

    enabled = tuple(provider for provider in selections if provider.enabled)
    enabled_ids = {provider.provider_id for provider in enabled}
    if enabled_ids != {"openai", "cloudflare-ai-gateway-custom"} or len(enabled) != 2:
        raise ExportError("opencode_v2 must enable OpenAI and Cloudflare Custom")
    provider_id, separator, model_id = default_model.partition("/")
    selected_provider = next(
        (provider for provider in enabled if provider.provider_id == provider_id), None,
    )
    if not separator or not model_id or selected_provider is None:
        raise ExportError("opencode_v2.default_model must use an enabled provider")
    if model_id not in selected_provider.model_ids:
        raise ExportError("opencode_v2.default_model is not declared in apm.yml")
    return V2Settings(
        default_model=default_model,
        deny_provider_fallback=True,
        deny_guest_auth=True,
        providers=tuple(selections),
    )


def _normalize_env(value: str) -> str:
    return re.sub(r"\$\{(env:[^}]+)\}", r"{\1}", value)


def _v2_variant(value: JsonValue, label: str) -> dict[str, JsonValue]:
    raw = _mapping(value, label)
    settings: dict[str, JsonValue] = {}
    result: dict[str, JsonValue] = {}
    for key, item in raw.items():
        if key in {"reasoningEffort", "reasoningSummary"}:
            settings[key] = item
        elif key in {"settings", "headers", "body"}:
            nested = _mapping(item, f"{label}.{key}")
            result[key] = nested
        else:
            raise ExportError(f"unsupported V1 variant field: {label}.{key}")
    if settings:
        result["settings"] = settings
    return result


def _v2_model(model_id: str, value: JsonValue) -> dict[str, JsonValue]:
    raw = _mapping(value, f"provider model {model_id}")
    unknown = set(raw) - {"name", "variants"}
    if unknown:
        raise ExportError(f"unsupported V1 model fields for {model_id}")
    model: dict[str, JsonValue] = {
        "modelID": model_id,
        "name": _string(raw.get("name"), f"provider model {model_id}.name"),
    }
    variants_raw = raw.get("variants", {})
    variants = _mapping(variants_raw, f"provider model {model_id}.variants")
    variants_out: list[JsonValue] = []
    for variant_id, variant_value in variants.items():
        converted = _v2_variant(variant_value, f"provider model {model_id}.{variant_id}")
        if variant_id == "default":
            model.update(converted)
        else:
            variants_out.append({"id": variant_id, **converted})
    if variants_out:
        model["variants"] = variants_out
    return model


def _v2_provider(provider_id: str, source: dict[str, JsonValue], model_ids: tuple[str, ...]) -> dict[str, JsonValue]:
    if provider_id == "openai":
        return {
            "models": {
                model_id: {"modelID": model_id, "name": model_id}
                for model_id in model_ids
            }
        }

    package_map = {
        "@ai-sdk/openai-compatible": "aisdk:@ai-sdk/openai-compatible",
        "@ai-sdk/openai": "aisdk:@ai-sdk/openai",
    }
    npm = _string(source.get("npm"), f"provider.{provider_id}.npm")
    package = package_map.get(npm)
    if package is None:
        raise ExportError(f"unsupported V2 provider package for {provider_id}")
    provider: dict[str, JsonValue] = {
        "package": package,
        "name": _string(source.get("name"), f"provider.{provider_id}.name"),
    }
    options = _mapping(source.get("options"), f"provider.{provider_id}.options")
    settings: dict[str, JsonValue] = {}
    headers: dict[str, JsonValue] = {}
    for key, value in options.items():
        if key == "baseURL":
            settings["baseURL"] = _normalize_env(_string(value, f"provider.{provider_id}.baseURL"))
        elif key == "apiKey":
            if value == "":
                continue
            api_key = _string(value, f"provider.{provider_id}.apiKey")
            if re.fullmatch(r"(?:\$\{env:[A-Za-z_][A-Za-z0-9_]*\}|\{env:[A-Za-z_][A-Za-z0-9_]*\})", api_key) is None:
                raise ExportError(f"literal API key is forbidden for provider {provider_id}")
            settings["apiKey"] = _normalize_env(api_key)
        elif key == "headers":
            raw_headers = _mapping(value, f"provider.{provider_id}.headers")
            for header_name, header_value in raw_headers.items():
                text = _string(header_value, f"provider.{provider_id}.headers.{header_name}") if header_value != "" else ""
                if header_name.casefold() in {"authorization", "cf-aig-authorization", "x-api-key"} and text and "{env:" not in _normalize_env(text):
                    raise ExportError(f"literal credential header is forbidden for provider {provider_id}")
                headers[header_name] = _normalize_env(text)
        else:
            raise ExportError(f"unsupported V1 provider option: {provider_id}.{key}")
    if settings:
        provider["settings"] = settings
    if headers:
        provider["headers"] = headers
    raw_models = _mapping(source.get("models"), f"provider.{provider_id}.models")
    provider["models"] = {
        model_id: _v2_model(model_id, raw_models[model_id])
        for model_id in model_ids
    }
    return provider


def _build_v2_config(
    settings: V2Settings, provider_catalog: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Build a positive-selection V2 config without exporting credentials."""
    enabled = tuple(provider for provider in settings.providers if provider.enabled)
    providers: dict[str, JsonValue] = {}
    for selection in enabled:
        source = _mapping(provider_catalog.get(selection.provider_id), f"provider.{selection.provider_id}")
        providers[selection.provider_id] = _v2_provider(
            selection.provider_id, source, selection.model_ids,
        )
    policies: list[JsonValue] = [
        {"action": "provider.use", "resource": "*", "effect": "deny"},
        *(
            {"action": "provider.use", "resource": selection.provider_id, "effect": "allow"}
            for selection in enabled
        ),
        {"action": "integration.connect", "resource": "*", "effect": "deny"},
        {"action": "plugin.use", "resource": "*", "effect": "deny"},
        {"action": "mcp.use", "resource": "*", "effect": "deny"},
    ]
    return {"model": settings.default_model, "providers": providers, "policies": policies}


def _read_apm_source(root: Path) -> APMConfig:
    source = root / "apm.yml"
    if source.is_symlink() or not source.is_file():
        raise ExportError("apm.yml must be a regular, non-symlink file")
    if source.stat().st_size > MAX_APM_BYTES:
        raise ExportError("apm.yml exceeds the input size limit")
    raw = source.read_bytes()
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ExportError("apm.yml is not valid YAML") from exc
    if not isinstance(loaded, dict):
        raise ExportError("apm.yml must contain a mapping")
    normalized = _normalize_yaml(loaded)
    if not isinstance(normalized, dict):
        raise ExportError("apm.yml must contain a string-keyed mapping")
    shell = normalized.get("shell", "bash")
    snapshot = normalized.get("snapshot", True)
    if type(shell) is not str or shell not in {"bash", "sh", "zsh"}:
        raise ExportError("apm.yml shell is not approved")
    if type(snapshot) is not bool:
        raise ExportError("apm.yml snapshot must be a boolean")
    provider_catalog = _mapping(normalized.get("provider", {}), "provider")
    v2_settings = _parse_v2_settings(normalized, provider_catalog)
    v2_config = (
        _build_v2_config(v2_settings, provider_catalog)
        if v2_settings is not None else None
    )
    return APMConfig(
        shell=shell,
        snapshot=snapshot,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        v2_config=v2_config,
    )


def _read_apm(root: Path) -> tuple[str, bool, str]:
    apm = _read_apm_source(root)
    return apm.shell, apm.snapshot, apm.source_sha256


def _build_files(
    shell: str, snapshot: bool, apm_sha: str,
    v2_config: dict[str, JsonValue] | None = None,
) -> dict[str, bytes]:
    # Strict positive selection: none of the other apm.yml values is serialized.
    server: dict[str, JsonValue] = {
        "$schema": "https://opencode.ai/config.json",
        "shell": shell,
        "snapshot": snapshot,
    }
    if v2_config is None:
        server["plugins"] = []
        server["mcp"] = {}
    else:
        server.update(v2_config)
    tui: dict[str, JsonValue] = {
        "$schema": "https://opencode.ai/v2/cli.json",
        "plugins": [],
    }
    generated = {
        "opencode.jsonc": _json_bytes(server),
        "cli.json": _json_bytes(tui),
    }
    manifest: dict[str, JsonValue] = {
        "schema": "dotfiles-ai/sandbox-export/v0",
        "generator": VERSION,
        "source": "apm.yml",
        "config_format": "opencode-v2" if v2_config is not None else "legacy-minimal",
        "source_sha256": apm_sha,
        "opencode_version": OPENCODE_VERSION,
        "plugins_exported": 0,
        "mcp_entries_exported": 0,
        "artifacts_sha256": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(generated.items())
        },
    }
    generated["export-manifest.json"] = _json_bytes(manifest)
    return generated


def _validate_destination(root: Path, output: Path) -> Path:
    # Refuse accidental writes into the source checkout or the user's live
    # OpenCode configuration. The destination is an independent staging area.
    if output.is_symlink():
        raise ExportError("output directory must not be a symlink")
    for candidate in (output, *output.parents):
        if candidate.is_symlink():
            raise ExportError("output path contains a symlink")
    actual = output.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if actual == temp_root or not actual.is_relative_to(temp_root):
        raise ExportError("output must be under the temporary directory")
    if actual == root or actual.is_relative_to(root):
        raise ExportError("output must be outside the source repository")
    home = Path.home().resolve()
    if actual == home / ".config" or actual.is_relative_to(home / ".config"):
        raise ExportError("output must not be under ~/.config")
    if actual == home / ".local" / "share" / "opencode" or actual.is_relative_to(
        home / ".local" / "share" / "opencode"
    ):
        raise ExportError("output must not be under OpenCode runtime data")
    return actual


def _check(output: Path, generated: dict[str, bytes]) -> None:
    if not output.is_dir() or output.is_symlink():
        raise ExportError("check output directory is missing or unsafe")
    entries = {entry.name for entry in output.iterdir()}
    if entries != set(FILES):
        raise ExportError("output file set does not match expected manifest")
    for name, expected in generated.items():
        file = output / name
        if file.is_symlink() or not file.is_file() or file.read_bytes() != expected:
            raise ExportError("export mismatch: " + name)


def _create(output: Path, generated: dict[str, bytes]) -> None:
    if output.exists() or output.is_symlink():
        raise ExportError("output already exists (overwrite is prohibited)")
    if not output.parent.is_dir():
        raise ExportError("output parent directory must already exist")
    output.mkdir(mode=0o700)
    for name, data in generated.items():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(output / name, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="verify existing snapshot, never write")
    args = parser.parse_args(argv)

    try:
        if args.repo_root.is_symlink():
            raise ExportError("repository root must not be a symlink")
        root = args.repo_root.resolve(strict=True)
        output = _validate_destination(root, args.out)
        apm = _read_apm_source(root)
        generated = _build_files(
            apm.shell, apm.snapshot, apm.source_sha256, apm.v2_config,
        )
        if args.check:
            _check(output, generated)
            print("CHECK_OK")
        else:
            _create(output, generated)
            print("EXPORT_OK: " + str(output))
        return 0
    except (OSError, ExportError) as exc:
        # Do not echo source YAML text or any unselected values.
        message = str(exc) if isinstance(exc, ExportError) else "filesystem operation failed"
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
