.PHONY: all install install-agents install-ides setup setup-agents setup-ides mcp-render link clean-internal install-requirements lint init sync secrets status clean test clean-legacy configure-git-ignore doctor

# --- Standard Entry Points ---
all: install init-env setup sync-mcp ## [完全セットアップ] インストール、環境構築、設定、MCP同期をすべて行う

install: install-requirements install-agents install-ides ## Install all AI agents and IDE binaries

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

sync: ## [更新] リポジトリを最新にし、エージェントを同期する
	$(Q_ECHO) "🔄 リポジトリを最新に同期中..."
	@git pull --rebase || (echo "❌ git pull --rebase に失敗しました"; exit 1)
	@$(MAKE) sync-agents

install-agents:
	$(Q_ECHO) "📦 dotfiles-ai エージェントバイナリをインストール中..."
	$(MAKE) install-packages-claude-code
	$(MAKE) install-packages-gemini-cli
	$(MAKE) install-packages-codex
	$(MAKE) install-packages-opencode
	$(MAKE) install-packages-superclaude

install-ides:
	$(Q_ECHO) "📦 dotfiles-ai IDE ツールをインストール中..."
	$(MAKE) install-packages-cursor

setup-agents:
	$(Q_ECHO) "🚀 dotfiles-ai エージェント設定をセットアップ中..."
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
	$(Q_ECHO) "🚀 dotfiles-ai IDE 設定をセットアップ中..."
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
		uv sync; \
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

secrets: ## [機密] BitワードenからAPIキー等の機密情報を取得 (このリポジトリでは未実装)
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
	@echo ""
	@echo "--- Action Required Check ---"
	@$(MAKE) -s doctor

doctor: ## [診断] 設定の不備や同期が必要な箇所を特定し、解決策を提示する
	$(Q_ECHO) "🩺 システム診断を実行中..."
	@# 1. .env check
	@if [ ! -f .env ]; then \
		echo "❌ [ACTION REQUIRED] .env ファイルが見つかりません。'make init-env' を実行してください。"; \
	fi
	@# 2. Sync check (skills vs agents)
	@LATEST_SKILL=$$(find agent-skills -type f -name "*.md" -printf '%%T@ %%p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); \
	LATEST_CMD=$$(find agent-commands -type f -name "*.md" -printf '%%T@ %%p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); \	LAST_SYNC_FILE="$(REPO_ROOT)/.last_sync"; \
	if [ -f "$$LAST_SYNC_FILE" ]; then \
		if [ -n "$$LATEST_SKILL" ] && [ "$$LATEST_SKILL" -nt "$$LAST_SYNC_FILE" ]; then \
			echo "⚠️  [ACTION REQUIRED] スキルが変更されています。'make sync-agents' を実行してください。"; \
		elif [ -n "$$LATEST_CMD" ] && [ "$$LATEST_CMD" -nt "$$LAST_SYNC_FILE" ]; then \
			echo "⚠️  [ACTION REQUIRED] コマンドが変更されています。'make sync-agents' を実行してください。"; \
		fi; \
	elif [ -n "$$LATEST_SKILL" ] || [ -n "$$LATEST_CMD" ]; then \
		echo "⚠️  [ACTION REQUIRED] 同期が一度も実行されていません。'make sync-agents' を実行してください。"; \
	fi
	@# 3. Component specific checks
	@if [ ! -L "$(HOME)/.claude/CLAUDE.md" ]; then \
		echo "⚠️  [ACTION REQUIRED] Claude の設定が未完了です。'make setup-claude' を実行してください。"; \
	fi
	@if [ ! -L "$(HOME)/.gemini/settings.json" ]; then \
		echo "⚠️  [ACTION REQUIRED] Gemini の設定が未完了です。'make setup-supergemini' を実行してください。"; \
	fi
	@if ! command -v skillport >/dev/null 2>&1; then \
		echo "⚠️  [ACTION REQUIRED] SkillPort がインストールされていません。'make install-skillport' を実行してください。"; \
	fi
	@# 4. OS-aware MCP check
	@if [ "$(OS_NAME)" = "Linux" ]; then \
		if ! systemctl --user list-unit-files docker-mcp-gateway.service >/dev/null 2>&1; then \
			echo "❌ [ACTION REQUIRED] Docker MCP Gateway がセットアップされていません。'make setup-docker-mcp' を実行してください。"; \
		elif ! systemctl --user is-active docker-mcp-gateway.service > /dev/null 2>&1; then \
			echo "ℹ️  [INFO] Docker MCP Gateway が起動していません。'make start-mcp' で起動できます。"; \
		fi; \
	elif [ "$(OS_NAME)" = "Darwin" ]; then \
		echo "ℹ️  [INFO] macOS (Darwin) 環境です。Docker MCP Gateway の自動起動診断は現在制限されています。"; \
	else \
		echo "ℹ️  [INFO] $(OS_NAME) 環境です。Docker MCP Gateway の自動診断はスキップされました。"; \
	fi
	$(Q_ECHO) "✅ 診断完了"

clean: ## 生成されたアーティファクトとキャッシュを削除
	@echo "🧹 クリーンアップ中..."
	@$(MAKE) -s clean-legacy 2>/dev/null || true
	@$(MAKE) -s clean-sync-artifacts 2>/dev/null || true
	@# _mk/main.mk の clean-internal を呼び出し
	@$(MAKE) -s clean-internal 2>/dev/null || true
	@rm -rf build/ dist/ *.pyc __pycache__ .ruff_cache .mypy_cache
	@echo "✅ クリーンアップが完了しました"

test: ## プロジェクトのテスト/静的解析を実行
	@$(MAKE) lint
	@echo "🧪 Running Python unit tests..."
	@PYTHONPATH=_scripts $(PYTHON) -m unittest discover -p "test_*.py" _scripts
	@echo "🧪 Running profile substitution tests..."
	@bash _scripts/test-omo-profiles.sh
	@echo "🧪 Running MCP Make target tests..."
	@bash _scripts/test-mcp-make-targets.sh

# --- Local Git Ignore Configuration ---
configure-git-ignore: ## [.git] .gitignore_template をグローバル設定に同期する
	@echo "🔄 グローバル gitignore を同期中..."
	@mkdir -p $(HOME)/.config/git
	@cp .gitignore_template $(HOME)/.config/git/ignore
	@git config --global core.excludesfile $(HOME)/.config/git/ignore
	@echo "✅ グローバル除外設定を同期しました: $(HOME)/.config/git/ignore"
