.PHONY: all install install-agents install-ides setup setup-agents setup-ides mcp-render link clean-internal install-requirements lint init sync secrets status clean test clean-legacy

# --- Standard Entry Points ---
all: install setup

install: install-agents install-ides ## Install all AI agents and IDE binaries

setup: setup-agents setup-ides ## Setup all AI agents and IDE configurations
	@$(MAKE) mcp-render
	-@$(MAKE) setup-superpowers 2>/dev/null || true
	-@$(MAKE) sync-agents 2>/dev/null || true
	-@$(MAKE) sync-mcp 2>/dev/null || true
	@echo "✅ dotfiles-ai のコア設定が適用されました"

sync: ## [更新] リポジトリを最新にし、エージェントを同期する
	@echo "🔄 リポジトリを最新に同期中..."
	@git pull --rebase || (echo "❌ git pull --rebase に失敗しました"; exit 1)
	@$(MAKE) sync-agents

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
	@if [ ! -d node_modules ]; then \
		if [ -f package-lock.json ]; then \
			npm ci; \
		else \
			npm install; \
		fi \
	fi
	$(MAKE) setup-claude
	$(MAKE) setup-supergemini
	$(MAKE) setup-codex
	$(MAKE) setup-opencode
	$(MAKE) setup-antigravity
	$(MAKE) setup-docker-mcp

setup-ides:
	@echo "🚀 dotfiles-ai IDE 設定をセットアップ中..."
	$(MAKE) setup-cursor
	$(MAKE) setup-vscode

mcp-render:
	@sed "s|__HOME__|$$HOME|g" mcp/catalogs/custom.yaml.template > mcp/catalogs/custom.yaml

link: setup
	@echo "🔗 dotfiles-ai をリンク中 (Handled in setup targets)"

clean-internal:
	@echo "🧹 dotfiles-ai をクリーンアップ中..."
	-$(MAKE) uninstall-superclaude
	-$(MAKE) uninstall-claude
	-$(MAKE) uninstall-gemini
	-$(MAKE) uninstall-codex
	-$(MAKE) uninstall-opencode
	-$(MAKE) uninstall-antigravity
	-$(MAKE) uninstall-skillport
	-$(MAKE) uninstall-mcp
	-$(MAKE) uninstall-superpowers
	-$(MAKE) uninstall-cursor FORCE=true
	-$(MAKE) uninstall-vscode FORCE=true

install-requirements:
	@echo "📦 依存関係をインストール中..."
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --system -r requirements.txt; \
	else \
		pip install -r requirements.txt; \
	fi

lint: ## Run Ruff and Mypy on .
	@echo "🔍 . に対して Ruff と Mypy を実行中..."
	@if command -v uv >/dev/null 2>&1; then \
		$(PYTHON) ruff check . && $(PYTHON) mypy .; \
	else \
		ruff check . && mypy .; \
	fi

# --- Workflow Guide Targets (Help Integration & Parent Compatibility) ---

init: install ## [初回] 依存パッケージのインストールと初期設定

secrets: ## [機密] BitwardenからAPIキー等の機密情報を取得 (このリポジトリでは未実装)
	@echo "ℹ️  secrets: Bitwarden からの取得機能はこのリポジトリには実装されていません。"
	@echo "   手動で .env や API キーを確認してください。"

status: ## [確認] 全コンポーネントの状態を一括表示
	@echo "--- Repository Status ---"
	@git status -s
	@echo ""
	@echo "--- Agent Status ---"
	@$(MAKE) -s check-skillport
	@$(MAKE) -s check-opencode
	@$(MAKE) -s check-superclaude
	@$(MAKE) -s check-codex
	@$(MAKE) -s check-antigravity
	@$(MAKE) -s check-cursor-version

clean: ## 生成されたアーティファクトとキャッシュを削除
	@echo "🧹 クリーンアップ中..."
	@$(MAKE) -s clean-legacy 2>/dev/null || true
	@# _mk/main.mk の clean-internal を呼び出し
	@$(MAKE) -s clean-internal 2>/dev/null || true
	@rm -rf build/ dist/ *.pyc __pycache__ .ruff_cache .mypy_cache
	@echo "✅ クリーンアップが完了しました"

test: ## プロジェクトのテスト/静的解析を実行
	@$(MAKE) lint
	@echo "🧪 Running profile substitution tests..."
	@bash _scripts/test-omo-profiles.sh
	@echo "🧪 Running MCP Make target tests..."
	@bash _scripts/test-mcp-make-targets.sh
