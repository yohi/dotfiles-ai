#!/usr/bin/env python3
"""Stage an exported OpenCode v2 config into a local Docker Sandbox.

Default is read-only dry-run. --apply transfers an immutable-looking, uniquely
named copy into the sandbox workspace and verifies it; it never activates config.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Iterable, TypeAlias


def _load_agent_policy() -> ModuleType:
    """Load the verified sibling policy helper without importing a Host package."""
    sidecar = Path(str(__file__) + '.native.py')
    if sidecar.exists() or sidecar.is_symlink():
        helper = sidecar
    elif Path(__file__).name == 'stage_opencode_v2.py':
        helper = Path(__file__).with_name('oc2_agent_native.py')
    else:
        raise ImportError('SHA-verified Native Agent policy sidecar is missing')
    if helper.is_symlink() or not helper.is_file():
        raise ImportError('Native Agent policy helper is missing or linked')
    spec = importlib.util.spec_from_file_location('oc2_agent_native_guest', helper)
    if spec is None or spec.loader is None:
        raise ImportError('Native Agent policy helper cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


agent_policy = _load_agent_policy()

NAMES = frozenset({"opencode.jsonc", "cli.json", "export-manifest.json"})
MAX_BYTES = 1024 * 1024
SECRET_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----",
    rb"\bAKIA[0-9A-Z]{16}\b",
    rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
    rb"\bsk-[A-Za-z0-9]{24,}\b",
    rb"(?i)\b(?:api[_-]?key|access[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}",
))
SECRET_PLACEHOLDERS = (b"DO_NOT_EXPORT", b"EXAMPLE", b"PLACEHOLDER", b"DUMMY", b"FIXTURE")
SANDBOX_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,61}[a-zA-Z0-9]$")
BUNDLE_DIRECTORY_RE = re.compile(r"^sbx-config-[a-f0-9]{16}-[a-f0-9]{12}$")
HOST_BUNDLE_RE = re.compile(r"^opencode-v2-export-[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
REMOTE_PARENT = str(Path("/home") / "agent" / "workspace")  # guest-only mountless path
BUNDLE_ROOT = Path(tempfile.gettempdir())
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
REASONING_VALUES = {
    "reasoningEffort": frozenset({"minimal", "low", "medium", "high", "xhigh", "max"}),
    "reasoningSummary": frozenset({"auto", "concise", "detailed"}),
}


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Parse a JSON object while rejecting duplicate keys."""
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise StageError("duplicate JSON object key")
        result[key] = value
    return result


def _contains_credential_material(data: bytes) -> bool:
    """Detect configured credential signatures, ignoring recognized fixture placeholders."""
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(data):
            value = match.group().upper()
            if not any(placeholder in value for placeholder in SECRET_PLACEHOLDERS):
                return True
    return False


def _verify_model_settings(value: JsonValue, label: str) -> None:
    """Require only supported reasoning settings and values."""
    if not isinstance(value, dict):
        raise StageError("invalid model reasoning settings: " + label)
    for key, item in value.items():
        allowed = REASONING_VALUES.get(key)
        if allowed is None or not isinstance(item, str) or item not in allowed:
            raise StageError("unapproved model reasoning setting: " + label)


def _verify_model_options(key: str, options: dict[str, JsonValue], label: str) -> None:
    """Allow only empty model headers and the supported thinking body control."""
    if key == "headers":
        if options:
            raise StageError("unsupported model headers: " + label)
        return
    if set(options) - {"thinking"}:
        raise StageError("unsupported model body field: " + label)
    thinking = options.get("thinking")
    if thinking is None and "thinking" not in options:
        return
    if (not isinstance(thinking, dict) or set(thinking) != {"type"}
            or not isinstance(thinking["type"], str)
            or thinking["type"] not in {"enabled", "disabled"}):
        raise StageError("unsupported model thinking option: " + label)


