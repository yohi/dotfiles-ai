# Comprehensive System Hardening and Issue Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve a series of identified code review issues ranging from security (secrets in repo) to robustness (error handling, version pinning) and documentation consistency.

**Architecture:** 
- Surgical fixes to Makefiles, Python scripts, and Shell scripts to improve error handling and environment portability.
- Pinning Docker image dependencies for reproducibility.
- Normalizing configurations and expanding documentation for better maintainability.
- Moving secrets from hardcoded strings to environment variable references.

**Tech Stack:** Makefile, Python, Bash, Docker, JSONC, Markdown

---

### Task 1: Fix Security and Path Issues in OpenCode Configuration

**Files:**
- Modify: `opencode/opencode.jsonc`

- [ ] **Step 1: Replace hardcoded secret with environment variable reference**
  Remove the Bearer token and use a placeholder or env var syntax if supported, or instruction to the user.
  Note: OpenCode `.jsonc` often supports `${ENV_VAR}`.

```json
      "headers": {
        "Authorization": "Bearer ${OPCODE_GATEWAY_TOKEN}"
      },
```

- [ ] **Step 2: Normalize instructions path**
  Change `"docs/global-rules/AGENTS.global.md"` to `"global-rules/AGENTS.global.md"`.

- [ ] **Step 3: Commit Task 1**

```bash
git add opencode/opencode.jsonc
git commit -m "fix: remove hardcoded secret and normalize paths in opencode config"
```

---

### Task 2: Robustness Improvements in Makefiles (variables, gemini, claude)

**Files:**
- Modify: `_mk/variables.mk`
- Modify: `_mk/gemini.mk`
- Modify: `_mk/claude.mk`

- [ ] **Step 1: Harden curl in variables.mk**
  Add `-fS --max-time 10 --retry 3` to `OPCODE_LATEST_TAG` and ensure pipeline fails on error.

```makefile
OPCODE_LATEST_TAG = $(shell curl -fS --max-time 10 --retry 3 https://api.github.com/repos/winfunc/opcode/releases/latest 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/' || echo "FAILED")
```

- [ ] **Step 2: Add existence check and fallback for gemini settings.json**
  Update line 90 of `_mk/gemini.mk` to check source before linking, and provide fallback.

```makefile
	@if [ -e "$(REPO_ROOT)/gemini/settings.json" ]; then \
		ln -sf "$(REPO_ROOT)/gemini/settings.json" "$(HOME_DIR)/.gemini/settings.json"; \
	else \
		mkdir -p "$(HOME_DIR)/.gemini"; \
		echo '{"mcpServers": {}}' > "$(HOME_DIR)/.gemini/settings.json"; \
		echo "⚠️  Warning: gemini/settings.json not found. Created a default one."; \
	fi
```

- [ ] **Step 3: Fix shell syntax in claude.mk**
  Ensure the inner `if` block in `install-packages-opcode` is properly terminated with a semicolon before the outer `fi`.

```makefile
			echo "✅ インストール完了"; \
			$(create_desktop_entry); \
		else \
			echo "❌ ダウンロードに失敗しました: $$DEB_URL"; \
			exit 1; \
		fi; \
	fi
```

- [ ] **Step 4: Commit Task 2**

```bash
git add _mk/variables.mk _mk/gemini.mk _mk/claude.mk
git commit -m "fix: harden Makefiles with better error handling and path resolution"
```

---

### Task 3: Reliability in Scripts (mcp-watchdog, render-mcp, setup-docker)

**Files:**
- Modify: `_scripts/mcp-watchdog.sh`
- Modify: `_scripts/render-mcp-configs.py`
- Modify: `_scripts/setup-docker-mcp.sh`

- [ ] **Step 1: Update watchdog endpoint to /sse**
  Change `GATEWAY_URL` in `_scripts/mcp-watchdog.sh`.

```bash
GATEWAY_URL="http://127.0.0.1:10888/sse"
```

- [ ] **Step 2: Fix symlink and directory handling in render-mcp-configs.py**
  Add `mkdir` for catalogs and use `is_symlink()` in `target.exists()` check.

```python
    (mcp_dir / "catalogs").mkdir(parents=True, exist_ok=True)
    (mcp_dir / "catalogs" / "custom.yaml").write_text(...)
    
    # ... later
    if target.exists() or target.is_symlink():
        target.unlink()
```

- [ ] **Step 3: Add uv check in setup-docker-mcp.sh**
  Implement fallback to `python3` if `uv` is missing.

```bash
if command -v uv >/dev/null 2>&1; then
    uv run python3 "$REPO_ROOT/_scripts/render-mcp-configs.py"
else
    python3 "$REPO_ROOT/_scripts/render-mcp-configs.py"
fi
```

- [ ] **Step 4: Commit Task 3**

```bash
git add _scripts/mcp-watchdog.sh _scripts/render-mcp-configs.py _scripts/setup-docker-mcp.sh
git commit -m "fix: improve reliability and portability of setup and watchdog scripts"
```

---

### Task 4: Documentation Consistency and Acronym Expansion

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/plans/2026-05-03-opcode-installer-refactor.md`
- Modify: `docs/superpowers/specs/2026-05-03-opcode-installer-redesign.md`

- [ ] **Step 1: Expand APM in AGENTS.md**
  Find `apm.yml` reference and add "(Agent Package Manager)".

- [ ] **Step 2: Fix header levels in opcode-installer-refactor.md**
  Change `### Task 1` to `## Task 1` (MD001).

- [ ] **Step 3: Align filenames in refactor plan**
  Change `opcode_$(OPCODE_VERSION)_amd64.deb` to `opcode_v$(OPCODE_VERSION)_linux_x86_64.deb` to match implementation.

- [ ] **Step 4: Align variable and filenames in redesign spec**
  Change `OPCODE_LATEST` to `OPCODE_VERSION`.
  Change `opcode_$(VERSION)_amd64.deb` to `opcode_v$(OPCODE_VERSION)_linux_x86_64.deb`.

- [ ] **Step 5: Commit Task 4**

```bash
git add AGENTS.md docs/superpowers/
git commit -m "docs: align documentation with implementation and expand acronyms"
```

---

### Task 5: Reproducible Docker Builds

**Files:**
- Modify: `mcp/Dockerfile.chronos-graph`
- Modify: `mcp/Dockerfile.nexus`

- [ ] **Step 1: Pin chronos-graph version**
  Add `@v0.1.0` (or similar stable ref) to the git install line.

```dockerfile
RUN uv pip install --system git+https://github.com/yohi/chronos-graph.git@v0.1.0
```

- [ ] **Step 2: Correct nexus package and pin version**
  Change `@yohi/nexus@latest` to actual package name (likely `@winfunc/nexus`) and pin version.

```dockerfile
RUN npm install -g @winfunc/nexus@0.1.0 typescript@5.4.5
```

- [ ] **Step 3: Commit Task 5**

```bash
git add mcp/Dockerfile.*
git commit -m "chore: pin dependencies in Dockerfiles for reproducible builds"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Run all tests**
  Run: `make test`

- [ ] **Step 2: Run Lint**
  Run: `make lint`

- [ ] **Step 3: Verify the whole system (Manual check of generated configs)**
  Run: `make sync-mcp`
