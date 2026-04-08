# Makefile Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Makefileを「薄いエントリーポイント」として整理し、ロジックを `_mk/main.mk` に集約することで、親プロジェクトとの整合性とメンテナンス性を向上させる。

**Architecture:** 
- `Makefile` は `include` のみに特化。
- `_mk/main.mk` が全体のワークフロー（`all`, `install`, `setup`, `sync` 等）をオーケストレートする。
- 既存のコンポーネント用モジュール（`claude.mk`, `gemini.mk` 等）のインターフェースは維持。

**Tech Stack:** GNU Make, Bash

---

## Task 1: `_mk/main.mk` の再構築

**Files:**
- Modify: `_mk/main.mk`

- [ ] **Step 1: 既存のロジックの統合と整理**

`_mk/main.mk` の冒頭に、親プロジェクトが期待する標準ターゲットを定義し、`Makefile` にあった `install-ai` や `setup-ai` の内容を適切に組み込みます。

```makefile
.PHONY: all install install-agents install-ides setup setup-agents setup-ides mcp-render link clean-internal install-requirements lint init sync secrets status

# --- Standard Entry Points ---

all: install setup sync ## [親プロジェクト用] 全てのインストール、セットアップ、同期を実行

install: install-agents install-ides ## [親プロジェクト用] エージェントとIDEツールのインストール

setup: setup-agents setup-ides ## [親プロジェクト用] 設定の適用
	@$(MAKE) mcp-render
	@$(MAKE) setup-superpowers
	@$(MAKE) sync-agents
	@$(MAKE) sync-mcp
	@echo "✅ dotfiles-ai のコア設定が適用されました"

sync: ## [親プロジェクト用] リポジトリとエージェントの同期
	@echo "🔄 リポジトリを最新に同期中..."
	@git pull --rebase || (echo "❌ git pull --rebase に失敗しました"; exit 1)
	@$(MAKE) sync-agents

# --- Implementation Details (existing logic updated) ---

install-agents:
	@echo "📦 dotfiles-ai エージェントバイナリをインストール中..."
	$(MAKE) install-packages-claude-code
	$(MAKE) install-packages-gemini-cli
	$(MAKE) install-packages-codex
	$(MAKE) install-packages-opencode
	$(MAKE) install-packages-superclaude

install-ides:
	@echo "📦 dotfiles-ai IDE ツールをインストール中..."
	$(MAKE) install-packages-cursor

setup-agents:
	@echo "🚀 dotfiles-ai エージェント設定をセットアップ中..."
	@if [ ! -d node_modules ]; then npm install; fi
	$(MAKE) setup-claude
	$(MAKE) setup-supergemini
	$(MAKE) setup-codex
	$(MAKE) setup-opencode
	$(MAKE) setup-antigravity
	$(MAKE) setup-docker-mcp

setup-ides:
	$(MAKE) setup-cursor
	$(MAKE) setup-vscode

# ... (その他の既存ターゲット: mcp-render, link, clean-internal, lint, init, secrets, status は維持)
```

- [ ] **Step 2: 変更의 保存とコミット**

```bash
git add _mk/main.mk
git commit -m "refactor(make): consolidate core logic into _mk/main.mk"
```

---

## Task 2: `Makefile` の簡素化

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: `Makefile` を include 中心に書き換え**

トップレベルの `Makefile` からロジックを削除し、純粋なエントリーポイントにします。

```makefile
# 1. Base Rules (Provided by parent or local)
include _mk/core.mk
include _mk/help.mk

# 2. Variables & Idempotency
-include _mk/variables.mk
-include _mk/idempotency.mk

# 3. Orchestrator (Main Workflow)
include _mk/main.mk

# 4. Component Modules
-include _mk/claude.mk
-include _mk/gemini.mk
-include _mk/codex.mk
-include _mk/opencode.mk
-include _mk/antigravity.mk
-include _mk/superclaude.mk
-include _mk/skillport.mk
-include _mk/sync-agents.mk
-include _mk/mcp.mk
-include _mk/superpowers.mk
-include _mk/ide-cursor.mk
-include _mk/ide-vscode.mk
-include _mk/test-ide-cursor.mk
```

- [ ] **Step 2: 変更の保存とコミット**

```bash
git add Makefile
git commit -m "refactor(make): simplify top-level Makefile to include-only structure"
```

---

## Task 3: `_mk/variables.mk` のクリーンアップ

**Files:**
- Modify: `_mk/variables.mk`

- [ ] **Step 1: 重複する `.PHONY` の削除**

`core.mk` や `main.mk` で定義されているターゲットの `.PHONY` 宣言を削除し、変数定義のみに整理します。

```makefile
# Global Variables
REQUIRE_NODEJS := 1
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON := uv run --with-requirements requirements.txt

# (Remove .PHONY: all help setup install clean ... as they are in core.mk/main.mk)
```

- [ ] **Step 2: 変更の保存とコミット**

```bash
git add _mk/variables.mk
git commit -m "refactor(make): cleanup .PHONY in variables.mk"
```

---

## Task 4: 最終検証

**Files:**
- None

- [ ] **Step 1: `make help` の確認**

Run: `make help`
Expected: 全てのカテゴリ（Main / Common, AI Tools, etc.）が正しく表示されること。

- [ ] **Step 2: ドライランによる順序確認**

Run: `make -n all`
Expected: `install` -> `setup` -> `sync` の順序で実行されることが出力から確認できること。

- [ ] **Step 3: コミット**

```bash
git commit --allow-empty -m "chore(make): reorganization verified"
```