def _verify_model_catalog(models: JsonValue) -> None:
    """Validate model identities, variants, and credential-free options."""
    if not isinstance(models, dict):
        raise StageError("invalid V2 model catalog")
    for model_id, value in models.items():
        if not isinstance(value, dict) or set(value) - {
            "modelID", "name", "settings", "headers", "body", "variants",
        }:
            raise StageError("invalid V2 model configuration")
        if value.get("modelID") != model_id or not isinstance(value.get("name"), str):
            raise StageError("V2 model identity does not match its catalog")
        _verify_model_settings(value.get("settings", {}), model_id)
        for key in ("headers", "body"):
            options = value.get(key, {})
            if not isinstance(options, dict):
                raise StageError("invalid V2 model " + key)
            _verify_model_options(key, options, model_id + "." + key)
        variants = value.get("variants", [])
        if not isinstance(variants, list):
            raise StageError("invalid V2 model variants")
        seen: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise StageError("invalid V2 model variant")
            variant_id = variant.get("id")
            if not isinstance(variant_id, str):
                raise StageError("invalid V2 model variant")
            if variant_id in seen or set(variant) - {"id", "settings", "headers", "body"}:
                raise StageError("invalid V2 model variant")
            seen.add(variant_id)
            _verify_model_settings(variant.get("settings", {}), model_id + "." + variant_id)
            for key in ("headers", "body"):
                options = variant.get(key, {})
                if not isinstance(options, dict):
                    raise StageError("invalid V2 model variant " + key)
                _verify_model_options(key, options, model_id + "." + variant_id)


class StageError(Exception):
    """Expected failure without exposing file contents or CLI stderr."""


def _regular_bytes(directory_fd: int, name: str) -> bytes:
    """Read an allowlisted regular bundle file without following symlinks or exceeding MAX_BYTES."""
    if name not in NAMES:
        raise StageError("bundle file is not in the allowlist")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise StageError("bundle file could not be opened safely: " + name) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise StageError("missing, non-regular, or symlinked bundle file: " + name)
        if info.st_size > MAX_BYTES:
            raise StageError("bundle file exceeds size limit: " + name)
        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, min(MAX_BYTES + 1 - size, 65536)):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise StageError("bundle file exceeds size limit: " + name)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _host_bundle_path(name: str) -> Path:
    if HOST_BUNDLE_RE.fullmatch(name) is None:
        raise StageError("bundle must be identified by its generated directory name")
    if (not BUNDLE_ROOT.is_absolute()
            or any(parent.is_symlink() for parent in (BUNDLE_ROOT, *BUNDLE_ROOT.parents))):
        raise StageError("temporary bundle root is not safe")
    bundle = BUNDLE_ROOT / name
    try:
        info = bundle.lstat()
    except OSError as exc:
        raise StageError("bundle directory is missing or unsafe") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise StageError("bundle directory must be private and owned by the current user")
    return bundle


def _open_bundle_directory(directory: Path) -> int:
    if ".." in directory.parts or any(parent.is_symlink() for parent in directory.parents):
        raise StageError("bundle path contains traversal or a symlink")
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise StageError("bundle directory is not safe") from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise StageError("bundle directory is not a regular directory")
    return directory_fd


def _read_bundle_files(directory: Path, names: Iterable[str]) -> dict[str, bytes]:
    requested = tuple(names)
    if not requested or not set(requested) <= NAMES:
        raise StageError("bundle file is not in the allowlist")
    directory_fd = _open_bundle_directory(directory)
    try:
        return {name: _regular_bytes(directory_fd, name) for name in requested}
    finally:
        os.close(directory_fd)


def _verify_v2_config(server: dict[str, JsonValue]) -> None:
    """Reject V2 bundles that can activate other providers or Guest auth."""
    expected_keys = {"$schema", "shell", "snapshot", "model", "providers", "policies"}
    if "agents" in server:
        expected_keys.add("agents")
        try:
            agent_policy.validate_agent_map(server["agents"])
        except ValueError as exc:
            raise StageError("unapproved V2 Native Agent configuration") from exc
    if set(server) != expected_keys:
        raise StageError("unexpected V2 server config fields")
    model = server.get("model")
    providers = server.get("providers")
    policies = server.get("policies")
    allowed_providers = {"openai", "cloudflare-ai-gateway-custom"}
    if (not isinstance(model, str) or "/" not in model
            or not isinstance(providers, dict) or set(providers) != allowed_providers
            or not isinstance(policies, list)):
        raise StageError("invalid V2 provider selection")
    provider_id, model_id = model.split("/", 1)
    if not model_id or provider_id not in providers:
        raise StageError("V2 model does not match the selected provider")
    provider = providers[provider_id]
    if not isinstance(provider, dict):
        raise StageError("invalid V2 provider configuration")
    models = provider.get("models")
    if not isinstance(models, dict) or model_id not in models:
        raise StageError("V2 default model is not in the provider catalog")
    for provider_config in providers.values():
        if not isinstance(provider_config, dict):
            raise StageError("invalid V2 provider configuration")
        _verify_model_catalog(provider_config.get("models"))
    expected_policies: list[JsonValue] = [
        {"action": "provider.use", "resource": "*", "effect": "deny"},
        {"action": "provider.use", "resource": "openai", "effect": "allow"},
        {"action": "provider.use", "resource": "cloudflare-ai-gateway-custom", "effect": "allow"},
        {"action": "integration.connect", "resource": "*", "effect": "deny"},
        {"action": "plugin.use", "resource": "*", "effect": "deny"},
        {"action": "mcp.use", "resource": "*", "effect": "deny"},
    ]
    if policies != expected_policies:
        raise StageError("V2 fallback or Guest authentication policy is not fail-closed")
    for provider_name, provider_config in providers.items():
        if not isinstance(provider_name, str) or not isinstance(provider_config, dict):
            raise StageError("invalid V2 provider configuration")
        settings = provider_config.get("settings", {})
        headers = provider_config.get("headers", {})
        if not isinstance(settings, dict) or not isinstance(headers, dict):
            raise StageError("invalid V2 provider request settings")
        if provider_name == "openai":
            if settings or headers:
                raise StageError("OpenAI V2 configuration must not contain Guest credentials")
        elif provider_name == "cloudflare-ai-gateway-custom":
            if settings != {"baseURL": CF_CUSTOM_BASE_URL}:
                raise StageError("Cloudflare Custom baseURL is not approved")
            _verify_custom_headers(headers)
        else:
            raise StageError("unsupported V2 provider options")


