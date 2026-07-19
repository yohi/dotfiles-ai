.PHONY: all install install-agents install-ides setup setup-agents setup-ides link clean-internal install-requirements lint init sync secrets status clean test clean-legacy configure-git-ignore doctor apm-install install-apm

UV_VERSION ?= 0.11.19

# --- APM Entry Point ---
apm-install: ## APM install と全設定の同期を実行
	$(Q_ECHO) "📦 APM install を実行中..."
	@apm install
	$(Q_ECHO) "🔄 opencode.jsonc を生成中..."
	@$(MAKE) sync-opencode
	$(Q_ECHO) "🔄 エージェントを同期中..."
	@$(MAKE) sync-agents
	$(Q_ECHO) "🔗 MCP設定を同期中..."
	@$(MAKE) sync-mcp
	$(Q_ECHO) "📝 .env 雛形を確認中..."
	@$(MAKE) setup-apm-env
	$(Q_ECHO) "🔗 OpenCode 設定を適用中..."
	@$(MAKE) setup-opencode
	$(Q_ECHO) "✅ APM install と全設定の同期が完了しました"

# --- Standard Entry Points ---
all: install setup ## [完全セットアップ] インストール、環境構築、エージェント/IDE/MCPの設定をすべて行う

install: install-requirements install-agents install-ides ## Install all AI agents and IDE binaries

