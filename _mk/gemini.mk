# ============================================================
# Gemini CLI セットアップ用Makefile
# Gemini CLI のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)

.PHONY: install-packages-gemini-cli install-gemini-ecosystem

# Gemini CLI のインストール
install-packages-gemini-cli:
	@echo "♊ Gemini CLI のバージョンを確認中..."
	@LATEST_VERSION=$$(npm show @google/gemini-cli version 2>/dev/null || echo "error"); \
	CURRENT_VERSION=$$(gemini --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
	if [ "$$LATEST_VERSION" = "error" ]; then \
		echo "⚠️  最新バージョンの取得に失敗しました。インストールを試行します..."; \
		npm install -g @google/gemini-cli; \
	elif [ "$$CURRENT_VERSION" = "$$LATEST_VERSION" ]; then \
		echo "✅ Gemini CLI は既に最新バージョン ($$CURRENT_VERSION) がインストールされています。"; \
	else \
		if [ "$$CURRENT_VERSION" = "none" ]; then \
			echo "📦 Gemini CLI を新規インストールします (バージョン: $$LATEST_VERSION)"; \
		else \
			echo "🔄 Gemini CLI をアップデートします ($$CURRENT_VERSION -> $$LATEST_VERSION)"; \
		fi; \
		if ! npm install -g @google/gemini-cli; then \
			echo "❌ Gemini CLI のインストールに失敗しました"; \
			exit 1; \
		fi; \
	fi
	@# インストール確認
	@if ! command -v gemini >/dev/null 2>&1; then \
		echo "❌ Gemini CLI のインストール確認に失敗しました。PATH を確認してください。"; \
		exit 1; \
	fi

	@echo "";
	@echo "🎉 Gemini CLI のセットアップガイド:"
	@echo "1. プロジェクトディレクトリに移動: cd your-project-directory"
	@echo "2. Gemini CLI を開始: gemini"
	@echo "3. 認証方法を選択: Google Cloud認証"
	@echo "4. 初回セットアップコマンド:"
	@echo "   > summarize this project"
	@echo "   > /help"
	@echo "";
	@echo "✅ Gemini CLI のインストールが完了しました"

GEMINI_GLOBAL_MD := $(HOME_DIR)/.gemini/GEMINI.md
AGENTS_GLOBAL_MD := $(REPO_ROOT)/global-rules/AGENTS.global.md

.PHONY: link-gemini-global-md
link-gemini-global-md: ## GEMINI.md をグローバルルールにリンク
	@echo "🔗 Linking Gemini global configuration..."
	@mkdir -p $(dir $(GEMINI_GLOBAL_MD))
	@if [ -f $(GEMINI_GLOBAL_MD) ] && [ ! -L $(GEMINI_GLOBAL_MD) ]; then \
		echo "📦 Backing up existing GEMINI.md to .bak"; \
		mv $(GEMINI_GLOBAL_MD) $(GEMINI_GLOBAL_MD).bak; \
	fi
	@ln -sf $(AGENTS_GLOBAL_MD) $(GEMINI_GLOBAL_MD)
	@echo "✅ Linked $(GEMINI_GLOBAL_MD) -> $(AGENTS_GLOBAL_MD)"

.PHONY: help-gemini
help-gemini: ## Gemini の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/gemini.md)

.PHONY: check-gemini
check-gemini: ## Gemini CLI の診断を実行
	@echo "🩺 Gemini CLI の診断を開始..."
	@if command -v gemini >/dev/null 2>&1; then \
		echo "✅ Gemini CLI: $$(gemini --version 2>/dev/null)"; \
	else \
		echo "❌ Gemini CLI が見つかりません。'make install-packages-gemini-cli' を実行してください。"; \
	fi
	@if [ -L "$(HOME_DIR)/.gemini/GEMINI.md" ]; then \
		echo "✅ GEMINI.md: リンク済み ($$(readlink "$(HOME_DIR)/.gemini/GEMINI.md"))"; \
	else \
		echo "❌ GEMINI.md がリンクされていません。'make setup-gemini' を実行してください。"; \
	fi
	@if [ -f "$(HOME_DIR)/.gemini/settings.json" ]; then \
		echo "✅ settings.json: 存在します"; \
	else \
		echo "❌ settings.json が見つかりません。'make setup-gemini' を実行してください。"; \
	fi

.PHONY: setup-gemini
setup-gemini: install-gemini-ecosystem ## Gemini CLI の設定を適用
	@echo "📝 Gemini CLI の追加設定を適用中..."
	@mkdir -p "$(HOME_DIR)/.gemini"
	@if [ ! -f "$(HOME_DIR)/.gemini/settings.json" ]; then \
		if [ -f "$(REPO_ROOT)/gemini/settings.json.template" ]; then \
			cp "$(REPO_ROOT)/gemini/settings.json.template" "$(HOME_DIR)/.gemini/settings.json"; \
			echo "✅ settings.json をテンプレートから作成しました"; \
		else \
			echo "{}" > "$(HOME_DIR)/.gemini/settings.json"; \
			echo "✅ 空の settings.json を作成しました"; \
		fi \
	else \
		echo "ℹ️  settings.json は既に存在します"; \
	fi
	@echo "✅ Gemini CLI の設定が完了しました"

# Gemini エコシステム一括インストール
install-gemini-ecosystem: install-packages-gemini-cli link-gemini-global-md
	@echo "✅ Gemini エコシステムのセットアップが完了しました"

.PHONY: uninstall-gemini
uninstall-gemini: ## Gemini CLI の設定を削除
	@echo "🗑️  Gemini CLI の設定を削除中..."
	@rm -f $(HOME_DIR)/.gemini/GEMINI.md
	@rm -f $(HOME_DIR)/.gemini/settings.json
	@echo "✅ Gemini CLI の設定を削除しました"

# ========================================
# エイリアス
# ========================================

.PHONY: install-gemini-cli
install-gemini-cli: install-packages-gemini-cli  ## Gemini CLIをインストール(エイリアス)

.PHONY: gemini
gemini: install-gemini-cli  ## Gemini CLIをインストール(エイリアス)
