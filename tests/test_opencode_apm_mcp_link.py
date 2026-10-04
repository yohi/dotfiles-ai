import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_setup_opencode_links_apm_mcp_config_without_replacing_global_config(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config" / "opencode"
    opencode_home = tmp_path / ".opencode"
    omo_dir = tmp_path / ".omo"
    apm_mcp_config = tmp_path / "project" / "opencode.json"
    apm_mcp_config.parent.mkdir()
    apm_mcp_config.write_text(
        json.dumps({"mcp": {"filesystem": {"command": ["npx", "${env:PWD}"]}}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "setup-opencode",
            f"OPENCODE_CONFIG_DIR={config_dir}",
            f"OPENCODE_CONFIG_PATH={config_dir / 'opencode.jsonc'}",
            f"OPENCODE_MCP_CONFIG_PATH={config_dir / 'opencode.json'}",
            f"OPENCODE_APM_MCP_CONFIG_SOURCE={apm_mcp_config}",
            f"OPENCODE_TUI_CONFIG_PATH={config_dir / 'tui.json'}",
            f"OPENCODE_ANTIGRAVITY_PATH={config_dir / 'antigravity.json'}",
            f"OPENCODE_AGENTS_PATH={config_dir / 'AGENTS.md'}",
            f"OPENCODE_HOME={opencode_home}",
            f"OPENCODE_COMMANDS_PATH={opencode_home / 'commands'}",
            f"OPENCODE_SKILLS_PATH={opencode_home / 'skills'}",
            f"OPENCODE_DOCS_PATH={config_dir / 'docs'}",
            f"OMO_CONFIG_DIR={omo_dir}",
            f"OMO_CONFIG_PATH={omo_dir / 'omo.jsonc'}",
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    global_mcp_config = config_dir / "opencode.json"
    assert global_mcp_config.is_symlink()
    assert global_mcp_config.resolve() == apm_mcp_config.resolve()
    normalized_config = json.loads(apm_mcp_config.read_text(encoding="utf-8"))
    assert normalized_config["mcp"]["filesystem"]["command"] == [
        "npx",
        "{env:PWD}",
    ]
    assert (config_dir / "opencode.jsonc").resolve() == (
        REPO_ROOT / "opencode" / "opencode.jsonc"
    ).resolve()
