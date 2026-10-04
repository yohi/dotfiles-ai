import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "_scripts" / "backup-config-path.sh"


def test_backup_config_path_uses_an_unused_name(tmp_path: Path) -> None:
    source = tmp_path / "config.json"
    source.write_text("current config\n", encoding="utf-8")
    first_backup = tmp_path / "config.json.bak.fixed"
    second_backup = tmp_path / "config.json.bak.fixed.1"
    first_backup.write_text("older backup\n", encoding="utf-8")
    second_backup.write_text("newer backup\n", encoding="utf-8")

    result = subprocess.run(
        ["sh", str(BACKUP_SCRIPT), str(source), "fixed"],
        capture_output=True,
        text=True,
        check=False,
    )

    final_backup = tmp_path / "config.json.bak.fixed.2"
    assert result.returncode == 0, result.stderr
    assert not source.exists()
    assert final_backup.read_text(encoding="utf-8") == "current config\n"
    assert first_backup.read_text(encoding="utf-8") == "older backup\n"
    assert second_backup.read_text(encoding="utf-8") == "newer backup\n"


def test_backup_config_path_moves_a_symlink_without_following_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "config.json"
    target = tmp_path / "user-config.json"
    target.write_text("user config\n", encoding="utf-8")
    source.symlink_to(target)

    result = subprocess.run(
        ["sh", str(BACKUP_SCRIPT), str(source), "fixed"],
        capture_output=True,
        text=True,
        check=False,
    )

    backup = tmp_path / "config.json.bak.fixed"
    assert result.returncode == 0, result.stderr
    assert not source.is_symlink()
    assert backup.is_symlink()
    assert backup.resolve() == target.resolve()
    assert target.read_text(encoding="utf-8") == "user config\n"
