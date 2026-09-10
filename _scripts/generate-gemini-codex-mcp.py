"""Generate Gemini and Codex MCP server sections from apm.yml (SSOT).

This script updates the tracked configuration files so they stay in sync with
apm.yml without manually editing each client config.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
APM_YML = REPO_ROOT / "apm.yml"
GEMINI_PATH = REPO_ROOT / "gemini" / "settings.json"
CODEX_PATH = REPO_ROOT / "codex" / "config.toml"


def _convert_env_syntax(value: str) -> str:
    """Convert apm.yml ${env:VAR} syntax to generic ${VAR} syntax."""
    return re.sub(r"\$\{(env:([^}]+))\}", r"${\2}", value)


def _convert_value(value: Any) -> Any:
    if isinstance(value, str):
        return _convert_env_syntax(value)
    if isinstance(value, list):
        return [_convert_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert_value(v) for k, v in value.items()}
    return value


def _mcp_entries(apm: dict[str, Any]) -> list[dict[str, Any]]:
    entries = (apm.get("dependencies") or {}).get("mcp") or []
    return [e for e in entries if e.get("enabled", True)]


def _build_mcp_server(entry: dict[str, Any]) -> dict[str, Any] | None:
    transport = entry.get("transport", "stdio")
    if transport in ("sse", "http", "streamable-http"):
        url = entry.get("url")
        if not url:
            print(
                f"[warning] Skipping MCP server '{entry.get('name', '?')}': url is missing for sse transport."
            )
            return None
        server: dict[str, Any] = {
            "url": _convert_value(url),
            "type": "sse",
        }
        if "headers" in entry:
            server["headers"] = _convert_value(entry["headers"])
        return server
    command = entry.get("command")
    if not command:
        print(
            f"[warning] Skipping MCP server '{entry.get('name', '?')}': command is missing for stdio transport."
        )
        return None

    server = {
        "command": _convert_value(command),
        "args": _convert_value(entry.get("args") or []),
        "type": "stdio",
    }
    if "env" in entry:
        server["env"] = _convert_value(entry["env"])
    return server


def _expand_codex_env_syntax(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        variable = match.group(1)
        default = match.group(2)
        if variable in os.environ:
            return os.environ[variable]
        if default is not None:
            return default
        if variable == "PWD":
            return str(Path.cwd())
        if variable == "HOME":
            return str(Path.home())
        return match.group(0)

    return re.sub(
        r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}",
        replace,
        value,
    )


def _build_codex_environment(
    values: dict[str, Any],
) -> tuple[dict[str, str], list[str]]:
    environment: dict[str, str] = {}
    env_vars: list[str] = []
    pattern = r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}"

    for name, raw_value in values.items():
        value = str(raw_value)
        match = re.fullmatch(pattern, value)
        if match and match.group(1) == name:
            variable = match.group(1)
            default = match.group(2)
            if variable in os.environ or default is None:
                env_vars.append(variable)
            else:
                environment[name] = default
            continue
        environment[name] = _expand_codex_env_syntax(value)

    return environment, env_vars


def _build_codex_mcp_server(entry: dict[str, Any]) -> dict[str, Any] | None:
    transport = entry.get("transport", "stdio")
    server: dict[str, Any]
    if transport in ("sse", "http", "streamable-http"):
        url = entry.get("url")
        if not url:
            print(
                f"[warning] Skipping MCP server '{entry.get('name', '?')}': url is missing for {transport} transport."
            )
            return None

        server = {
            "url": _expand_codex_env_syntax(str(url)),
            "type": "http",
        }
        http_headers: dict[str, str] = {}
        env_http_headers: dict[str, str] = {}
        for raw_name, raw_value in (entry.get("headers") or {}).items():
            name = str(raw_name)
            value = str(raw_value)
            bearer_match = re.fullmatch(
                r"Bearer \$\{env:([A-Za-z_][A-Za-z0-9_]*)\}", value
            )
            if name.lower() == "authorization" and bearer_match:
                server["bearer_token_env_var"] = bearer_match.group(1)
                continue

            env_match = re.fullmatch(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}", value)
            if env_match:
                env_http_headers[name] = env_match.group(1)
            else:
                http_headers[name] = _expand_codex_env_syntax(value)

        if http_headers:
            server["http_headers"] = http_headers
        if env_http_headers:
            server["env_http_headers"] = env_http_headers
    else:
        command = entry.get("command")
        if not command:
            print(
                f"[warning] Skipping MCP server '{entry.get('name', '?')}': command is missing for stdio transport."
            )
            return None

        server = {
            "command": _expand_codex_env_syntax(str(command)),
            "args": [
                _expand_codex_env_syntax(str(arg)) for arg in (entry.get("args") or [])
            ],
            "type": "stdio",
        }

        if entry.get("env"):
            environment, env_vars = _build_codex_environment(entry["env"])
            if environment:
                server["env"] = environment
            if env_vars:
                server["env_vars"] = env_vars

    timeout_ms = entry.get("timeout")
    if isinstance(timeout_ms, (int, float)) and not isinstance(timeout_ms, bool):
        if timeout_ms > 0:
            server["startup_timeout_sec"] = max(1, math.ceil(timeout_ms / 1000))

    return server




def _toml_escape(value: str) -> str:
    """Return a TOML double-quoted basic string for simple values."""
    return json.dumps(value, ensure_ascii=True)


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _toml_escape(key)


def _toml_dump_table(key_path: list[str], data: dict[str, Any], lines: list[str]) -> None:
    table_header = ".".join(_toml_key(k) for k in key_path)
    lines.append(f"[{table_header}]")
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        if isinstance(value, list):
            escaped = ", ".join(_toml_escape(str(v)) for v in value)
            lines.append(f"{key} = [{escaped}]")
        elif isinstance(value, str):
            lines.append(f"{key} = {_toml_escape(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")
    for key, value in data.items():
        if isinstance(value, dict):
            _toml_dump_table(key_path + [key], value, lines)
            lines.append("")


def _dump_mcp_servers(mcp_servers: dict[str, Any], lines: list[str]) -> None:
    if mcp_servers:
        lines.append("")
        lines.append("[mcp_servers]")
        lines.append("")
        for server_name, server_cfg in mcp_servers.items():
            _toml_dump_table(["mcp_servers", server_name], server_cfg, lines)
            lines.append("")


def _dump_codex_config(data: dict[str, Any], trailing_comments: list[str]) -> str:
    lines: list[str] = []
    mcp_servers = data.get("mcp_servers", {})
    for key, value in data.items():
        if key == "mcp_servers":
            _dump_mcp_servers(mcp_servers, lines)
            continue
        if isinstance(value, dict):
            lines.append("")
            _toml_dump_table([key], value, lines)
            lines.append("")
        elif isinstance(value, list):
            escaped = ", ".join(_toml_escape(str(v)) for v in value)
            lines.append(f"{key} = [{escaped}]")
        elif isinstance(value, str):
            lines.append(f"{key} = {_toml_escape(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")

    if trailing_comments:
        lines.extend(trailing_comments)

    return "\n".join(lines).rstrip() + "\n"



def _extract_trailing_comments(text: str) -> list[str]:
    lines = text.splitlines()
    comments: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            comments.insert(0, line)
            continue
        if stripped.startswith("#"):
            comments.insert(0, line)
        else:
            break
    return comments


def update_gemini(apm: dict[str, Any]) -> None:
    entries = _mcp_entries(apm)
    mcp_servers = {
        str(e["name"]): cfg
        for e in entries
        if (cfg := _build_mcp_server(e)) is not None
    }

    data: dict[str, Any]
    if GEMINI_PATH.exists():
        with open(GEMINI_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["mcpServers"] = mcp_servers

    with open(GEMINI_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")
    print(f"[ok] Updated: {GEMINI_PATH}")


def update_codex(apm: dict[str, Any]) -> None:
    entries = _mcp_entries(apm)
    mcp_servers = {
        str(e["name"]): cfg
        for e in entries
        if (cfg := _build_codex_mcp_server(e)) is not None
    }

    original_text = ""
    if CODEX_PATH.exists():
        with open(CODEX_PATH, "r", encoding="utf-8") as f:
            original_text = f.read()
    trailing_comments = _extract_trailing_comments(original_text)

    data: dict[str, Any]
    if CODEX_PATH.exists():
        data = tomllib.loads(original_text)
    else:
        data = {}

    data = {
        "mcp_optional_startup_grace_ms": data.get(
            "mcp_optional_startup_grace_ms", 0
        ),
        **data,
    }
    data["mcp_servers"] = mcp_servers

    with open(CODEX_PATH, "w", encoding="utf-8") as f:
        f.write(_dump_codex_config(data, trailing_comments))
    print(f"[ok] Updated: {CODEX_PATH}")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode not in {"all", "--codex-only", "--gemini-only"}:
        print(f"[error] Unknown generation mode: {mode}", file=sys.stderr)
        return 2

    try:
        apm = yaml.safe_load(APM_YML.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"[error] Failed to read {APM_YML}: {exc}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"[error] Failed to parse {APM_YML}: {exc}", file=sys.stderr)
        return 1

    if mode in {"all", "--gemini-only"}:
        update_gemini(apm)
    if mode in {"all", "--codex-only"}:
        update_codex(apm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
