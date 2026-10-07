import os
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_setup_codex_preserves_existing_config_and_links_apm_output(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    global_config = home / ".codex" / "config.toml"
    global_config.parent.mkdir(parents=True)
    original_config = (
        'model = "private-model"\n[projects."/workspace"]\ntrust_level = "trusted"\n'
    )
    global_config.write_text(original_config, encoding="utf-8")

    apm_root = tmp_path / "project"
    apm_call_log = tmp_path / "apm-call.txt"
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" > "$APM_CALL_LOG"\n'
        'root="$PWD"\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--root" ]; then shift; root="$1"; fi\n'
        "  shift\n"
        "done\n"
        'printf \'\\n[mcp_servers.registry-server]\\ncommand = "mock"\\nargs = []\\n\' >> "$root/.codex/config.toml"\n',
        encoding="utf-8",
    )
    fake_apm.chmod(0o755)

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "setup-codex",
            f"HOME_DIR={home}",
            f"CODEX_APM_ROOT={apm_root}",
            f"APM_COMMAND={fake_apm}",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "APM_CALL_LOG": str(apm_call_log)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    apm_config = apm_root / ".codex" / "config.toml"
    assert global_config.is_symlink()
    assert global_config.resolve() == apm_config.resolve()
    installed_config = tomllib.loads(apm_config.read_text(encoding="utf-8"))
    assert installed_config["model"] == "private-model"
    assert installed_config["projects"]["/workspace"]["trust_level"] == "trusted"
    assert "registry-server" in installed_config["mcp_servers"]
    apm_args = apm_call_log.read_text(encoding="utf-8")
    assert "--only mcp" in apm_args
    assert "--target" not in apm_args
    backups = list(global_config.parent.glob("config.toml.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original_config


def test_apm_manifest_targets_cover_linked_mcp_clients() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "apm.yml").read_text(encoding="utf-8"))
    assert {"opencode", "codex", "antigravity"}.issubset(set(manifest["targets"]))


def test_setup_codex_backs_up_a_conflicting_config_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    global_config = home / ".codex" / "config.toml"
    global_config.parent.mkdir(parents=True)
    custom_config = tmp_path / "custom-config.toml"
    custom_config.write_text('model = "custom-model"\n', encoding="utf-8")
    global_config.symlink_to(custom_config)

    apm_root = tmp_path / "project"
    apm_config = apm_root / ".codex" / "config.toml"
    apm_config.parent.mkdir(parents=True)
    apm_config.write_text('model = "apm-model"\n', encoding="utf-8")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "setup-codex",
            f"HOME_DIR={home}",
            f"CODEX_APM_ROOT={apm_root}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert global_config.is_symlink()
    assert global_config.resolve() == apm_config.resolve()
    backups = list(global_config.parent.glob("config.toml.bak.*"))
    assert len(backups) == 1
    assert backups[0].is_symlink()
    assert backups[0].resolve() == custom_config.resolve()


@pytest.mark.parametrize(
    "target",
    [
        "sync-mcp",
        "sync-agents-run",
        "apm-install",
        "sync-antigravity",
        "sync-antigravity-mcp",
        "sync-codex-apm-mcp",
    ],
)
def test_apm_install_targets_seed_codex_config_first(
    tmp_path: Path,
    target: str,
) -> None:
    home = tmp_path / "home"
    global_config = home / ".codex" / "config.toml"
    global_config.parent.mkdir(parents=True)
    global_config.write_text('model = "user-model"\n', encoding="utf-8")
    apm_config = tmp_path / "project" / ".codex" / "config.toml"

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-n",
            target,
            f"HOME_DIR={home}",
            f"CODEX_APM_ROOT={tmp_path / 'project'}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    seed_command = f'cp -p "{global_config}" "{apm_config}"'
    assert seed_command in result.stdout
    assert result.stdout.index(seed_command) < result.stdout.index("apm install")
