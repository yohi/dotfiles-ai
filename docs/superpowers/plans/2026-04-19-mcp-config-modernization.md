# MCP Configuration Modernization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address Codacy security and quality findings by removing hardcoded paths, fixing configuration inconsistencies, and making the rendering script non-destructive and more robust.

**Architecture:** 
1. Replace hardcoded absolute paths in `mcp/servers.yaml` with pre-defined placeholders (`__REPO_ROOT__`, `__HOME__`).
2. Update `_scripts/render-mcp-configs.py` to support deep-merging of JSON/JSONC/TOML configurations.
3. Decouple specific agent logic from the rendering script by using a generalized mapping system.
4. Harmonize documentation regarding configuration paths.

**Tech Stack:** Python 3, YAML, JSON5, TOML.

---

### Task 1: Fix Hardcoded Paths in `mcp/servers.yaml`

**Files:**
- Modify: `mcp/servers.yaml`

- [ ] **Step 1: Replace hardcoded project path for Claude**
Replace `/home/y_ohi/dotfiles/components/dotfiles-ai` with `__REPO_ROOT__`.

- [ ] **Step 2: Replace hardcoded home path for Filesystem server**
Replace `/home/y_ohi` with `__HOME__` in `command` and `volumes` of `filesystem` server.

- [ ] **Step 3: Verify changes**
Ensure `mcp/servers.yaml` no longer contains `/home/y_ohi`.

---

### Task 2: Harmonize Claude Configuration Paths

**Files:**
- Modify: `mcp/README.md`
- Modify: `_docs/mcp-settings.md`

- [ ] **Step 1: Update `mcp/README.md`**
Align the path for Claude Code to `.claude.json` (local) or mention it correctly.

- [ ] **Step 2: Update `_docs/mcp-settings.md`**
Change `~/.claude/config.json` to `.claude.json` to match the implementation.

---

### Task 3: Implement Deep Merge in `_scripts/render-mcp-configs.py`

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Add `deep_merge` utility function**

```python
def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base
```

- [ ] **Step 2: Use `deep_merge` in `write_json_file`**

```python
def write_json_file(path: Path, root_key: str, servers: dict[str, Any], project_key: str | None = None) -> bool:
    ...
    if project_key:
        if "projects" not in data:
            data["projects"] = {}
        if project_key not in data["projects"]:
            data["projects"][project_key] = {}
        # Use deep_merge instead of direct assignment
        deep_merge(data["projects"][project_key], {root_key: servers})
    else:
        deep_merge(data, {root_key: servers})
    ...
```

- [ ] **Step 3: Apply same logic to `write_jsonc_object_key` (if applicable)**
Actually, `write_jsonc_object_key` and `write_opencode_jsonc` use regex/marker-based replacement which is already somewhat targeted, but we should ensure they don't wipe out other keys in the same object if they manage the whole object.

---

### Task 4: Generalize URL Key Mapping in `_scripts/render-mcp-configs.py`

**Files:**
- Modify: `mcp/servers.yaml`
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Add `override_url_key` to `servers.yaml` for Gemini+Atlassian**

```yaml
  gemini:
    ...
    servers:
      ...
      atlassian: { inherit: "atlassian", url_key: "httpUrl" }
```

- [ ] **Step 2: Update script to respect per-server `url_key`**
Modify the inheritance logic to check for `url_key` in the server config.

- [ ] **Step 3: Remove hardcoded `if agent_name == "gemini" and s_name == "atlassian"`**

---

### Task 5: Improve TOML Writer

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Refactor `write_toml_file` to be more robust**
Handle data structures better and avoid simple string concatenation where possible, or at least ensure proper quoting.

---

### Task 6: Validation

- [ ] **Step 1: Run `make sync-mcp`**
Verify that the output files are generated correctly and no data loss occurs in `.claude.json`.

- [ ] **Step 2: Check diffs**
Ensure placeholders are correctly expanded.
