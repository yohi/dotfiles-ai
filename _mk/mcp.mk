.PHONY: setup-docker-mcp sync-mcp mcp uninstall-mcp status-mcp start-mcp stop-mcp restart-mcp logs-mcp status-watchdog logs-watchdog fix-ubuntu-rootless sync-mcp-gateway auth-mcp

mcp: setup-docker-mcp

setup-docker-mcp: sync-mcp sync-mcp-gateway ## Docker MCP Gateway のセットアップ（APM同期→設定反映→サービス起動）
	$(Q_ECHO) "🐳 Docker MCPの設定をセットアップ中..."
	@bash _scripts/setup-docker-mcp.sh
	systemctl --user daemon-reload
	$(MAKE) restart-mcp
	$(Q_ECHO) "✅ Docker MCPの設定が完了しました。"
	$(Q_ECHO) "💡 使い方を確認するには 'make help-mcp' を実行してください。"

fix-ubuntu-rootless: ## Ubuntu 24.04+ の Rootless Docker 制限を解除 (要 sudo)
	@echo "🔧 Ubuntu 24.04+ の Rootless Docker 制限を解除しています..."
	sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
	echo "kernel.apparmor_restrict_unprivileged_userns = 0" | sudo tee /etc/sysctl.d/99-rootless-docker.conf
	@echo "✅ 設定が完了しました。'systemctl --user restart docker.service' を実行して Docker を再起動してください。"

.PHONY: help-mcp
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
	@echo "✅ MCP synchronization complete."
	@$(MAKE) restart-mcp

sync-mcp-gateway: ## Docker MCP Gateway 設定を同期
	@echo "📦 Syncing Docker MCP Gateway config..."
	@mkdir -p $(HOME_DIR)/.docker/mcp
	@mkdir -p $(HOME_DIR)/.config/systemd/user
	@# APMによって生成された設定ファイルをGatewayの場所へ配置
	@if [ -f "mcp/config.yaml" ]; then \
		cp mcp/config.yaml $(HOME_DIR)/.docker/mcp/config.yaml; \
		echo "✅ Gateway config synced."; \
	else \
		echo "⚠️  mcp/config.yaml not found — run 'make sync-mcp' first."; \
	fi
	@mkdir -p $(HOME_DIR)/.docker/mcp/catalogs
	@if [ -f "mcp/catalogs/custom.yaml.template" ]; then \
		sed -e "s|__HOME__|$(HOME_DIR)|g" \
		    -e "s|__REPO_ROOT__|$(REPO_ROOT)|g" \
		    mcp/catalogs/custom.yaml.template > $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml; \
		cp $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml mcp/catalogs/custom.yaml; \
		echo "✅ Custom catalog configured and synced."; \
	else \
		echo "⚠️  mcp/catalogs/custom.yaml.template not found."; \
	fi
	@# Docker MCP Gateway refuses catalogs that resolve outside its catalogs directory,
	@# so ensure the deployed files are real copies rather than symlinks.
	@# Only materialize if the source file exists, to avoid deleting the symlink and leaving nothing.
	@if [ -L $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml ] && [ -f mcp/catalogs/custom.yaml ]; then \
		rm -f $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml; \
		cp mcp/catalogs/custom.yaml $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml; \
		echo "✅ Custom catalog materialized to a regular file."; \
	elif [ -L $(HOME_DIR)/.docker/mcp/catalogs/custom.yaml ]; then \
		echo "[!] Custom catalog is a symlink but source mcp/catalogs/custom.yaml is missing; leaving symlink intact."; \
	fi
	@if [ -f "mcp/catalogs/bootstrap.yaml" ]; then \
		cp mcp/catalogs/bootstrap.yaml $(HOME_DIR)/.docker/mcp/catalogs/bootstrap.yaml; \
		echo "✅ Bootstrap catalog synced."; \
	fi
	@if [ -L $(HOME_DIR)/.docker/mcp/catalogs/bootstrap.yaml ] && [ -f mcp/catalogs/bootstrap.yaml ]; then \
		rm -f $(HOME_DIR)/.docker/mcp/catalogs/bootstrap.yaml; \
		cp mcp/catalogs/bootstrap.yaml $(HOME_DIR)/.docker/mcp/catalogs/bootstrap.yaml; \
		echo "✅ Bootstrap catalog materialized to a regular file."; \
	elif [ -L $(HOME_DIR)/.docker/mcp/catalogs/bootstrap.yaml ]; then \
		echo "[!] Bootstrap catalog is a symlink but source mcp/catalogs/bootstrap.yaml is missing; leaving symlink intact."; \
	fi
	@if [ ! -f "mcp/docker-mcp-gateway.service" ]; then \
		echo "❌ Error: mcp/docker-mcp-gateway.service not found." >&2; \
		exit 1; \
	fi
	@sed -e "s|__HOME__|$(HOME_DIR)|g" \
	    -e "s|__REPO_ROOT__|$(REPO_ROOT)|g" \
	    -e "s|__ENABLED_SERVERS__|nexus,chronos-graph|g" \
	    mcp/docker-mcp-gateway.service > $(HOME_DIR)/.config/systemd/user/docker-mcp-gateway.service
	@echo "✅ Service file docker-mcp-gateway.service deployed and configured."
	@if [ ! -f "mcp/mcp-watchdog.service" ]; then \
		echo "❌ Error: mcp/mcp-watchdog.service not found." >&2; \
		exit 1; \
	fi
	@sed -e "s|__HOME__|$(HOME_DIR)|g" \
	    -e "s|__REPO_ROOT__|$(REPO_ROOT)|g" \
	    mcp/mcp-watchdog.service > $(HOME_DIR)/.config/systemd/user/mcp-watchdog.service
	@echo "✅ Service file mcp-watchdog.service deployed and configured."

