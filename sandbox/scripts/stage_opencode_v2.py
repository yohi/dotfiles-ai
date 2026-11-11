#!/usr/bin/env python3
"""Stage an exported OpenCode v2 config into a local Docker Sandbox.

Default is read-only dry-run. --apply transfers an immutable-looking, uniquely
named copy into the sandbox workspace and verifies it; it never activates config.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypeAlias

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

exporter = importlib.import_module("sandbox.scripts.prepare_opencode_v2")

NAMES = frozenset({"opencode.jsonc", "cli.json", "export-manifest.json"})
MAX_BYTES = 1024 * 1024
SANDBOX_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,61}[a-zA-Z0-9]$")
BUNDLE_DIRECTORY_RE = re.compile(r"^sbx-config-[a-f0-9]{16}-[a-f0-9]{12}$")
HOST_BUNDLE_RE = re.compile(r"^opencode-v2-export-[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
REMOTE_PARENT = str(Path("/home") / "agent" / "workspace")  # guest-only mountless path
BUNDLE_ROOT = Path(tempfile.gettempdir())
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class StageError(Exception):
    """Expected failure without exposing file contents or CLI stderr."""


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


def _regular_bytes(directory_fd: int, name: str) -> bytes:
    if name not in NAMES:
        raise StageError("unexpected bundle file name")
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise StageError("bundle member is not a safe regular file: " + name) from exc
    try:
        file_info = os.fstat(file_fd)
        if not stat.S_ISREG(file_info.st_mode):
            raise StageError("bundle member is not a regular file: " + name)
        if file_info.st_size > MAX_BYTES:
            raise StageError("bundle file exceeds size limit: " + name)
        with os.fdopen(file_fd, "rb", closefd=False) as file:
            content = file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise StageError("bundle file exceeds size limit: " + name)
        return content
    finally:
        os.close(file_fd)


def _verify_v2_config(server: dict[str, JsonValue]) -> None:
    """Reject V2 bundles that can activate other providers or Guest auth."""
    expected_keys = {"$schema", "shell", "snapshot", "model", "providers", "policies"}
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
        try:
            exporter.validate_v2_provider_options(provider_name, settings, headers)
        except exporter.ExportError as exc:
            raise StageError("V2 provider request settings are not approved") from exc


def verify_bundle(directory: Path) -> str:
    """Validate content and hashes, without executing any exported config."""
    if directory.is_symlink() or not directory.is_dir():
        raise StageError("bundle directory must be a regular directory")
    directory_fd = _open_bundle_directory(directory)
    try:
        if set(os.listdir(directory_fd)) != NAMES:
            raise StageError("unexpected bundle file set")
        data = {name: _regular_bytes(directory_fd, name) for name in NAMES}
    finally:
        os.close(directory_fd)
    try:
        manifest = json.loads(
            data["export-manifest.json"], object_pairs_hook=exporter._unique_json_object,
        )
        server = json.loads(
            data["opencode.jsonc"], object_pairs_hook=exporter._unique_json_object,
        )
        tui = json.loads(data["cli.json"], object_pairs_hook=exporter._unique_json_object)
    except (ValueError, UnicodeDecodeError) as exc:
        raise StageError("bundle is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise StageError("invalid manifest")
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
    expected = {
        name: hashlib.sha256(data[name]).hexdigest()
        for name in ("opencode.jsonc", "cli.json")
    }
    if manifest.get("artifacts_sha256") != expected:
        raise StageError("artifact checksum mismatch")
    if manifest.get("plugins_exported") != 0 or manifest.get("mcp_entries_exported") != 0:
        raise StageError("exported plugins or MCP entries are forbidden")
    if not isinstance(server, dict):
        raise StageError("unexpected server config fields")
    if server["$schema"] != "https://opencode.ai/config.json":
        raise StageError("unexpected server config schema")
    if server["shell"] not in ("bash", "sh", "zsh") or type(server["shell"]) is not str:
        raise StageError("unapproved shell")
    if type(server["snapshot"]) is not bool:
        raise StageError("unapproved server config values")
    match manifest["config_format"]:
        case "legacy-minimal":
            if (set(server) != {"$schema", "shell", "snapshot", "plugins", "mcp"}
                    or server["plugins"] != [] or server["mcp"] != {}):
                raise StageError("unapproved legacy server config values")
        case "opencode-v2":
            _verify_v2_config(server)
        case _:
            raise StageError("unrecognized config format")
    if not isinstance(tui, dict) or tui != {"$schema": "https://opencode.ai/v2/cli.json", "plugins": []}:
        raise StageError("unexpected TUI config")
    return hashlib.sha256(data["export-manifest.json"]).hexdigest()


def _run(command: list[str]) -> None:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageError("sandbox command could not complete") from exc
    if proc.returncode != 0:
        raise StageError("sandbox command failed (no config activated)")


def _check_source(root: Path, bundle: Path) -> None:
    try:
        apm = exporter._read_apm_source(root)
    except (OSError, exporter.ExportError) as exc:
        raise StageError("export provenance check could not complete") from exc
    expected = exporter._build_files(
        apm.shell, apm.snapshot, apm.source_sha256, apm.v2_config,
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
    digest = verify_bundle(bundle)
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
        _run(["sbx", "exec", sandbox, "sh", "-c",
              'test -d "$1" && test ! -L "$1" && test ! -e "$2" && test ! -L "$2"'
              ' && test ! -e "$3" && test ! -L "$3"',
              "sh", REMOTE_PARENT, remote, remote_verifier])
        _run(["sbx", "cp", str(folder), f"{sandbox}:{remote}"])
        verifier = Path(__file__).resolve(strict=True)
        # Verifier is executed from the sandbox agent's local Python interpreter.
        # Transfer separately to avoid smuggling a script in a supposedly data-only bundle.
        _run(["sbx", "cp", str(verifier), f"{sandbox}:{remote_verifier}"])
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
            if not BUNDLE_DIRECTORY_RE.fullmatch(args.verify_bundle):
                raise StageError("invalid staged bundle directory name")
            digest = verify_bundle(Path(REMOTE_PARENT) / args.verify_bundle)
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
