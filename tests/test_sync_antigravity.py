import json
import os
from pathlib import Path
from unittest import mock

# Stub config to mock apm.lock.yaml
MOCK_LOCKFILE = """
lockfile_version: '1'
mcp_configs:
  skillport:
    name: skillport
    transport: stdio
    command: uvx
    args:
      - skillport-mcp
    env:
      SKILLPORT_SKILLS_DIR: "${env:SKILLPORT_SKILLS_DIR:-.agents/skills}"
"""


def test_sync_antigravity(tmp_path: Path) -> None:
    """Test successful conversion of the mock lockfile to mcp_config.json."""
    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text(MOCK_LOCKFILE)
    outfile = tmp_path / "mcp_config.json"

    # Run conversion logic using mock environment and mock file existence for standard paths
    original_exists = os.path.exists

    def mock_exists(path: str) -> bool:
        if (
            path.endswith(".local/bin/uvx")
            or path.endswith(".local/bin/npx")
            or path.endswith("uvx")
            or path.endswith("npx")
        ):
            return True
        return original_exists(path)

    with (
        mock.patch("os.path.exists", side_effect=mock_exists),
        mock.patch("shutil.which", return_value=None),
        mock.patch.dict(os.environ, {"SKILLPORT_SKILLS_DIR": "/workspace/.agents/skills"}),
    ):
        from _scripts.sync_antigravity import convert_lockfile

        convert_lockfile(str(lockfile), str(outfile))

    assert outfile.exists()
    content = json.loads(outfile.read_text())
    assert "mcpServers" in content
    assert "skillport" in content["mcpServers"]

    skillport = content["mcpServers"]["skillport"]
    assert skillport["command"].endswith("uvx")
    assert skillport["args"] == ["skillport-mcp"]
    # Verify environment variable substitution
    assert skillport["env"]["SKILLPORT_SKILLS_DIR"] == "/workspace/.agents/skills"



def test_sync_antigravity_fallback(tmp_path: Path) -> None:
    """Test that SKILLPORT_SKILLS_DIR resolves to its fallback default when the environment variable is not set."""
    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text(MOCK_LOCKFILE)
    outfile = tmp_path / "mcp_config.json"

    original_exists = os.path.exists

    def mock_exists(path: str) -> bool:
        if (
            path.endswith(".local/bin/uvx")
            or path.endswith(".local/bin/npx")
            or path.endswith("uvx")
            or path.endswith("npx")
        ):
            return True
        return original_exists(path)

    # Clean SKILLPORT_SKILLS_DIR from environment if exists
    clean_env = os.environ.copy()
    clean_env.pop("SKILLPORT_SKILLS_DIR", None)

    with (
        mock.patch("os.path.exists", side_effect=mock_exists),
        mock.patch("shutil.which", return_value=None),
        mock.patch.dict(os.environ, clean_env, clear=True),
    ):
        from _scripts.sync_antigravity import convert_lockfile

        convert_lockfile(str(lockfile), str(outfile))

    assert outfile.exists()
    content = json.loads(outfile.read_text())
    skillport = content["mcpServers"]["skillport"]
    # Fallback to default ".agents/skills"
    assert skillport["env"]["SKILLPORT_SKILLS_DIR"] == ".agents/skills"


def test_sync_antigravity_missing_lockfile(tmp_path: Path) -> None:
    """Test that convert_lockfile raises FileNotFoundError when the lockfile is missing."""
    import pytest
    from _scripts.sync_antigravity import convert_lockfile

    non_existent = tmp_path / "non_existent.yaml"
    outfile = tmp_path / "mcp_config.json"

    with pytest.raises(FileNotFoundError):
        convert_lockfile(str(non_existent), str(outfile))


def test_sync_antigravity_extended(tmp_path: Path) -> None:
    """Test convert_lockfile with custom server configuration and env variable replacement."""
    mock_lockfile = """
lockfile_version: '1'
mcp_configs:
  skillport:
    name: skillport
    transport: stdio
    command: uvx
    args:
      - skillport-mcp
  custom_server:
    name: custom_server
    url: http://localhost:8000
    headers:
      Authorization: Bearer test
"""
    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text(mock_lockfile)
    outfile = tmp_path / "mcp_config.json"

    with (
        mock.patch("shutil.which", return_value="/usr/local/bin/uvx-custom"),
        mock.patch("os.path.exists", return_value=True),
    ):
        from _scripts.sync_antigravity import convert_lockfile

        convert_lockfile(str(lockfile), str(outfile))

    assert outfile.exists()
    content = json.loads(outfile.read_text())
    assert "mcpServers" in content
    assert "skillport" in content["mcpServers"]
    assert "custom_server" in content["mcpServers"]

    skillport = content["mcpServers"]["skillport"]
    assert skillport["command"] == "/usr/local/bin/uvx-custom"

    custom_server = content["mcpServers"]["custom_server"]
    assert "serverUrl" in custom_server
    assert custom_server["serverUrl"] == "http://localhost:8000"
    assert custom_server["headers"] == {"Authorization": "Bearer test"}


def test_sync_antigravity_invalid_lockfile_format(tmp_path: Path) -> None:
    """Test that convert_lockfile raises ValueError when lock_data is not a mapping/dict."""
    import pytest
    from _scripts.sync_antigravity import convert_lockfile

    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text("invalid_string_not_a_dict")
    outfile = tmp_path / "mcp_config.json"

    with pytest.raises(ValueError):
        convert_lockfile(str(lockfile), str(outfile))

def test_sync_antigravity_env_var_simple(tmp_path: Path) -> None:
    """Test environment variable expansion with $VAR and ${VAR} syntax."""
    mock_lockfile = """
lockfile_version: '1'
mcp_configs:
  test_server:
    name: test_server
    command: uvx
    env:
      SIMPLE_VAR: "$TEST_SIMPLE"
      BRACED_VAR: "${TEST_BRACED}"
"""
    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text(mock_lockfile)
    outfile = tmp_path / "mcp_config.json"

    with (
        mock.patch("shutil.which", return_value="/usr/local/bin/uvx"),
        mock.patch("os.path.exists", return_value=True),
        mock.patch.dict(os.environ, {"TEST_SIMPLE": "simple_value", "TEST_BRACED": "braced_value"}),
    ):
        from _scripts.sync_antigravity import convert_lockfile

        convert_lockfile(str(lockfile), str(outfile))

    assert outfile.exists()
    content = json.loads(outfile.read_text())
    server = content["mcpServers"]["test_server"]
    assert server["env"]["SIMPLE_VAR"] == "simple_value"
    assert server["env"]["BRACED_VAR"] == "braced_value"

