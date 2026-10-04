import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_sync_claude_uses_project_manifest_and_preserves_user_config(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    config_dir = home / ".claude-profile"
    config_dir.mkdir(parents=True)
    claude_config = config_dir / ".claude.json"
    initial_config = {
        "projects": {"/workspace": {"hasTrustDialogAccepted": True}},
        "mcpServers": {"manual-server": {"type": "stdio", "command": "manual"}},
    }
    claude_config.write_text(json.dumps(initial_config), encoding="utf-8")

    apm_call_log = tmp_path / "apm-call.txt"
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['APM_CALL_LOG']).write_text(' '.join(sys.argv[1:]))\n"
        "config = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / '.claude.json'\n"
        "data = json.loads(config.read_text())\n"
        "data.setdefault('mcpServers', {})['registry-server'] = {'type': 'stdio', 'command': 'apm'}\n"
        "config.write_text(json.dumps(data))\n",
        encoding="utf-8",
    )
    fake_apm.chmod(0o755)

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sync-claude-apm-mcp",
            f"HOME_DIR={home}",
            f"CLAUDE_CONFIG_DIR={config_dir}",
            f"APM_COMMAND={fake_apm}",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "APM_CALL_LOG": str(apm_call_log),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    global_manifest = home / ".apm" / "apm.yml"
    assert global_manifest.is_symlink()
    assert global_manifest.resolve() == (REPO_ROOT / "apm.yml").resolve()
    arguments = apm_call_log.read_text(encoding="utf-8")
    assert "--global --only mcp --target claude" in arguments
    updated_config = json.loads(claude_config.read_text(encoding="utf-8"))
    assert updated_config["projects"] == initial_config["projects"]
    assert "manual-server" in updated_config["mcpServers"]
    assert "registry-server" in updated_config["mcpServers"]


def test_sync_claude_does_not_replace_existing_global_apm_manifest(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    global_apm = home / ".apm" / "apm.yml"
    global_apm.parent.mkdir(parents=True)
    existing_manifest = "name: separate-global-apm\n"
    global_apm.write_text(existing_manifest, encoding="utf-8")
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_apm.chmod(0o755)

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sync-claude-apm-mcp",
            f"HOME_DIR={home}",
            f"APM_COMMAND={fake_apm}",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not global_apm.is_symlink()
    assert global_apm.read_text(encoding="utf-8") == existing_manifest