status-mcp: ## Docker MCP Gatewayのステータスを確認
	@echo "📊 Docker MCP Gateway status:"
	@if systemctl --user is-active docker-mcp-gateway.service > /dev/null 2>&1; then \
		systemctl --user --no-pager status docker-mcp-gateway.service; \
	else \
		echo "❌ Docker MCP Gateway is not running."; \
		exit 1; \
	fi

start-mcp: ## Docker MCP Gatewayを起動
	@echo "🚀 Starting Docker MCP Gateway..."
	@systemctl --user --no-pager start docker-mcp-gateway.service
	@$(MAKE) status-mcp

stop-mcp: ## Docker MCP Gatewayを停止
	@echo "🛑 Stopping Docker MCP Gateway..."
	@systemctl --user --no-pager stop docker-mcp-gateway.service
	@echo "✅ Docker MCP Gateway stopped."

restart-mcp: ## Docker MCP Gatewayを再起動
	@echo "🔄 Restarting Docker MCP Gateway..."
	@systemctl --user --no-pager daemon-reload || true
	@if systemctl --user list-unit-files docker-mcp-gateway.service >/dev/null 2>&1; then \
		if systemctl --user --no-pager is-active docker-mcp-gateway.service > /dev/null 2>&1; then \
			systemctl --user --no-pager restart docker-mcp-gateway.service || echo "⚠️  Failed to restart docker-mcp-gateway.service"; \
		else \
			systemctl --user --no-pager start docker-mcp-gateway.service || echo "⚠️  Failed to start docker-mcp-gateway.service"; \
		fi; \
		$(MAKE) status-mcp || true; \
	else \
		echo "ℹ️  docker-mcp-gateway.service is not installed yet. Skipping restart."; \
	fi

logs-mcp: ## Docker MCP Gatewayのログを表示
	@echo "📋 Docker MCP Gateway logs (last 50 lines):"
	@journalctl --user --no-pager -u docker-mcp-gateway.service -n 50 -f

status-watchdog: ## MCP Watchdogのステータスを確認
	@echo "📊 MCP Watchdog status:"
	@if systemctl --user is-active mcp-watchdog.service > /dev/null 2>&1; then \
		systemctl --user --no-pager status mcp-watchdog.service; \
	else \
		echo "❌ MCP Watchdog is not running."; exit 1; \
	fi

logs-watchdog: ## MCP Watchdogのログを表示
	@echo "📋 MCP Watchdog logs (last 50 lines):"
	@journalctl --user --no-pager -u mcp-watchdog.service -n 50 -f

uninstall-mcp:
	@echo "🗑️ Docker MCPの設定を削除中..."
	@set -e; \
	MCP_CONFIG_DIR="$$HOME/.docker/mcp"; \
	SERVICE_FILE="$$HOME/.config/systemd/user/docker-mcp-gateway.service"; \
	WATCHDOG_SERVICE_FILE="$$HOME/.config/systemd/user/mcp-watchdog.service"; \
	if systemctl --user --no-pager status > /dev/null 2>&1; then \
		echo "Stopping and disabling systemd services..."; \
		systemctl --user --no-pager stop mcp-watchdog.service || true; \
		systemctl --user --no-pager disable mcp-watchdog.service || true; \
		systemctl --user --no-pager stop docker-mcp-gateway.service || true; \
		systemctl --user --no-pager disable docker-mcp-gateway.service || true; \
		rm -f "$$SERVICE_FILE" "$$WATCHDOG_SERVICE_FILE"; \
		systemctl --user --no-pager daemon-reload; \
	else \
		echo "Systemd user session not available, skipping service cleanup."; \
		rm -f "$$SERVICE_FILE" "$$WATCHDOG_SERVICE_FILE"; \
	fi; \
	echo "Removing configuration directory: $$MCP_CONFIG_DIR"; \
	rm -rf "$$MCP_CONFIG_DIR"; \
	echo "✅ Docker MCPの設定が削除されました。"

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
auth-mcp: ## Docker MCP Gateway OAuth 認証を対話的に実行
	@python3 _scripts/auth-mcp.py
