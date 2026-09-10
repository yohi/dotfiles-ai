import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "_scripts" / "generate-gemini-codex-mcp.py"
SPEC = importlib.util.spec_from_file_location("generate_gemini_codex_mcp", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_mcp)


def test_sync_mcp_runs_codex_mcp_generator() -> None:
    result = subprocess.run(
        ["make", "-n", "sync-mcp"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "generate-gemini-codex-mcp.py --codex-only" in result.stdout


def test_setup_agents_applies_codex_configuration() -> None:
    makefile = (PROJECT_ROOT / "_mk" / "main.mk").read_text(encoding="utf-8")

    active_lines = {
        line.strip()
        for line in makefile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "$(MAKE) setup-codex" in active_lines


def test_codex_only_generation_preserves_gemini_config(tmp_path, monkeypatch) -> None:
    apm_path = tmp_path / "apm.yml"
    gemini_path = tmp_path / "settings.json"
    codex_path = tmp_path / "config.toml"
    apm_path.write_text(
        "dependencies:\n"
        "  mcp:\n"
        "    - name: enabled-server\n"
        "      command: uvx\n"
        "      args: [enabled-server]\n"
        "      enabled: true\n"
        "    - name: disabled-server\n"
        "      command: uvx\n"
        "      args: [disabled-server]\n"
        "      enabled: false\n",
        encoding="utf-8",
    )
    original_gemini = '{"existing": true}\n'
    gemini_path.write_text(original_gemini, encoding="utf-8")
    codex_path.write_text("# existing Codex settings\n", encoding="utf-8")

    monkeypatch.setattr(generate_mcp, "APM_YML", apm_path)
    monkeypatch.setattr(generate_mcp, "GEMINI_PATH", gemini_path)
    monkeypatch.setattr(generate_mcp, "CODEX_PATH", codex_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--codex-only"])

    assert generate_mcp.main() == 0
    assert gemini_path.read_text(encoding="utf-8") == original_gemini

    generated_codex = codex_path.read_text(encoding="utf-8")
    assert "enabled-server" in generated_codex
    assert "disabled-server" not in generated_codex


def test_sync_mcp_normalizes_opencode_after_apm_install() -> None:
    makefile = (PROJECT_ROOT / "_mk" / "mcp.mk").read_text(encoding="utf-8")

    apm_install_index = makefile.index("apm install --force")
    sync_opencode_index = makefile.index("$(MAKE) sync-opencode")

    assert sync_opencode_index > apm_install_index


def test_codex_server_resolves_environment_placeholders_in_stdio_arguments(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PWD", "/workspace/project")
    monkeypatch.setenv("HOME", "/workspace/home")

    server = generate_mcp._build_codex_mcp_server(
        {
            "name": "semgrep",
            "command": "uvx",
            "args": ["${env:PWD}", "${env:HOME}/.local/bin/semgrep"],
        }
    )

    assert server is not None
    assert server["args"] == ["/workspace/project", "/workspace/home/.local/bin/semgrep"]


def test_codex_server_forwards_environment_references_and_maps_timeout(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEMGREP_APP_TOKEN", raising=False)

    server = generate_mcp._build_codex_mcp_server(
        {
            "name": "semgrep",
            "command": "uvx",
            "args": ["semgrep-mcp"],
            "env": {"SEMGREP_APP_TOKEN": "${env:SEMGREP_APP_TOKEN}"},
            "timeout": 60000,
        }
    )

    assert server is not None
    assert server["env_vars"] == ["SEMGREP_APP_TOKEN"]
    assert "env" not in server
    assert server["startup_timeout_sec"] == 60


def test_codex_server_maps_remote_authentication_headers() -> None:
    server = generate_mcp._build_codex_mcp_server(
        {
            "name": "remote-server",
            "transport": "sse",
            "url": "https://example.test/mcp",
            "headers": {
                "Authorization": "Bearer ${env:REMOTE_TOKEN}",
                "X-API-Key": "${env:API_KEY}",
                "X-Static": "static-value",
            },
        }
    )

    assert server == {
        "url": "https://example.test/mcp",
        "type": "http",
        "bearer_token_env_var": "REMOTE_TOKEN",
        "env_http_headers": {"X-API-Key": "API_KEY"},
        "http_headers": {"X-Static": "static-value"},
    }


def test_codex_generation_maps_remote_timeout_to_startup_timeout(
    tmp_path, monkeypatch
) -> None:
    codex_path = tmp_path / "config.toml"
    codex_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(generate_mcp, "CODEX_PATH", codex_path)

    generate_mcp.update_codex(
        {
            "dependencies": {
                "mcp": [
                    {
                        "name": "remote-server",
                        "transport": "streamable-http",
                        "url": "https://example.test/mcp",
                        "timeout": 60000,
                        "enabled": True,
                    }
                ]
            }
        }
    )

    config = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert config["mcp_servers"]["remote-server"]["startup_timeout_sec"] == 60


def test_codex_generation_waits_for_optional_servers_until_their_timeout(tmp_path, monkeypatch) -> None:
    apm_path = tmp_path / "apm.yml"
    codex_path = tmp_path / "config.toml"
    apm_path.write_text(
        "dependencies:\n"
        "  mcp:\n"
        "    - name: slow-server\n"
        "      command: npx\n"
        "      args: [slow-server]\n"
        "      timeout: 60000\n"
        "      enabled: true\n",
        encoding="utf-8",
    )
    codex_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(generate_mcp, "APM_YML", apm_path)
    monkeypatch.setattr(generate_mcp, "CODEX_PATH", codex_path)

    generate_mcp.update_codex(
        {
            "dependencies": {
                "mcp": [
                    {
                        "name": "slow-server",
                        "command": "npx",
                        "args": ["slow-server"],
                        "timeout": 60000,
                        "enabled": True,
                    }
                ]
            }
        }
    )

    config = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert config["mcp_optional_startup_grace_ms"] == 0
    assert config["mcp_servers"]["slow-server"]["startup_timeout_sec"] == 60


def test_nexus_codex_config_forwards_github_package_auth() -> None:
    apm = yaml.safe_load((PROJECT_ROOT / "apm.yml").read_text(encoding="utf-8"))
    nexus = next(
        entry
        for entry in apm["dependencies"]["mcp"]
        if entry["name"] == "nexus"
    )

    server = generate_mcp._build_codex_mcp_server(nexus)

    assert server is not None
    assert "GITHUB_TOKEN" in server["env_vars"]
