import json
import os
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
      SKILLPORT_SKILLS_DIR: "${env:PWD}/.agents/skills"
"""

def test_sync_antigravity(tmp_path):
    lockfile = tmp_path / "apm.lock.yaml"
    lockfile.write_text(MOCK_LOCKFILE)
    outfile = tmp_path / "mcp_config.json"
    
    # Run conversion logic using mock environment and mock file existence for standard paths
    original_exists = os.path.exists
    def mock_exists(path):
        if path.endswith(".local/bin/uvx") or path.endswith(".local/bin/npx") or path.endswith("uvx") or path.endswith("npx"):
            return True
        return original_exists(path)

    with mock.patch("os.path.exists", side_effect=mock_exists), \
         mock.patch("shutil.which", return_value=None), \
         mock.patch.dict(os.environ, {"PWD": "/workspace"}):
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

def test_sync_antigravity_missing_lockfile(tmp_path):
    import pytest
    from _scripts.sync_antigravity import convert_lockfile
    
    non_existent = tmp_path / "non_existent.yaml"
    outfile = tmp_path / "mcp_config.json"
    
    with pytest.raises(FileNotFoundError):
        convert_lockfile(str(non_existent), str(outfile))

def test_sync_antigravity_extended(tmp_path):
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
    
    with mock.patch("shutil.which", return_value="/usr/local/bin/uvx-custom"), \
         mock.patch("os.path.exists", return_value=True):
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

