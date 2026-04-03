# ============================================================
# Codex CLI セットアップ用Makefile
# ~/.codex ディレクトリの管理と設定ファイルの同期を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)
CODEX_DOT_DIR := $(HOME_DIR)/.codex
CODEX_REPO_DIR := $(REPO_ROOT)/codex

.PHONY: setup-codex sync-codex uninstall-codex check-codex

# Codex CLI のセットアップ
setup-codex: ## ~/.codex を実体化し、設定ファイルをリポジトリからリンクする
	@echo "🚀 Codex CLI のセットアップを開始..."
	
	@# 1. ~/.codex がシンボリックリンクなら、内容を待避して実体ディレクトリに置き換える
	@if [ -L "$(CODEX_DOT_DIR)" ]; then \
		echo "🔗 現在の ~/.codex はシンボリックリンクです。実体化を試みます..."; \
		temp_dir="$$(mktemp -d)"; \
		cp -a "$(CODEX_DOT_DIR)/." "$$temp_dir/"; \
		rm -f "$(CODEX_DOT_DIR)"; \
		mkdir -p "$(CODEX_DOT_DIR)"; \
		cp -a "$$temp_dir/." "$(CODEX_DOT_DIR)/"; \
		rm -rf "$$temp_dir"; \
		echo "✅ ~/.codex を実体ディレクトリに変換しました"; \
	else \
		mkdir -p "$(CODEX_DOT_DIR)"; \
		echo "✅ ~/.codex ディレクトリを確認しました"; \
	fi

	@# 2. 設定ファイルの同期（リンク作成）
	@$(MAKE) sync-codex

	@echo "🎉 Codex CLI のセットアップが完了しました"

# 設定ファイルの同期（個別リンク作成）
sync-codex: ## リポジトリ内の設定ファイルを ~/.codex へ個別にリンクする
	@echo "🔄 Codex 設定ファイルの同期中..."
	
	@# config.toml
	@if [ -f "$(CODEX_REPO_DIR)/config.toml" ]; then \
		ln -sf "$(CODEX_REPO_DIR)/config.toml" "$(CODEX_DOT_DIR)/config.toml"; \
		echo "  ✅ config.toml -> $(CODEX_REPO_DIR)/config.toml"; \
	fi

	@# AGENTS.md (SSOT)
	@if [ -f "$(CODEX_REPO_DIR)/AGENTS.md" ]; then \
		ln -sf "$(CODEX_REPO_DIR)/AGENTS.md" "$(CODEX_DOT_DIR)/AGENTS.md"; \
		echo "  ✅ AGENTS.md -> $(CODEX_REPO_DIR)/AGENTS.md"; \
	fi

	@# rules/ (ディレクトリごとリンク)
	@if [ -d "$(CODEX_REPO_DIR)/rules" ]; then \
		ln -sfn "$(CODEX_REPO_DIR)/rules" "$(CODEX_DOT_DIR)/rules"; \
		echo "  ✅ rules/ -> $(CODEX_REPO_DIR)/rules"; \
	fi

	@# version.json
	@if [ -f "$(CODEX_REPO_DIR)/version.json" ]; then \
		ln -sf "$(CODEX_REPO_DIR)/version.json" "$(CODEX_DOT_DIR)/version.json"; \
		echo "  ✅ version.json -> $(CODEX_REPO_DIR)/version.json"; \
	fi

	@echo "✅ 同期が完了しました"

# アンインストール
uninstall-codex: ## 設定ファイルのリンクを解除する（実体ファイルは残す）
	@echo "🗑️  Codex 設定ファイルのリンクを解除中..."
	@rm -f "$(CODEX_DOT_DIR)/config.toml"
	@rm -f "$(CODEX_DOT_DIR)/AGENTS.md"
	@rm -f "$(CODEX_DOT_DIR)/rules"
	@rm -f "$(CODEX_DOT_DIR)/version.json"
	@echo "✅ リンクを解除しました。~/.codex 内の実体データは保持されています"

# 状態確認
check-codex: ## Codex の設定状態を確認
	@echo "🔍 Codex 設定状態の確認..."
	@ls -ld "$(CODEX_DOT_DIR)"
	@ls -l "$(CODEX_DOT_DIR)/config.toml" "$(CODEX_DOT_DIR)/AGENTS.md" "$(CODEX_DOT_DIR)/rules" 2>/dev/null || true
