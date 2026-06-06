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
        if path.endswith("uvx") or path.endswith("npx"):
            return False
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
    assert skillport["command"] == "uvx"
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
