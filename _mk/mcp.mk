.PHONY: setup-docker-mcp sync-mcp mcp uninstall-mcp status-mcp start-mcp stop-mcp restart-mcp logs-mcp

mcp: setup-docker-mcp

setup-docker-mcp:
	@echo "🐳 Docker MCPの設定をセットアップ中..."
	@bash _scripts/setup-docker-mcp.sh
	@echo "✅ Docker MCPの設定が完了しました。"

sync-mcp: ## Render and synchronize centralized MCP configs
	@bash _scripts/sync-mcp-configs.sh
	@$(MAKE) restart-mcp
	@echo "✅ MCP synchronization complete."

status-mcp: ## Docker MCP Gatewayのステータスを確認
	@echo "📊 Docker MCP Gateway status:"
	@if systemctl --user is-active docker-mcp-gateway.service > /dev/null 2>&1; then \
		systemctl --user status docker-mcp-gateway.service; \
	else \
		echo "❌ Docker MCP Gateway is not running."; \
		exit 1; \
	fi

start-mcp: ## Docker MCP Gatewayを起動
	@echo "🚀 Starting Docker MCP Gateway..."
	@systemctl --user start docker-mcp-gateway.service
	@$(MAKE) status-mcp

stop-mcp: ## Docker MCP Gatewayを停止
	@echo "🛑 Stopping Docker MCP Gateway..."
	@systemctl --user stop docker-mcp-gateway.service
	@echo "✅ Docker MCP Gateway stopped."

restart-mcp: ## Docker MCP Gatewayを再起動
	@echo "🔄 Restarting Docker MCP Gateway..."
	@systemctl --user daemon-reload
	@if systemctl --user is-active docker-mcp-gateway.service > /dev/null 2>&1; then \
		systemctl --user restart docker-mcp-gateway.service; \
	else \
		systemctl --user start docker-mcp-gateway.service; \
	fi
	@$(MAKE) status-mcp

logs-mcp: ## Docker MCP Gatewayのログを表示
	@echo "📋 Docker MCP Gateway logs (last 50 lines):"
	@journalctl --user -u docker-mcp-gateway.service -n 50 -f

uninstall-mcp:
	@echo "🗑️ Docker MCPの設定を削除中..."
	@set -e; \
	MCP_CONFIG_DIR="$$HOME/.docker/mcp"; \
	SERVICE_FILE="$$HOME/.config/systemd/user/docker-mcp-gateway.service"; \
	if systemctl --user status > /dev/null 2>&1; then \
		echo "Stopping and disabling systemd service..."; \
		systemctl --user stop docker-mcp-gateway.service || true; \
		systemctl --user disable docker-mcp-gateway.service || true; \
		rm -f "$$SERVICE_FILE"; \
		systemctl --user daemon-reload; \
	else \
		echo "Systemd user session not available, skipping service cleanup."; \
		rm -f "$$SERVICE_FILE"; \
	fi; \
	echo "Removing configuration directory: $$MCP_CONFIG_DIR"; \
	rm -rf "$$MCP_CONFIG_DIR"; \
	echo "✅ Docker MCPの設定が削除されました。"
