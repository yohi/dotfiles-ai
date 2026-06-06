# APM Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the legacy Makefile sync workflow and optimize APM usage by centralizing all external skills and target compilations under APM, including a custom hook wrapper for Antigravity settings generation.

**Architecture:** Points Skillport MCP to the APM `.agents/skills` output dir, removes redundant file copies, and uses a python-based post-compile hook to generate Antigravity's `mcp_config.json` from `apm.lock.yaml`.

**Tech Stack:** Python, pytest, yaml, APM, Make

---

### Task 1: Create Antigravity Config Generator (`_scripts/sync_antigravity.py`) with TDD

**Files:**
- Create: `_scripts/sync_antigravity.py`
- Create: `tests/test_sync_antigravity.py`

- [ ] **Step 1: Write the failing test**
Create a test file `tests/test_sync_antigravity.py` that verifies the config conversion and environment variable expansion.

```python
import json
import os
from unittest import mock
import yaml

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
    
    # Run conversion logic using mock environment
    with mock.patch.dict(os.environ, {"PWD": "/workspace"}):
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_sync_antigravity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '_scripts.sync_antigravity'` or `ImportError`.

- [ ] **Step 3: Write minimal implementation**
Create `_scripts/sync_antigravity.py`:

```python
import json
import os
import re
import sys
import yaml

def replace_env_vars(val):
    if isinstance(val, str):
        # Match both ${env:VAR} and $VAR or ${VAR}
        matches = re.findall(r"\$\{env:([^}]+)\}", val)
        for var in matches:
            val = val.replace(f"${{env:{var}}}", os.environ.get(var, ""))
        # Standard env expansion
        val = os.path.expandvars(val)
    elif isinstance(val, dict):
        return {k: replace_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [replace_env_vars(x) for x in val]
    return val

def convert_lockfile(lockfile_path, output_path):
    if not os.path.exists(lockfile_path):
        print(f"Error: {lockfile_path} not found.")
        sys.exit(1)
        
    with open(lockfile_path, "r", encoding="utf-8") as f:
        lock_data = yaml.safe_load(f)
        
    mcp_configs = lock_data.get("mcp_configs", {})
    mcp_servers = {}
    
    for name, cfg in mcp_configs.items():
        # Clean config representation for Antigravity
        server_cfg = {}
        if "command" in cfg:
            server_cfg["command"] = cfg["command"]
        if "args" in cfg:
            server_cfg["args"] = cfg["args"]
        if "env" in cfg:
            server_cfg["env"] = cfg["env"]
        if "url" in cfg:
            server_cfg["serverUrl"] = cfg["url"]
        if "headers" in cfg:
            server_cfg["headers"] = cfg["headers"]
            
        # Standardize command path resolving for typical environment executables
        if "command" in server_cfg and server_cfg["command"] == "uvx":
            # Resolve standard system uvx path if it exists
            for path in ["/home/y_ohi/.local/bin/uvx", "/usr/local/bin/uvx", "/usr/bin/uvx"]:
                if os.path.exists(path):
                    server_cfg["command"] = path
                    break
        elif "command" in server_cfg and server_cfg["command"] == "npx":
            for path in ["/home/linuxbrew/.linuxbrew/bin/npx", "/usr/local/bin/npx", "/usr/bin/npx"]:
                if os.path.exists(path):
                    server_cfg["command"] = path
                    break
                    
        # Apply environment variable replacement
        mcp_servers[name] = replace_env_vars(server_cfg)
        
    output_data = {"mcpServers": mcp_servers}
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"Successfully generated {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lockfile", default="apm.lock.yaml")
    parser.add_argument("--output", default="antigravity/mcp_config.json")
    args = parser.parse_args()
    convert_lockfile(args.lockfile, args.output)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_sync_antigravity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add _scripts/sync_antigravity.py tests/test_sync_antigravity.py
git commit -m "feat: add antigravity config converter with tests"
```

---

### Task 2: Update `apm.yml` configuration

**Files:**
- Modify: `apm.yml`

- [ ] **Step 1: Edit `apm.yml`**
Change the `skillport` MCP server definition's `SKILLPORT_SKILLS_DIR` env configuration to point to `.agents/skills`.

Modify `apm.yml` (around line 23-33):
```yaml
    - name: skillport
      title: "Skillport"
      registry: false
      transport: stdio
      command: "uvx"
      args:
        - "skillport-mcp"
      env:
        SKILLPORT_SKILLS_DIR: "${env:PWD}/.agents/skills"
      standalone: true
      enabled: true
```

- [ ] **Step 2: Run verification**
Validate the APM configuration syntax by running APM CLI checks.
Run: `apm audit`
Expected: Verification passes or indicates drift but config structure is valid.

- [ ] **Step 3: Commit**
```bash
git add apm.yml
git commit -m "config: update skillport directory in apm.yml to point to .agents/skills"
```

