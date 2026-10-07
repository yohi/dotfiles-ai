import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = REPO_ROOT / "_scripts" / "normalize_opencode_mcp_env.py"


def test_normalize_opencode_env_translates_apm_placeholders(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "_scripts"
    scripts_dir.mkdir(parents=True)
    script_path = scripts_dir / NORMALIZER.name
    shutil.copyfile(NORMALIZER, script_path)
    config_path = repo_root / "opencode.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {"example": {"apiKey": "${env:API_KEY}"}},
                "mcp": {
                    "filesystem": {
                        "command": ["npx", "${env:PWD}"],
                        "environment": {"ROOT": "${env:HOME}"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["uv", "run", "--script", str(script_path), str(config_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["mcp"]["filesystem"]["command"] == ["npx", "{env:PWD}"]
    assert config["mcp"]["filesystem"]["environment"]["ROOT"] == "{env:HOME}"
    assert config["provider"]["example"]["apiKey"] == "{env:API_KEY}"


def test_normalizer_rejects_paths_outside_repository(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "_scripts"
    scripts_dir.mkdir(parents=True)
    script_path = scripts_dir / NORMALIZER.name
    shutil.copyfile(NORMALIZER, script_path)
    protected_file = tmp_path / "protected.json"
    protected_file.write_text('{"key": "${env:SECRET}"}\n', encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "--script", str(script_path), str(protected_file)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert json.loads(protected_file.read_text(encoding="utf-8"))["key"] == "${env:SECRET}"
