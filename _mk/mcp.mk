.PHONY: setup-docker-mcp mcp uninstall-mcp

mcp: setup-docker-mcp

setup-docker-mcp:
	@echo "🐳 Docker MCPの設定をセットアップ中..."
	@bash scripts/setup-docker-mcp.sh
	@echo "✅ Docker MCPの設定が完了しました。"

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