setup: install-requirements install-apm ## APMインストール、エージェント/IDE/MCP設定を一括適用
	$(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."
	@$(MAKE) sync-agents
	@$(MAKE) setup-apm-env
	@$(MAKE) sync-mcp
	@$(MAKE) setup-agents
	@$(MAKE) setup-ides
	$(Q_ECHO) "✅ dotfiles-ai の全設定が適用されました"
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
	$(MAKE) install-packages-opcode
	$(MAKE) install-codegraph

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
	#	$(MAKE) setup-gemini  # disabled: Gemini CLI integration disabled (see apm.yml targets:)
	#	$(MAKE) setup-codex  # disabled: Codex integration disabled (see apm.yml targets:)
	$(MAKE) setup-opencode
	$(MAKE) setup-antigravity
	$(MAKE) setup-codegraph

setup-ides:
	$(Q_ECHO) "🚀 dotfiles-ai IDE 設定をセットアップ中..."
	#	$(MAKE) setup-cursor  # disabled: Cursor IDE integration disabled (see apm.yml targets:)
	#	$(MAKE) setup-vscode  # disabled: VSCode integration disabled (see apm.yml targets:)

link: setup
	@echo "🔗 dotfiles-ai をリンク中 (Handled in setup targets)"

clean-internal:
	@echo "🧹 dotfiles-ai をクリーンアップ中..."
	-$(MAKE) uninstall-claude
	-$(MAKE) uninstall-gemini
	-$(MAKE) uninstall-codex
	-$(MAKE) uninstall-opencode
	-$(MAKE) uninstall-antigravity
	-$(MAKE) uninstall-skillport
	-$(MAKE) uninstall-mcp
	-$(MAKE) uninstall-codegraph
	-$(MAKE) uninstall-cursor FORCE=true
	-$(MAKE) uninstall-vscode FORCE=true

install-requirements:
	@echo "📦 依存関係をインストール中..."
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	else \
		installer=$$(mktemp /tmp/uv-installer.XXXXXX.sh); \
		checksums=$$(mktemp /tmp/uv-sha256.XXXXXX.sum); \
		base_url="https://releases.astral.sh/github/uv/releases/download/$(UV_VERSION)"; \
		if curl -fSL --retry 3 --retry-delay 2 --max-time 60 "$$base_url/uv-installer.sh" -o "$$installer" && \
			curl -fSL --retry 3 --retry-delay 2 --max-time 60 "$$base_url/sha256.sum" -o "$$checksums" && \
			expected=$$(grep ' uv-installer.sh$$' "$$checksums" | awk '{print $$1}') && \
			actual=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$installer" | cut -d" " -f1) || shasum -a 256 "$$installer" | cut -d" " -f1 ) && \
			[ "$$actual" = "$$expected" ]; then \
			sh "$$installer"; \
			rm -f "$$installer" "$$checksums"; \
		export PATH="$(HOME)/.local/bin:$(PATH)"; \
		uv sync; \
		else \
			rm -f "$$installer" "$$checksums"; \
			if [ ! -d ".venv" ]; then \
				python3 -m venv .venv; \
			fi; \
			.venv/bin/pip install -r requirements.txt; \
		fi; \
	fi

lint: ## Run Ruff and Mypy on .
	@echo "🔍 . に対して Ruff と Mypy を実行中..."
	@if command -v uv >/dev/null 2>&1; then \
		$(PYTHON) ruff check . --exclude oss && $(PYTHON) mypy --exclude '(^|/)oss/' .; \
	else \
		ruff check . --exclude oss && mypy --exclude '(^|/)oss/' .; \
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
	@$(MAKE) -s check-claude
	@$(MAKE) -s check-gemini
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
	LATEST_CMD=$$(find agent-commands -type f -name "*.md" -printf '%%T@ %%p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); \
	LAST_SYNC_FILE="$(REPO_ROOT)/.last_sync"; \
	if [ -f "$$LAST_SYNC_FILE" ]; then \
		if [ -n "$$LATEST_SKILL" ] && [ "$$LATEST_SKILL" -nt "$$LAST_SYNC_FILE" ]; then \
			echo "⚠️  [ACTION REQUIRED] スキルが変更されています。'make sync-agents' を実行してください。"; \
		elif [ -n "$$LATEST_CMD" ] && [ "$$LATEST_CMD" -nt "$$LAST_SYNC_FILE" ]; then \
			echo "⚠️  [ACTION REQUIRED] コマンドが変更されています。'make sync-agents' を実行してください。"; \
		fi; \
	elif [ -n "$$LATEST_SKILL" ] || [ -n "$$LATEST_CMD" ]; then \
		echo "⚠️  [ACTION REQUIRED] 同期が一度も実行されていません。'make sync-agents' を実行してください。"; \
	fi
	@# 4. Direct MCP runtime check
	@missing_runtime=""; \
	for cmd in uv npx; do \
		if ! command -v $$cmd >/dev/null 2>&1; then \
			missing_runtime="$$missing_runtime $$cmd"; \
		fi; \
	done; \
	if [ -n "$$missing_runtime" ]; then \
		echo "⚠️  [ACTION REQUIRED] Direct MCP runtime が見つかりません:$$missing_runtime。'make install-requirements' を実行してください。"; \
	fi
	@# 5. GitHub MCP server binary check
	@if ! command -v github-mcp-server >/dev/null 2>&1; then \
		echo "⚠️  [ACTION REQUIRED] github-mcp-server バイナリが見つかりません。'go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest' を実行してください。"; \
	fi
	$(Q_ECHO) "✅ 診断完了"

clean: ## 生成されたアーティファクトとキャッシュを削除
	@echo "🧹 クリーンアップ中..."
	@$(MAKE) -s clean-legacy 2>/dev/null || true
	@$(MAKE) -s clean-sync-artifacts 2>/dev/null || true
	@# _mk/main.mk の clean-internal を呼び出し
	@$(MAKE) -s clean-internal 2>/dev/null || true
	@rm -rf build/ dist/ *.pyc __pycache__ .ruff_cache .mypy_cache
	@# ルートの不要な一時隠しフォルダやバグフォルダを完全削除
	@rm -rf "$(REPO_ROOT)/.claude" "$(REPO_ROOT)/.gemini"
	@echo "[i] Preserved runtime skills directory: $(RUNTIME_SKILLS_DIR)"
	@# バグでできた特殊フォルダの削除（シングルクォートで変数展開を防ぐ）
	@rm -rf '$(REPO_ROOT)/$$' '$(REPO_ROOT)/$${HOME}' '$(REPO_ROOT)/$${env:HOME}'
	@echo "✅ クリーンアップが完了しました"

# --- Local Git Ignore Configuration ---
configure-git-ignore: ## [.git] .gitignore_template をグローバル設定に同期する
	@echo "🔄 グローバル gitignore を同期中..."
	@mkdir -p $(HOME)/.config/git
	@cp .gitignore_template $(HOME)/.config/git/ignore
	@git config --global core.excludesfile $(HOME)/.config/git/ignore
	@echo "✅ グローバル除外設定を同期しました: $(HOME)/.config/git/ignore"
