# ============================================================
# Gemini CLI / SuperGemini セットアップ用Makefile
# Gemini CLI、SuperGemini Framework のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)

.PHONY: install-packages-gemini-cli install-packages-supergemini install-gemini-ecosystem

# install-packages-supergemini を setup-supergemini のエイリアスとして定義
install-packages-supergemini: setup-supergemini

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

# SuperGemini (Gemini CLI Framework) のセットアップ
.PHONY: setup-supergemini
setup-supergemini:
	@$(MAKE) link-gemini-global-md
	@echo "🚀 SuperGemini (Gemini CLI Framework) のセットアップを開始..."

	# Gemini CLI の確認
	@echo "🔍 Gemini CLI の確認中..."
	@if ! command -v gemini >/dev/null 2>&1; then \
		echo "⚠️  Gemini CLI がインストールされていません。設定のみ進行します。"; \
	else \
		echo "✅ Gemini CLI が見つかりました"; \
	fi

	# SuperGeminiフレームワークのセットアップ
	@echo "⚙️  SuperGemini フレームワークをセットアップ中..."
	@export PATH="$$HOME/.local/bin:$$PATH"; \
	echo "🔧 SuperGemini セットアップ準備中..."; \
	echo "ℹ️  フレームワークファイル、ユーザーツール、Gemini CLI設定をシンボリックリンクで構成します"; \
	\
	echo "📁 必要なディレクトリを作成中..."; \
	mkdir -p $(HOME_DIR)/.gemini/ || true; \
	mkdir -p $(HOME_DIR)/.gemini/user-tools/ || true; \
	\
	echo "🔗 シンボリックリンクを作成中..."; \
	# SuperGemini本体へのリンク \
	ln -sf $(REPO_ROOT)/gemini/supergemini $(HOME_DIR)/.gemini/supergemini || true; \
	# 各種ディレクトリへのリンク \
	ln -sfn $(REPO_ROOT)/gemini/Core $(HOME_DIR)/.gemini/core || true; \
	ln -sf $(REPO_ROOT)/gemini/supergemini/Hooks $(HOME_DIR)/.gemini/hooks || true; \
	# 重要なファイルへの直接リンク \
	\
	echo "📝 カスタムツールファイルを作成中..."; \
	cp -f $(REPO_ROOT)/gemini/supergemini/Commands/help.md $(HOME_DIR)/.gemini/user-tools/user-help.md 2>/dev/null || \
	printf "import-help: # /user-help コマンド\n\nSuperGeminiフレームワークのコマンド一覧を表示します。\n" > $(HOME_DIR)/.gemini/user-tools/user-help.md; \
	\
	cp -f $(REPO_ROOT)/gemini/supergemini/Commands/analyze.md $(HOME_DIR)/.gemini/user-tools/user-analyze.md 2>/dev/null || \
	printf "import-analyze: # /user-analyze コマンド\n\nコードや機能を分析します。\n" > $(HOME_DIR)/.gemini/user-tools/user-analyze.md; \
	\
	cp -f $(REPO_ROOT)/gemini/supergemini/Commands/implement.md $(HOME_DIR)/.gemini/user-tools/user-implement.md 2>/dev/null || \
	printf "import-implement: # /user-implement コマンド\n\n新機能を実装します。\n" > $(HOME_DIR)/.gemini/user-tools/user-implement.md; \
	\
	echo "🔧 Gemini CLI設定ファイルを更新中..."; \
	if [ -L "$(HOME_DIR)/.gemini/settings.json" ]; then \
		rm -f "$(HOME_DIR)/.gemini/settings.json"; \
	elif [ -f "$(HOME_DIR)/.gemini/settings.json" ]; then \
		mv "$(HOME_DIR)/.gemini/settings.json" "$(HOME_DIR)/.gemini/settings.json.backup.$$(date +%Y%m%d_%H%M%S)"; \
	fi; \
	ln -sf "$(REPO_ROOT)/gemini/settings.json" "$(HOME_DIR)/.gemini/settings.json"; \
	\
	echo "✅ SuperGemini フレームワークのシンボリックリンク設定が完了しました";
	$(Q_ECHO) ""
	$(Q_ECHO) "✨ SuperGemini のセットアップが完了しました！"
	$(Q_ECHO) "💡 使い方を確認するには 'make help-gemini' を実行してください。"

