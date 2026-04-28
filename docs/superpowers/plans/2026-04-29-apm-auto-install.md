# APM Auto-Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the installation of Microsoft APM and its execution during the project setup phase.

**Architecture:** Add a new `install-apm` target to the SkillPort module and integrate it into the main `setup` workflow.

**Tech Stack:** Makefile, Bash, Microsoft APM

---

### Task 1: Define APM Installation Variables

**Files:**
- Modify: `_mk/variables.mk`

- [ ] **Step 1: Add APM_INSTALL_URL to variables.mk**

```makefile
<<<<
# Helper for conditional echo
====
# APM Installation
APM_INSTALL_URL := https://aka.ms/apm-unix

# Helper for conditional echo
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add _mk/variables.mk
git commit -m "feat: add APM installation URL variable"
```

### Task 2: Implement install-apm Target

**Files:**
- Modify: `_mk/skillport.mk`

- [ ] **Step 1: Add install-apm target to skillport.mk**

```makefile
<<<<
.PHONY: skillport install-skillport setup-skillport check-skillport check-skillport-version
====
.PHONY: skillport install-skillport setup-skillport check-skillport check-skillport-version install-apm
>>>>

<<<<
        echo "✅ SkillPort のインストールが完了しました"
# SkillPort の設定（ディレクトリ作成とリンク）
====
        echo "✅ SkillPort のインストールが完了しました"

# APM (Agent Package Manager) のインストール
install-apm: ## Microsoft APM をインストール
	@if command -v apm >/dev/null 2>&1; then \
		echo "✅ APM は既にインストールされています ($$(apm --version 2>/dev/null || echo 'installed'))"; \
	else \
		echo "📦 APM をインストール中..."; \
		curl -sSL $(APM_INSTALL_URL) | sh; \
		if ! command -v apm >/dev/null 2>&1; then \
			echo "⚠️  APM インストール後に PATH が通っていない可能性があります。手動で設定を確認してください。"; \
		fi; \
	fi

# SkillPort の設定（ディレクトリ作成とリンク）
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add _mk/skillport.mk
git commit -m "feat: add install-apm target to skillport.mk"
```

### Task 3: Integrate APM into Setup Workflow

**Files:**
- Modify: `_mk/main.mk`

- [ ] **Step 1: Update setup target in main.mk**

```makefile
<<<<
setup: install-requirements
        $(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."
        @if command -v apm >/dev/null 2>&1; then \
                apm install; \
        else \
                echo "❌ APMがインストールされていません。 https://github.com/microsoft/apm に従いインストールしてください。"; \
                exit 1; \
        fi
        @$(MAKE) sync-agents
        $(Q_ECHO) "✅ dotfiles-ai のコア設定が適用されました"
====
setup: install-requirements install-apm
	$(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."
	@if command -v apm >/dev/null 2>&1; then \
		apm install; \
	else \
		echo "❌ APMのインストールまたは実行に失敗しました。"; \
		exit 1; \
	fi
	@$(MAKE) sync-agents
	$(Q_ECHO) "✅ dotfiles-ai のコア設定が適用されました"
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add _mk/main.mk
git commit -m "refactor: integrate install-apm into setup workflow"
```

### Task 4: Verification

- [ ] **Step 1: Check if apm is available**

Run: `make install-apm`
Expected: If installed, shows "already installed". If not, runs installer.

- [ ] **Step 2: Run make setup**

Run: `make setup`
Expected: Runs `install-apm`, then `apm install`, then `sync-agents`.
