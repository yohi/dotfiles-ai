# ============================================================
# Codex CLI セットアップ用Makefile
# ~/.codex ディレクトリの管理と設定ファイルの同期を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)
CODEX_DOT_DIR := $(HOME_DIR)/.codex
CODEX_REPO_DIR := $(REPO_ROOT)/codex

.PHONY: setup-codex sync-codex uninstall-codex check-codex install-packages-codex

# Codex CLI のインストール
install-packages-codex: ## Codex CLI のインストール / アップデート
	@echo "🧠 Codex CLI のバージョンを確認中..."
	@if ! command -v npm >/dev/null 2>&1; then \
		echo "❌ npm が見つかりません。先に Node.js/npm をインストールしてください"; \
		exit 1; \
	fi
	@LATEST_VERSION=$$(npm show @openai/codex version 2>/dev/null || echo "error"); \
	CURRENT_VERSION=$$(codex --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
	if [ "$$LATEST_VERSION" != "error" ] && [ "$$CURRENT_VERSION" = "$$LATEST_VERSION" ]; then \
		echo "✅ Codex CLI は既に最新バージョン ($$CURRENT_VERSION) がインストールされています。"; \
		exit 0; \
	fi; \
	if [ "$$LATEST_VERSION" = "error" ]; then \
		echo "⚠️  最新バージョンの取得に失敗しました。インストールを試行します..."; \
		INSTALL_PKG="@openai/codex"; \
	else \
		if [ "$$CURRENT_VERSION" = "none" ]; then \
			echo "📦 Codex CLI を新規インストールします (バージョン: $$LATEST_VERSION)"; \
		else \
			echo "🔄 Codex CLI をアップデートします ($$CURRENT_VERSION -> $$LATEST_VERSION)"; \
		fi; \
		INSTALL_PKG="@openai/codex@$$LATEST_VERSION"; \
	fi; \
	if ! npm install -g "$$INSTALL_PKG"; then \
		echo "❌ Codex CLI のインストールに失敗しました"; \
		exit 1; \
	fi
# Codex CLI のセットアップ
setup-codex: ## ~/.codex を実体化し、設定ファイルをリポジトリからリンクする
	@echo "🚀 Codex CLI のセットアップを開始..."
	
	@# 1. ~/.codex がシンボリックリンクなら、内容を待避して実体ディレクトリに置き換える
	@if [ -L "$(CODEX_DOT_DIR)" ]; then \
		echo "🔗 現在の ~/.codex はシンボリックリンクです。実体化を試みます..."; \
		(set -e; \
		 temp_dir=$$(mktemp -d); \
		 trap 'rm -rf "$$temp_dir"' EXIT; \
		 cp -a "$(CODEX_DOT_DIR)/." "$$temp_dir/"; \
		 rm -f "$(CODEX_DOT_DIR)"; \
		 mkdir -p "$(CODEX_DOT_DIR)"; \
		 cp -a "$$temp_dir/." "$(CODEX_DOT_DIR)/"; \
		 echo "✅ ~/.codex を実体ディレクトリに変換しました"); \
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
	@mkdir -p "$(CODEX_DOT_DIR)"
	
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
		if [ -d "$(CODEX_DOT_DIR)/rules" ] && [ ! -L "$(CODEX_DOT_DIR)/rules" ]; then \
			mv "$(CODEX_DOT_DIR)/rules" "$(CODEX_DOT_DIR)/rules.bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "  ⚠️  Existing rules/ backed up"; \
		fi; \
		ln -sfn "$(CODEX_REPO_DIR)/rules" "$(CODEX_DOT_DIR)/rules"; \
		echo "  ✅ rules/ -> $(CODEX_REPO_DIR)/rules"; \
	fi

	@# skills/ (ディレクトリごとリンク)
	@if [ -d "$(CODEX_REPO_DIR)/skills" ]; then \
		if [ -d "$(CODEX_DOT_DIR)/skills" ] && [ ! -L "$(CODEX_DOT_DIR)/skills" ]; then \
			mv "$(CODEX_DOT_DIR)/skills" "$(CODEX_DOT_DIR)/skills.bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "  ⚠️  Existing skills/ backed up"; \
		fi; \
		ln -sfn "$(CODEX_REPO_DIR)/skills" "$(CODEX_DOT_DIR)/skills"; \
		echo "  ✅ skills/ -> $(CODEX_REPO_DIR)/skills"; \
	fi

	@# .personality_migration
	@if [ -f "$(CODEX_REPO_DIR)/.personality_migration" ]; then \
		ln -sf "$(CODEX_REPO_DIR)/.personality_migration" "$(CODEX_DOT_DIR)/.personality_migration"; \
		echo "  ✅ .personality_migration -> $(CODEX_REPO_DIR)/.personality_migration"; \
	fi

	@echo "✅ 同期が完了しました"

# アンインストール
uninstall-codex: ## 設定ファイルのリンクを解除する（実体ファイルは残す）
	@echo "🗑️  Codex 設定ファイルのリンクを解除中..."
	@if [ -L "$(CODEX_DOT_DIR)/config.toml" ]; then rm -f "$(CODEX_DOT_DIR)/config.toml"; fi
	@if [ -L "$(CODEX_DOT_DIR)/AGENTS.md" ]; then rm -f "$(CODEX_DOT_DIR)/AGENTS.md"; fi
	@if [ -L "$(CODEX_DOT_DIR)/rules" ]; then rm -rf "$(CODEX_DOT_DIR)/rules"; fi
	@if [ -L "$(CODEX_DOT_DIR)/skills" ]; then rm -rf "$(CODEX_DOT_DIR)/skills"; fi
	@if [ -L "$(CODEX_DOT_DIR)/.personality_migration" ]; then rm -f "$(CODEX_DOT_DIR)/.personality_migration"; fi
	@echo "✅ リンクを解除しました。実体データは保持されています"

# Codex CLI の起動
.PHONY: run-codex
run-codex: ## Codex CLI を起動
	@if [ -f .env ]; then \
		set -a; \
		. ./.env; \
		set +a; \
	fi; \
	echo "🚀 Starting Codex CLI..."; \
	codex

# 状態確認
check-codex: ## Codex の設定状態を確認
	@echo "🔍 Codex 設定状態の確認..."
	@ls -ld "$(CODEX_DOT_DIR)"
	@ls -l "$(CODEX_DOT_DIR)/config.toml" "$(CODEX_DOT_DIR)/AGENTS.md" "$(CODEX_DOT_DIR)/rules" "$(CODEX_DOT_DIR)/.personality_migration" 2>/dev/null || true