.PHONY: help-gemini
help-gemini: ## Gemini の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/gemini.md)

# Gemini エコシステム一括インストール
install-gemini-ecosystem:
	@echo "🌟 Gemini エコシステム一括インストールを開始..."
	@echo "";

	# Step 1: Gemini CLI のインストール
	@echo "📋 Step 1/2: Gemini CLI をインストール中..."
	@$(MAKE) install-packages-gemini-cli
	@echo "✅ Gemini CLI のインストールが完了しました"
	@echo "";

	# Step 2: SuperGemini のセットアップ
	@echo "📋 Step 2/2: SuperGemini をセットアップ中..."
	@$(MAKE) setup-supergemini
	@echo "✅ SuperGemini のセットアップが完了しました"
	@echo "";

	# 最終確認
	@echo "🔍 インストール結果の確認中..."
	@export PATH="$$HOME/.local/bin:$$PATH"; \
	if command -v gemini >/dev/null 2>&1; then \
		echo "Gemini CLI: ✅ $$(gemini --version 2>/dev/null || echo "インストール済み")"; \
	else \
		echo "Gemini CLI: ❌ 未確認"; \
	fi; \
	if [ -f "$$HOME/.gemini/GEMINI.md" ]; then \
		echo "SuperGemini: ✅ インストール済み"; \
	else \
		echo "SuperGemini: ❌ 未確認"; \
	fi

	@echo "";
	@echo "🎉 Gemini エコシステムのインストールが完了しました！"
	@echo "";
	@echo "🚀 使用開始ガイド:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "";
	@echo "💻 Gemini CLI:"
	@echo "  コマンド: gemini"
	@echo "  使用例: プロジェクトディレクトリで 'gemini' を実行"
	@echo "";
	@echo "🚀 SuperGemini (フレームワーク):"
	@echo "  Gemini CLI内で以下のコマンドが利用可能:"
	@echo "    /user-implement <機能>     - 機能実装"
	@echo "    /user-build                  - ビルド・パッケージング"
	@echo "    /user-design <UI>            - UI/UXデザイン"
	@echo "    /user-analyze <コード>       - コード分析"
	@echo "    /user-troubleshoot <issue>   - 問題のデバッグ"
	@echo "    /user-test <テスト>          - テストスイート"
	@echo "    /user-improve <コード>       - コード改善"
	@echo "";
	@echo "✨ おすすめワークフロー:"
	@echo "  1. 'gemini' でプロジェクトを開始"
	@echo "  2. '/user-implement' で機能を実装"
	@echo "";
	@echo "✅ Gemini エコシステムの一括インストールが完了しました"

.PHONY: uninstall-gemini
uninstall-gemini: ## Gemini CLI/SuperGemini の設定を削除
	@echo "🗑️  Gemini CLI/SuperGemini の設定を削除中..."
	@rm -f $(HOME_DIR)/.gemini/GEMINI.md
	@rm -f $(HOME_DIR)/.gemini/settings.json
	@rm -f $(HOME_DIR)/.gemini/supergemini
	@rm -f $(HOME_DIR)/.gemini/core
	@rm -f $(HOME_DIR)/.gemini/hooks
	@echo "✅ Gemini CLI/SuperGemini の設定を削除しました"

# ========================================
# エイリアス
# ========================================

.PHONY: install-gemini-cli
install-gemini-cli: install-packages-gemini-cli  ## Gemini CLIをインストール(エイリアス)

.PHONY: install-supergemini
install-supergemini: setup-supergemini  ## SuperGeminiをインストール(エイリアス)

.PHONY: gemini
gemini: install-gemini-cli  ## Gemini CLIをインストール(エイリアス)

