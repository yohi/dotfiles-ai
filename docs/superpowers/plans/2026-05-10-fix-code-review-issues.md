# Fix Code Review Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix multiple code review issues including security, credentials, model naming, and build script errors.

**Architecture:** Systematic cleanup of configuration files (`.jsonc`, `.gitignore`), scripts (`.py`), and Makefiles (`.mk`).

**Tech Stack:** Python, Makefile, Bash, JSONC.

---

### Task 1: Security & Credentials - Git & Env

**Files:**
- Modify: `.gitignore`
- Modify: `.env` (Clear secrets)
- Create: `.env.example`

- [ ] **Step 1: Update .gitignore to include .sisyphus/**
    - Add `.sisyphus/` entry.

- [ ] **Step 2: Create .env.example with placeholders**
    - Create a clean `.env.example` file based on existing keys but with safe values.

- [ ] **Step 3: Remove secrets from .env**
    - Replace real values with placeholders in `.env`.

- [ ] **Step 4: Verify .gitignore and .env state**
    - Run `git status` to ensure `.sisyphus` is ignored and `.env` is safe.

- [ ] **Step 5: Commit**
    ```bash
    git add .gitignore .env.example .env
    git commit -m "sec: remove secrets and improve gitignore"
    ```

### Task 2: Security & Permissions in opencode.jsonc

**Files:**
- Modify: `opencode/opencode.jsonc`

- [ ] **Step 1: Update permissions key from "shell" to "bash"**
    - Change `"shell"` object under `"permission"` to `"bash"`.

- [ ] **Step 2: Add missing security deny rules**
    - Add `su *`, `curl * | sh`, etc.

- [ ] **Step 3: Tighten git add rules**
    - Deny `git add *`, `-A`, `--all`, `-u`, `:/`.

- [ ] **Step 4: Remove hardcoded Authorization header**
    - Replace literal token with placeholder `Bearer ${env:MCP_GATEWAY_TOKEN}` or similar.

- [ ] **Step 5: Verify opencode.jsonc syntax**
    - Run a JSONC validator or simple `jq` if available.

- [ ] **Step 6: Commit**
    ```bash
    git add opencode/opencode.jsonc
    git commit -m "sec: harden opencode permissions and remove hardcoded tokens"
    ```

### Task 3: Model IDs & Configuration Inconsistency

**Files:**
- Modify: `opencode/oh-my-openagent.jsonc`
- Modify: `opencode/opencode.jsonc` (ESLint & Whitelist)

- [ ] **Step 1: Fix model ID inconsistencies in oh-my-openagent.jsonc**
    - Correct `nvidia/minimax-m2.7`, `kimi-k2.7`, and missing `@cf` prefixes.

- [ ] **Step 2: Resolve Atlas vs task_system contradiction**
    - Re-enable `experimental.task_system: true` in `oh-my-openagent.jsonc`.

- [ ] **Step 3: Update ESLint formatter in opencode.jsonc**
    - Change `--format compact` to `--format stylish`.

- [ ] **Step 4: Update OpenAI/Google whitelists if needed**
    - Ensure IDs like `gpt-5.5` are properly handled or updated to latest project standards.

- [ ] **Step 5: Verify config integrity**
    - Run `python3 _scripts/test_configs_integrity.py` (if it exists).

- [ ] **Step 6: Commit**
    ```bash
    git add opencode/oh-my-openagent.jsonc opencode/opencode.jsonc
    git commit -m "fix: resolve model inconsistencies and task_system contradiction"
    ```

### Task 4: Fix render-mcp-configs.py

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Add type check for header values**
    - Ensure `v` is `str` before `"__AUTH_TOKEN__" in v`.

- [ ] **Step 2: Fix secret injection logic**
    - Unconditionally use environment-variable placeholder instead of injecting real token.

- [ ] **Step 3: Run test_render_mcp.py**
    - `python3 _scripts/test_render_mcp.py`

- [ ] **Step 4: Commit**
    ```bash
    git add _scripts/render-mcp-configs.py
    git commit -m "fix: improve render-mcp-configs.py type safety and security"
    ```

### Task 5: Fix Makefiles (opencode.mk & mcp.mk)

**Files:**
- Modify: `_mk/opencode.mk`
- Modify: `_mk/mcp.mk`

- [ ] **Step 1: Fix variable names and syntax in opencode.mk**
    - Correct `$$act`/`$$exp` to `$$actual`/`$$expected`. Fix line continuations.

- [ ] **Step 2: Fix sync-mcp dependencies in mcp.mk**
    - Make `restart-mcp` depend on `render-mcp`.

- [ ] **Step 3: Add render-mcp to .PHONY**
    - Update `.PHONY` in `_mk/mcp.mk`.

- [ ] **Step 4: Verify make targets**
    - Run `make render-mcp` and `make check-opencode`.

- [ ] **Step 5: Commit**
    ```bash
    git add _mk/opencode.mk _mk/mcp.mk
    git commit -m "fix: correct Makefile syntax and dependencies"
    ```