---

### Task 3: Clean up Makefile and Integrate Antigravity post-compile Hook

**Files:**
- Modify: `Makefile`
- Modify: `_mk/sync-agents.mk`

- [ ] **Step 1: Clean up redundant targets in `_mk/sync-agents.mk`**
Remove legacy copy/git clone targets: `install-external-skills`, `sync-skills-to-agents`, and `uninstall-superpowers`.
Also update the `sync-agents` target sequence.

Modify `_mk/sync-agents.mk`:
```diff
@@ -17,2 +17,2 @@
 .PHONY: sync-agents clean-sync-artifacts ai-setup \
-        inject-meta-prompt-opencode inject-meta-prompt-codex \
-        sync-skillport-doc link-user-agents link-agent-commands \
-        install-external-skills uninstall-superpowers clean-legacy \
-        sync-skills-to-agents
+        inject-meta-prompt-opencode inject-meta-prompt-codex \
+        sync-skillport-doc link-user-agents link-agent-commands \
+        clean-legacy
@@ -23,38 +23,2 @@
-# ============================================================
-# install-external-skills: 外部スキルのセットアップ
-# ============================================================
-install-external-skills:
-    ...
-
-uninstall-superpowers:
-    ...
@@ -60,7 +60,5 @@
 sync-agents: ## SSOTのスキル群を各エージェントの設定ファイルへ同期する
 	@echo "🔄 sync-agents: SSOT → 各エージェントへの同期を開始..."
 	@$(MAKE) clean-sync-artifacts
-	@$(MAKE) sync-skills-to-agents
 	@$(MAKE) sync-skillport-doc
 	@$(MAKE) link-user-agents
 	@$(MAKE) link-agent-commands
 	@$(MAKE) inject-meta-prompt-opencode
 	@$(MAKE) inject-meta-prompt-codex
 	@touch "$(REPO_ROOT)/.last_sync"
 	@echo "✅ sync-agents: 全エージェントへの同期が完了しました"
-
-sync-skills-to-agents:
-    ...
```

- [ ] **Step 2: Update `clean-sync-artifacts` to delete legacy external skills in `agent-skills/`**
Modify `clean-sync-artifacts` in `_mk/sync-agents.mk` to remove `agent-skills/anthropics` and `agent-skills/superpowers`:
```diff
@@ -107,3 +107,5 @@
 clean-sync-artifacts: ## 同期マーカーおよび生成されたリンク・コマンドファイルを削除する
 	@echo "🧹 clean-sync-artifacts: 同期状態をリセット中..."
 	@rm -f "$(REPO_ROOT)/.last_sync"
+	@rm -rf "$(REPO_ROOT)/agent-skills/anthropics"
+	@rm -rf "$(REPO_ROOT)/agent-skills/superpowers"
```

- [ ] **Step 3: Modify `Makefile` to run APM install/compile and sync Antigravity**
Simplify Makefile orchestration.

Modify `Makefile` to include APM command wrappers and trigger the post-compile hook:
```makefile
.PHONY: sync-agents
sync-agents: ## Run APM install and compile, followed by post-compile sync
	apm install
	apm compile
	python _scripts/sync_antigravity.py
	$(MAKE) -f _mk/sync-agents.mk sync-agents
```

- [ ] **Step 4: Run make sync-agents to test integration**
Run: `make sync-agents`
Expected: APM installs and compiles, then `_scripts/sync_antigravity.py` correctly generates `antigravity/mcp_config.json`, followed by successful completion of target-specific sync routines.

- [ ] **Step 5: Commit**
```bash
git add Makefile _mk/sync-agents.mk
git commit -m "refactor: simplify Makefile workflow and integrate APM compile and Antigravity hook"
```

---

### Task 4: Update `AVAILABLE_SKILLS.md` generation logic

**Files:**
- Modify: `_scripts/sync_agents.sh`

- [ ] **Step 1: Update skill scanning paths in `_scripts/sync_agents.sh`**
Modify the scanning logic to scan `.agents/skills/` and `agent-skills/custom/` directories to generate `AVAILABLE_SKILLS.md` instead of just `agent-skills/`.

Let's read `_scripts/sync_agents.sh` to locate the scanning command:
*(Note: Verification will be performed on the target file prior to replacement)*

- [ ] **Step 2: Run verification**
Execute `make sync-agents` to ensure `AVAILABLE_SKILLS.md` is updated with all combined skills.
Verify: Open `agent-skills/AVAILABLE_SKILLS.md` and check that it contains both custom skills and external skills (like `brainstorming`).

- [ ] **Step 3: Commit**
```bash
git add _scripts/sync_agents.sh
git commit -m "refactor: update AVAILABLE_SKILLS.md scanning directory to include APM deployed skills"
```