CF_CUSTOM_BASE_URL = (
    "https://gateway.ai.cloudflare.com/v1/"
    "{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat"
)
CF_CUSTOM_HEADERS = {
    "Authorization": "",
    "cf-aig-authorization": "Bearer {env:OC_CF_API_TOKEN}",
    "cf-aig-collect-log-payload": "true",
    "cf-aig-max-attempts": "1",
    "cf-aig-skip-cache": "true",
}


def _verify_custom_headers(headers: dict[str, JsonValue]) -> None:
    """Require the exact approved Cloudflare proxy headers."""
    allowed = {name.casefold(): (name, value) for name, value in CF_CUSTOM_HEADERS.items()}
    seen: set[str] = set()
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise StageError("Cloudflare Custom header names and values must be strings")
        folded = name.casefold()
        approved = allowed.get(folded)
        if folded in seen or approved != (name, value):
            raise StageError("Cloudflare Custom header is not approved")
        seen.add(folded)
    if headers.get("cf-aig-authorization") != CF_CUSTOM_HEADERS["cf-aig-authorization"]:
        raise StageError("Cloudflare Custom proxy authorization header is required")


def _validated_bundle_directory(directory: Path, trusted_root: Path) -> Path:
    """Resolve a bundle strictly beneath the trusted root, rejecting traversal and symlink paths."""
    root = trusted_root.absolute()
    candidate = directory if directory.is_absolute() else Path.cwd() / directory
    candidate = candidate.absolute()
    if ".." in candidate.parts:
        raise StageError("bundle directory contains traversal")
    if candidate == root or not candidate.is_relative_to(root):
        raise StageError("bundle directory is outside the approved staging root")
    current = candidate
    while current != root:
        if current.is_symlink():
            raise StageError("bundle directory path contains a symlink")
        current = current.parent
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise StageError("bundle directory resolves outside the approved staging root")
    return resolved


def verify_bundle(directory: Path, *, trusted_root: Path) -> str:
    """Validate content and hashes, without executing any exported config."""
    directory = _validated_bundle_directory(directory, trusted_root)
    directory_fd = _open_bundle_directory(directory)
    try:
        if set(os.listdir(directory_fd)) != NAMES:
            raise StageError("unexpected bundle file set")
        manifest, server, tui, data = _load_bundle(directory_fd)
    finally:
        os.close(directory_fd)
    if any(_contains_credential_material(content) for content in data.values()):
        raise StageError("bundle contains credential material")

    digest = _validate_manifest(manifest, data)
    _validate_server_config(server, manifest)
    _validate_tui_config(tui)
    return digest




