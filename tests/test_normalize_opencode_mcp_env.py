import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = REPO_ROOT / "_scripts" / "normalize_opencode_mcp_env.py"


def test_normalize_opencode_env_translates_apm_placeholders(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "opencode.json"
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
        ["uv", "run", "--script", str(NORMALIZER), str(config_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["mcp"]["filesystem"]["command"] == ["npx", "{env:PWD}"]
    assert config["mcp"]["filesystem"]["environment"]["ROOT"] == "{env:HOME}"
    assert config["provider"]["example"]["apiKey"] == "{env:API_KEY}"
