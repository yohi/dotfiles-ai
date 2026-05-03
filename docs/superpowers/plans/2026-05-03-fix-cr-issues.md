# Fix Code Review Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address 6 code review issues to improve system stability, robustness, and performance.

**Architecture:** 
1. Enhance Python scripts with proper exit code propagation and validation.
2. Optimize Makefiles by introducing lazy evaluation and robust version checks.
3. Align package naming with specifications.

**Tech Stack:** Python, GNU Make, Shell (bash/grep)

---

### Task 1: Improve render-mcp-configs.py (Issues 1, 5, 6)

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [x] **Step 1: Fix exit code propagation**
  Update the entry point to use `sys.exit(main())`.

```python
if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [x] **Step 2: Add validation for required environment variables**
  Update `_get_env` to raise `ValueError` if a variable is missing and no default is provided.

```python
        def _get_env(m: Match[str]) -> str:
            v, d = m.group(1), m.group(2)
            val = os.environ.get(v)
            if val is not None:
                return cast(str, val)
            if d is not None:
                return cast(str, d)
            raise ValueError(f"Required environment variable '${{{v}}}' is not set and has no default.")
```

- [x] **Step 3: Improve systemd service deployment error handling**
  Update `deploy_systemd_service` to print an error and exit if the source path does not exist.

```python
def deploy_systemd_service(
    src_path: Path, dest_dir: Path, repo_root: str, enabled_servers: str
) -> None:
    if not src_path.exists():
        print(f"❌ Error: systemd service template not found: {src_path}")
        import sys
        sys.exit(1)
    # ... rest remains same
```

- [x] **Step 4: Verify Task 1 changes**
  Run existing tests and check if they still pass (some might need update if they relied on empty strings).
  Run: `uv run python _scripts/test_render_mcp.py`

---

### Task 2: Optimize and Fix Makefiles (Issues 2, 3, 4)

**Files:**
- Modify: `_mk/variables.mk`
- Modify: `_mk/claude.mk`

- [x] **Step 1: Use lazy evaluation for GitHub API requests in variables.mk**
  Change `:=` to `=` for `OPCODE_LATEST_TAG` to prevent API calls on every `make` invocation.

```makefile
OPCODE_LATEST_TAG = $(shell curl -s https://api.github.com/repos/winfunc/opcode/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
```

- [x] **Step 2: Implement robust version comparison in claude.mk**
  Update `install-packages-opcode` to normalize the version string from `opcode --version`.

```makefile
        # 既存バージョンの確認
        @CURRENT_VERSION=$$(/opt/opcode/opcode --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
        if [ "$$CURRENT_VERSION" = "$(OPCODE_VERSION)" ]; then \
```

- [x] **Step 3: Align .deb filename with specifications in claude.mk**
  Update `DEB_URL` to use `opcode_$(OPCODE_VERSION)_amd64.deb`.

```makefile
                DEB_URL="https://github.com/winfunc/opcode/releases/download/v$(OPCODE_VERSION)/opcode_$(OPCODE_VERSION)_amd64.deb"; \
```

- [x] **Step 4: Verify Task 2 changes**
  Run `make help` and verify no network activity/delay occurs.
  Run `make help-claude` and verify it works.
  (Optional) Run `make install-packages-opcode` if in a compatible environment.

---

### Task 3: Final Verification and Commit

- [x] **Step 1: Run all integrity checks**
  Run: `make test`

- [x] **Step 2: Commit all changes**
  Run: `git add . && git commit -m "fix: address code review issues for system stability and performance"`
