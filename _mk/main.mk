install: install-agents install-ides ## Install all AI agents and IDE binaries

install-agents:
	@echo "📦 dotfiles-ai エージェントバイナリをインストール中..."
	$(MAKE) install-packages-claude-code
	$(MAKE) install-packages-gemini-cli
	$(MAKE) install-packages-codex
	$(MAKE) install-packages-opencode

install-ides:
	@echo "📦 dotfiles-ai IDE ツールをインストール中..."
	$(MAKE) install-packages-cursor

setup: setup-agents setup-ides ## Setup all AI agents and IDE configurations

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
	$(MAKE) install-packages-superclaude
	$(MAKE) setup-superpowers
	$(MAKE) sync-agents
	$(MAKE) sync-mcp

setup-ides:
	@echo "🚀 dotfiles-ai IDE 設定をセットアップ中..."
	$(MAKE) setup-cursor
	$(MAKE) setup-vscode

mcp-render:
	@sed "s|__HOME__|$$HOME|g" mcp/catalogs/custom.yaml.template > mcp/catalogs/custom.yaml

link: setup
	@echo "🔗 dotfiles-ai をリンク中 (Handled in setup targets)"

clean:
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

lint: ## Run Ruff and Mypy on scripts/
	@echo "🔍 scripts/ に対して Ruff と Mypy を実行中..."
	@if command -v uv >/dev/null 2>&1; then \
		$(PYTHON) ruff check scripts/ && $(PYTHON) mypy scripts/; \
	else \
		ruff check scripts/ && mypy scripts/; \
	fi
