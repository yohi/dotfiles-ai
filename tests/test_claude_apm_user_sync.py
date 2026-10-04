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


def test_setup_claude_preserves_existing_claude_json_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    alternate_config = tmp_path / "alternate-claude.json"
    alternate_config.write_text('{"user":"kept"}\n', encoding="utf-8")
    root_claude_config = home / ".claude.json"
    root_claude_config.symlink_to(alternate_config)
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    alternate_settings = tmp_path / "alternate-settings.json"
    alternate_settings.write_text('{"settings":"kept"}\n', encoding="utf-8")
    (claude_dir / "settings.json").symlink_to(alternate_settings)
    claude_config_dir = home / ".claude-profile"
    claude_config_dir.mkdir()
    active_config = claude_config_dir / ".claude.json"
    active_config.write_text('{"mcpServers":{"manual":{}}}\n', encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['APM_CALL_LOG']).write_text(' '.join(sys.argv[1:]))\n"
        "config = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / '.claude.json'\n"
        "data = json.loads(config.read_text())\n"
        "data.setdefault('mcpServers', {})['apm-server'] = {'command': 'apm'}\n"
        "config.write_text(json.dumps(data))\n",
        encoding="utf-8",
    )
    fake_apm.chmod(0o755)
    apm_call_log = tmp_path / "apm-call.txt"
    path_env = os.pathsep.join((str(fake_bin), os.environ["PATH"]))

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "setup-claude",
            f"HOME_DIR={home}",
            f"CLAUDE_CONFIG_DIR={claude_config_dir}",
            f"APM_COMMAND={fake_apm}",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(claude_config_dir),
            "APM_CALL_LOG": str(apm_call_log),
            "PATH": path_env,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert root_claude_config.is_symlink()
    assert root_claude_config.resolve() == alternate_config.resolve()
    settings_config = claude_dir / "settings.json"
    assert settings_config.is_symlink()
    assert settings_config.resolve() == (REPO_ROOT / "claude/settings.json").resolve()
    backups = list(claude_dir.glob("settings.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].is_symlink()
    assert backups[0].resolve() == alternate_settings.resolve()
    assert "apm-server" in json.loads(active_config.read_text())["mcpServers"]


def test_sync_claude_refuses_to_atomically_replace_user_config_symlink(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    config_dir = home / ".claude-profile"
    config_dir.mkdir(parents=True)
    alternate_config = tmp_path / "alternate-claude.json"
    alternate_content = '{"mcpServers":{"manual":{}}}\n'
    alternate_config.write_text(alternate_content, encoding="utf-8")
    active_config = config_dir / ".claude.json"
    active_config.symlink_to(alternate_config)
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert active_config.is_symlink()
    assert active_config.resolve() == alternate_config.resolve()
    assert alternate_config.read_text(encoding="utf-8") == alternate_content
