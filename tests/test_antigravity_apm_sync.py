import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_antigravity_sync_installs_project_mcp_before_linking_global_config(
    tmp_path: Path,
) -> None:
    apm_root = tmp_path / "project"
    config_dir = tmp_path / "home" / ".gemini" / "antigravity-cli"
    mcp_config = apm_root / ".agents" / "mcp_config.json"
    custom_config = tmp_path / "custom-mcp.json"
    custom_config.write_text("{}\n", encoding="utf-8")
    config_dir.mkdir(parents=True)
    (config_dir / "mcp_config.json").symlink_to(custom_config)
    apm_call_log = tmp_path / "apm-call.txt"
    fake_apm = tmp_path / "fake-apm"
    fake_apm.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$APM_CALL_LOG"\n'
        'root="$PWD"\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--root" ]; then shift; root="$1"; fi\n'
        "  shift\n"
        "done\n"
        'mkdir -p "$root/.agents"\n'
        'printf \'{"mcpServers":{"registry-server":{"command":"mock"}}}\\n\' > "$root/.agents/mcp_config.json"\n',
        encoding="utf-8",
    )
    fake_apm.chmod(0o755)

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sync-antigravity-mcp",
            "setup-antigravity-mcp",
            f"APM_COMMAND={fake_apm}",
            f"ANTIGRAVITY_APM_ROOT={apm_root}",
            f"ANTIGRAVITY_PROJECT_MCP_CONFIG={mcp_config}",
            f"ANTIGRAVITY_CONFIG_DIR={config_dir}",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "APM_CALL_LOG": str(apm_call_log)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    global_mcp_config = config_dir / "mcp_config.json"
    assert global_mcp_config.is_symlink(), (
        f"stdout={result.stdout}; exists={global_mcp_config.exists()}; "
        f"symlink={global_mcp_config.is_symlink()}; "
        f"entries={list(config_dir.iterdir()) if config_dir.exists() else []}"
    )
    assert global_mcp_config.resolve() == mcp_config.resolve()
    backups = list(config_dir.glob("mcp_config.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].is_symlink()
    assert backups[0].resolve() == custom_config.resolve()
    apm_args = apm_call_log.read_text(encoding="utf-8")
    assert "--only mcp" in apm_args
    assert "--target" not in apm_args
    installed_config = json.loads(mcp_config.read_text(encoding="utf-8"))
    assert "registry-server" in installed_config["mcpServers"]
