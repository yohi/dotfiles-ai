# Opcode Latest Version Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the source-build Opcode installation with a dynamic `.deb` package installer that fetches the latest version from GitHub.

**Architecture:** Use `curl` to query the GitHub API for the latest release, download the corresponding `.deb` asset, and install it using `apt`. The logic will be integrated into `_mk/variables.mk` for configuration and `_mk/claude.mk` for the installation target.

**Tech Stack:** Makefile, Bash, curl, apt (Debian/Ubuntu)

---

## Task 1: Update variables.mk with version detection logic

**Files:**
- Modify: `_mk/variables.mk`

- [ ] **Step 1: Define helper variables for Opcode version detection**

```makefile
# Opcode (Claude Code GUI) Version Detection
# Uses GitHub API to get the latest tag name (vX.Y.Z) and strips the 'v'
OPCODE_LATEST_TAG := $(shell curl -s https://api.github.com/repos/winfunc/opcode/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
OPCODE_VERSION := $(shell echo $(OPCODE_LATEST_TAG) | sed 's/^v//')
```

- [ ] **Step 2: Verify version detection works**

Run: `make -f _mk/variables.mk -e 'echo-version:; @echo $(OPCODE_VERSION)' echo-version`
Expected: `0.2.0` (or the current latest version)

- [ ] **Step 3: Commit**

```bash
git add _mk/variables.mk
git commit -m "refactor: add dynamic version detection for Opcode"
```

---

## Task 2: Refactor install-packages-opcode in claude.mk

**Files:**
- Modify: `_mk/claude.mk`

- [ ] **Step 1: Simplify dependencies and implement download/install flow**

Remove old build logic (clone, bun install, tauri build) and replace with `.deb` installation.

```makefile
install-packages-opcode: ## Opcode (Claude Code GUI) をインストール
        @echo "🖥️  Opcode (Claude Code GUI) のインストールを開始..."
        @if [ -z "$(OPCODE_VERSION)" ]; then echo "❌ 最新バージョンの取得に失敗しました"; exit 1; fi
        @echo "📦 最新バージョン: v$(OPCODE_VERSION)"

        # 既存バージョンの確認
        @CURRENT_VERSION=$$(/opt/opcode/opcode --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
        if [ "$$CURRENT_VERSION" = "$(OPCODE_VERSION)" ]; then \
                echo "✅ すでに最新バージョン (v$(OPCODE_VERSION)) がインストールされています"; \
        else \
                echo "📥 .deb パッケージをダウンロード中..."; \
                TEMP_DIR=$$(mktemp -d); \
                trap 'rm -rf "$$TEMP_DIR"' EXIT; \
                DEB_URL="https://github.com/winfunc/opcode/releases/download/v$(OPCODE_VERSION)/opcode_v$(OPCODE_VERSION)_linux_x86_64.deb"; \
                if curl -L -o "$$TEMP_DIR/opcode.deb" "$$DEB_URL"; then \
                        echo "🔧 インストール中 (sudo権限が必要です)..."; \
                        sudo apt-get update -q && sudo apt-get install -y "$$TEMP_DIR/opcode.deb"; \
                        echo "✅ インストール完了"; \
                        $(create_desktop_entry); \
                else \
                        echo "❌ ダウンロードに失敗しました: $$DEB_URL"; \
                        exit 1; \
                fi \
        fi
```

- [ ] **Step 2: Verify the target structure (Dry Run)**

Check the file content to ensure the `create_desktop_entry` macro and other logic are correctly preserved.

- [ ] **Step 3: Commit**

```bash
git add _mk/claude.mk
git commit -m "refactor: replace Opcode source build with .deb installer"
```

---

## Task 3: Final Verification

- [ ] **Step 1: Run the new installer**

Run: `make install-packages-opcode`
Expected: Download and install of v0.2.0 (or latest) succeeds.

- [ ] **Step 2: Verify the installation**

Run: `ls -l /opt/opcode/opcode` and `/opt/opcode/opcode --version`
Expected: Executable exists and version matches the latest.

- [ ] **Step 3: Verify Desktop Entry**

Run: `ls -l /usr/share/applications/opcode.desktop`
Expected: File exists.

- [ ] **Step 4: Final Commit and Cleanup**

```bash
git commit --allow-empty -m "chore: verify opcode installer refactoring"
```
