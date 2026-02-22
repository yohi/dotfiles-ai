# ============================================================
# Gemini CLI / SuperGemini セットアップ用Makefile
# Gemini CLI、SuperGemini Framework のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)

# Gemini CLI のインストール
install-packages-gemini-cli:
	@echo "🤖 Gemini CLI のインストールを開始..."

	# Node.jsの確認
	@$(MAKE) check-nodejs

	# npmの確認
	@echo "🔍 npm の確認中..."
	@if ! command -v npm >/dev/null 2>&1; then \
		echo "❌ npm がインストールされていません"; \
		echo "ℹ️  通常はNode.jsと一緒にインストールされます"; \
		exit 1; \
	else \
		echo "✅ npm が見つかりました (バージョン: $$(npm --version))"; \
	fi

	# Gemini CLI のインストール確認
	@echo "🔍 既存の Gemini CLI インストールを確認中..."
	@if command -v gemini >/dev/null 2>&1; then \
		echo "✅ Gemini CLI は既にインストールされています"; \
		echo "   バージョン: $$(gemini --version 2>/dev/null || echo '取得できませんでした')"; \
		echo ""; \
		echo "🔄 アップデートを確認中..."; \
		npm update -g @google/gemini-cli 2>/dev/null || true; \
	else \
		echo "📦 Gemini CLI をインストール中..."; \
		echo "ℹ️  グローバルインストールを実行します: npm install -g @google/gemini-cli"; \
		\
		if npm install -g @google/gemini-cli; then \
			echo "✅ Gemini CLI のインストールが完了しました"; \
		else \
			echo "❌ Gemini CLI のインストールに失敗しました"; \
			echo ""; \
			echo "🔧 トラブルシューティング:"; \
			echo "1. 権限の問題: npm config set prefix $(HOME)/.local"; \
			echo "2. WSLの場合: npm config set os linux"; \
			echo "3. 強制インストール: npm install -g @google/gemini-cli --force"; \
			echo ""; \
			exit 1; \
		fi; \
	fi

	# インストール確認
	@echo "🔍 インストールの確認中..."
	@if command -v gemini >/dev/null 2>&1; then \
		echo "✅ Gemini CLI が正常にインストールされました"; \
		echo "   実行ファイル: $$(which gemini)"; \
		echo "   バージョン: $$(gemini --version 2>/dev/null || echo '取得できませんでした')"; \
	else \
		echo "❌ Gemini CLI のインストール確認に失敗しました"; \
		echo "ℹ️  PATH の問題の可能性があります"; \
		echo "   手動確認: which gemini"; \
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

# SuperGemini (Gemini CLI Framework) のインストール
install-packages-supergemini:
	@echo "🚀 SuperGemini (Gemini CLI Framework) のインストールを開始..."

	# Gemini CLI の確認
	@echo "🔍 Gemini CLI の確認中..."
	@if ! command -v gemini >/dev/null 2>&1; then \
		echo "❌ Gemini CLI がインストールされていません"; \
		echo "ℹ️  先に 'make install-packages-gemini-cli' を実行してください"; \
		exit 1; \
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
	ln -sf $(REPO_ROOT)/gemini/supergemini/Core $(HOME_DIR)/.gemini/core || true; \
	ln -sf $(REPO_ROOT)/gemini/supergemini/Hooks $(HOME_DIR)/.gemini/hooks || true; \
	# 重要なファイルへの直接リンク \
	ln -sf $(REPO_ROOT)/gemini/supergemini/GEMINI.md $(HOME_DIR)/.gemini/GEMINI.md || true; \
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
	echo '{"selectedAuthType":"oauth-personal","usageStatisticsEnabled":false,"customToolsDirectory":"~/.gemini/user-tools","enableCustomTools":true}' > $(HOME_DIR)/.gemini/settings.json || true; \
	\
	echo "✅ SuperGemini フレームワークのシンボリックリンク設定が完了しました";
	@echo "";
	@echo "🎉 SuperGemini のセットアップが完了しました！"
	@echo "";
	@echo "🚀 使用方法:"
	@echo "1. Gemini CLI を起動: gemini"
	@echo "2. SuperGemini コマンドを使用:"
	@echo "";
	@echo "📋 利用可能なコマンド例:"
	@echo "   /user-implement <feature>    - 機能の実装"
	@echo "   /user-build                  - ビルド・パッケージング"
	@echo "   /user-design <ui>            - UI/UXデザイン"
	@echo "   /user-analyze <code>         - コード分析"
	@echo "   /user-troubleshoot <issue>   - 問題のデバッグ"
	@echo "   /user-test <suite>           - テストスイート"
	@echo "   /user-improve <code>         - コード改善"
	@echo "   /user-cleanup                - コードクリーンアップ"
	@echo "   /user-document <code>        - ドキュメント生成"
	@echo "   /user-git <operation>        - Git操作"
	@echo "   /user-estimate <task>        - 時間見積もり"
	@echo "   /user-task <management>      - タスク管理"
	@echo "";
	@echo "🎭 スマートペルソナ:"
	@echo "   🏗️  architect   - システム設計・アーキテクチャ"
	@echo "   🎨 frontend    - UI/UX・アクセシビリティ"
	@echo "   ⚙️  backend     - API・インフラストラクチャ"
	@echo "   🔍 analyzer    - デバッグ・問題解決"
	@echo "   🛡️  security    - セキュリティ・脆弱性評価"
	@echo "   ✍️  scribe      - ドキュメント・技術文書"
	@echo "";
	@echo "📝 注意: カスタムツールを再読み込みするには /reload-user-tools コマンドを使用します"
	@echo "";
	@echo "✅ SuperGemini のインストールが完了しました"

# Gemini エコシステム一括インストール
install-gemini-ecosystem:
	@echo "🌟 Gemini エコシステム一括インストールを開始..."
	@echo "";

	# Step 1: Gemini CLI のインストール
	@echo "📋 Step 1/2: Gemini CLI をインストール中..."
	@$(MAKE) install-packages-gemini-cli
	@echo "✅ Gemini CLI のインストールが完了しました"
	@echo "";

	# Step 2: SuperGemini のインストール
	@echo "📋 Step 2/2: SuperGemini をインストール中..."
	@$(MAKE) install-packages-supergemini
	@echo "✅ SuperGemini のインストールが完了しました"
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

# ========================================
# エイリアス
# ========================================

.PHONY: install-gemini-cli
install-gemini-cli: install-packages-gemini-cli  ## Gemini CLIをインストール(エイリアス)

.PHONY: install-supergemini
install-supergemini: install-packages-supergemini  ## SuperGeminiをインストール(エイリアス)

.PHONY: gemini
gemini: install-gemini-cli  ## Gemini CLIをインストール(エイリアス)

