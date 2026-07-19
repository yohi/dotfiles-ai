.PHONY: sync-mcp sync-gemini-codex help-mcp

mcp: sync-mcp

help-mcp: ## MCP の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/mcp.md)

sync-mcp: ## APMを使用してMCP設定を同期
	@echo "🔄 Synchronizing MCP settings via APM..."
	@if ! command -v semgrep &> /dev/null; then \
		echo "[*] Installing semgrep via uv..."; \
		uv tool install semgrep; \
	fi
	@if [ -f ".env" ]; then \
		set -a && source .env && set +a && apm install --force; \
	else \
		apm install --force; \
	fi
	#	@-$(MAKE) sync-gemini-codex  # disabled: Codex/Gemini CLI integration disabled (see apm.yml targets:)
	@echo "[+] MCP synchronization complete."

sync-gemini-codex: ## Gemini / Codex の MCP 設定を同期
	@echo "🔄 Synchronizing Gemini / Codex MCP settings..."
	@uv run --with pyyaml --with tomli python3 _scripts/generate-gemini-codex-mcp.py




CODEGRAPH_VERSION ?= v1.1.3
CODEGRAPH_HASH ?= 6dc5a5b932eab90aafbabb7744d44d6df6fff7061df981c82d11497497f4ff7a

.PHONY: install-codegraph setup-codegraph uninstall-codegraph

install-codegraph: ## Install codegraph CLI
	$(Q_ECHO) "📦 codegraph CLI をインストール中..."
	@if ! command -v codegraph &> /dev/null && [ ! -f "$(HOME_DIR)/.local/bin/codegraph" ]; then \
		installer=$$(mktemp /tmp/codegraph-installer.XXXXXX.sh); \
		if curl -fsSL --retry 3 --retry-delay 2 --max-time 60 "https://raw.githubusercontent.com/colbymchenry/codegraph/$(CODEGRAPH_VERSION)/install.sh" -o "$$installer" && \
			actual=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$installer" | cut -d" " -f1) || shasum -a 256 "$$installer" | cut -d" " -f1 ) && \
			[ "$$actual" = "$(CODEGRAPH_HASH)" ]; then \
			sh "$$installer" && rm -f "$$installer" || { rc=$$?; rm -f "$$installer"; exit $$rc; }; \
		else \
			rm -f "$$installer"; \
			echo "❌ codegraph installer のチェックサム検証に失敗しました。"; \
			exit 1; \
		fi; \
	else \
		echo "  [SKIP] codegraph CLI は既にインストールされています。"; \
	fi

setup-codegraph: install-codegraph ## Wire up codegraph to agents
	$(Q_ECHO) "🚀 codegraph を各エージェントに紐付け中..."
	@export PATH="$(HOME_DIR)/.local/bin:$$PATH"; \
	if command -v codegraph &> /dev/null; then \
		codegraph install --yes; \
	else \
		echo "❌ codegraph が見つかりません。パスを確認してください。"; \
		exit 1; \
	fi
	$(Q_ECHO) "✅ codegraph の紐付けが完了しました。"

uninstall-codegraph: ## Uninstall codegraph from agents and system
	$(Q_ECHO) "🗑️ codegraph をアンインストール中..."
	@export PATH="$(HOME_DIR)/.local/bin:$$PATH"; \
	if command -v codegraph &> /dev/null; then \
		codegraph uninstall --yes || true; \
	fi
	@rm -f "$(HOME_DIR)/.local/bin/codegraph"
	@rm -rf "$(HOME_DIR)/.codegraph"
	$(Q_ECHO) "✅ codegraph のアンインストールが完了しました。"

