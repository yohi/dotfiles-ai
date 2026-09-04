import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_index_skillport_exits_nonzero_when_index_build_fails(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uvx = fake_bin / "uvx"
    fake_uvx.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '{\"success\": false, \"skill_count\": 0, \"message\": \"build failed\"}'\n",
        encoding="utf-8",
    )
    fake_uvx.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    result = subprocess.run(
        ["make", "--no-print-directory", "index-skillport"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "失敗" in result.stdout