def _load_bundle(
    directory_fd: int,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue], dict[str, bytes]]:
    """Read the allowlisted bundle files and parse the three JSON documents as objects."""
    data = {name: _regular_bytes(directory_fd, name) for name in NAMES}
    try:
        manifest = json.loads(
            data["export-manifest.json"], object_pairs_hook=_unique_json_object,
        )
        server = json.loads(
            data["opencode.jsonc"], object_pairs_hook=_unique_json_object,
        )
        tui = json.loads(data["cli.json"], object_pairs_hook=_unique_json_object)
    except (ValueError, UnicodeDecodeError) as exc:
        raise StageError("bundle is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or not isinstance(server, dict) or not isinstance(tui, dict):
        raise StageError("bundle JSON roots must be objects")
    return manifest, server, tui, data


def _validate_manifest(manifest: dict[str, JsonValue], data: dict[str, bytes]) -> str:
    expected_keys = {"schema", "generator", "source", "config_format", "source_sha256",
                     "opencode_version", "plugins_exported", "mcp_entries_exported",
                     "artifacts_sha256"}
    if set(manifest) != expected_keys:
        raise StageError("unexpected manifest fields")
    if manifest.get("generator") != "v0.2" or manifest.get("source") != "apm.yml":
        raise StageError("unexpected export generator or source")
    if manifest.get("schema") != "dotfiles-ai/sandbox-export/v0":
        raise StageError("invalid manifest schema")
    if manifest.get("opencode_version") != "2.2.5":
        raise StageError("unapproved OpenCode version")
    source_hash = manifest.get("source_sha256")
    if not isinstance(source_hash, str) or re.fullmatch(r"[a-f0-9]{64}", source_hash) is None:
        raise StageError("invalid source digest")
    expected_hashes = {
        name: hashlib.sha256(data[name]).hexdigest()
        for name in ("opencode.jsonc", "cli.json")
    }
    if manifest.get("artifacts_sha256") != expected_hashes:
        raise StageError("artifact checksum mismatch")
    if manifest.get("plugins_exported") != 0 or manifest.get("mcp_entries_exported") != 0:
        raise StageError("exported plugins or MCP entries are forbidden")
    return hashlib.sha256(data["export-manifest.json"]).hexdigest()


def _validate_server_config(
    server: dict[str, JsonValue],
    manifest: dict[str, JsonValue],
) -> None:
    if server.get("$schema") != "https://opencode.ai/config.json":
        raise StageError("unexpected server config schema")
    if server.get("shell") not in ("bash", "sh", "zsh") or type(server.get("shell")) is not str:
        raise StageError("unapproved shell")
    if type(server.get("snapshot")) is not bool:
        raise StageError("unapproved server config values")
    match manifest["config_format"]:
        case "legacy-minimal":
            if (set(server) != {"$schema", "shell", "snapshot", "plugins", "mcp"}
                    or server["plugins"] != [] or server["mcp"] != {}):
                raise StageError("unapproved legacy server config values")
        case "oc2-verification":
            if (set(server) != {"$schema", "shell", "snapshot", "plugins", "mcp"}
                    or server["plugins"] != [] or server["mcp"] != {}):
                raise StageError("unapproved verification server config values")
        case "opencode-v2":
            _verify_v2_config(server)
        case _:
            raise StageError("unrecognized config format")


def _validate_tui_config(tui: dict[str, JsonValue]) -> None:
    if tui != {"$schema": "https://opencode.ai/v2/cli.json", "plugins": []}:
        raise StageError("unexpected TUI config")


def verify_guest_bundle(bundle_name: str) -> str:
    expected_parent = Path(REMOTE_PARENT)
    if BUNDLE_DIRECTORY_RE.fullmatch(bundle_name) is None:
        raise StageError("guest bundle must be an approved staging directory")
    if any(parent.is_symlink() for parent in (expected_parent, *expected_parent.parents)):
        raise StageError("guest bundle path contains a symlink")
    return verify_bundle(expected_parent / bundle_name, trusted_root=expected_parent)


def _run(command: list[str]) -> bytes:
    """Run a Sandbox command and return stdout after checking its exit status."""
    try:
        proc = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageError("sandbox command could not complete") from exc
    if proc.returncode != 0:
        raise StageError("sandbox command failed (no config activated)")
    return proc.stdout


def _check_source(root: Path, bundle: Path) -> None:
    bundle = _validated_bundle_directory(bundle, BUNDLE_ROOT)
    try:
        import importlib

        exporter = importlib.import_module("sandbox.scripts.prepare_opencode_v2")
    except ImportError as exc:
        raise StageError("export provenance check could not complete") from exc
    try:
        manifest_data = _read_bundle_files(bundle, ("export-manifest.json",))[
            "export-manifest.json"
        ]
        manifest = json.loads(manifest_data)
        verification_only = (
            isinstance(manifest, dict)
            and manifest.get("config_format") == "oc2-verification"
        )
        apm = exporter._read_apm_source(root, verification_only=verification_only)
    except (OSError, ValueError, UnicodeDecodeError, exporter.ExportError) as exc:
        raise StageError("export provenance check could not complete") from exc
    expected = exporter._build_files(
        apm.shell, apm.snapshot, apm.source_sha256, apm.v2_config,
        verification_only=apm.verification_only,
    )
    directory_fd = _open_bundle_directory(bundle)
    try:
        if any(_regular_bytes(directory_fd, name) != content
               for name, content in expected.items()):
            raise StageError("bundle does not match the current apm.yml SSOT")
    finally:
        os.close(directory_fd)


def stage(bundle: Path, repo_root: Path, sandbox: str | None, apply: bool) -> None:
    if bundle.is_symlink():
        raise StageError("bundle path must not be a symlink")
    root = repo_root.resolve(strict=True)
    digest = verify_bundle(bundle, trusted_root=BUNDLE_ROOT)
    _check_source(root, bundle)
    if not apply:
        print("DRY_RUN_OK: verified source and snapshot; nothing transferred")
        return
    if not sandbox or not SANDBOX_RE.fullmatch(sandbox):
        raise StageError("--apply requires a valid local sandbox name")
    if shutil.which("sbx") is None:
        raise StageError("sbx CLI was not found")
    with tempfile.TemporaryDirectory(prefix="opencode-v2-stage-") as tmp:
        folder = Path(tmp) / ("sbx-config-" + digest[:16] + "-" + os.urandom(6).hex())
        folder.mkdir(mode=0o755)
        for name in sorted(NAMES):
            shutil.copyfile(bundle / name, folder / name)
            (folder / name).chmod(0o644)  # Non-secret output; guest agent may have another UID.
        remote = REMOTE_PARENT + "/" + folder.name
        # The VM owns this path, never a host mount in the intended configuration.
        remote_verifier = REMOTE_PARENT + "/." + folder.name + ".verify.py"
        native_helper = Path(__file__).with_name('oc2_agent_native.py')
        if native_helper.is_symlink() or not native_helper.is_file():
            raise StageError('Native Agent policy helper is missing or linked')
        native_helper = native_helper.resolve(strict=True)
        native_helper_sha = hashlib.sha256(native_helper.read_bytes()).hexdigest()
        remote_native_helper = remote_verifier + '.native.py'
        _run(["sbx", "exec", sandbox, "sh", "-c",
              'test -d "$1" && test ! -L "$1" && test ! -e "$2" && test ! -L "$2"'
              ' && test ! -e "$3" && test ! -L "$3"'
              ' && test ! -e "$4" && test ! -L "$4"',
              "sh", REMOTE_PARENT, remote, remote_verifier, remote_native_helper])
        _run(["sbx", "cp", str(folder), f"{sandbox}:{remote}"])
        verifier = Path(__file__).resolve(strict=True)
        # Verifier is executed from the sandbox agent's local Python interpreter.
        # Transfer separately to avoid smuggling a script in a supposedly data-only bundle.
        _run(["sbx", "cp", str(verifier), f"{sandbox}:{remote_verifier}"])
        _run(["sbx", "cp", str(native_helper), f"{sandbox}:{remote_native_helper}"])
        helper_sha = _run(
            ["sbx", "exec", sandbox, "sha256sum", remote_native_helper],
        ).split()
        if not helper_sha or helper_sha[0] != native_helper_sha.encode("ascii"):
            raise StageError("Guest Native Agent policy helper SHA mismatch")
        _run(["sbx", "exec", sandbox, "python3", remote_verifier,
              "--verify-bundle", folder.name])
        print("STAGED_AND_VERIFIED: " + sandbox + ":" + remote)
        print("NOT_ACTIVATED: OpenCode settings were not modified")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify-bundle", help="verify a staged bundle by its generated directory name")
    p.add_argument("--bundle", help="generated bundle directory name under the temporary directory")
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--sandbox", help="local Docker Sandbox name (used only with --apply)")
    p.add_argument("--apply", action="store_true", help="explicitly copy and verify; never activate")
    args = p.parse_args(argv)
    try:
        if args.verify_bundle is not None:
            digest = verify_guest_bundle(args.verify_bundle)
            print("VERIFY_OK: " + digest)
        else:
            if args.bundle is None:
                raise StageError("--bundle is required")
            stage(_host_bundle_path(args.bundle), args.repo_root, args.sandbox, args.apply)
        return 0
    except (StageError, OSError) as exc:
        msg = str(exc) if isinstance(exc, StageError) else "filesystem operation failed"
        print("ERROR: " + msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
