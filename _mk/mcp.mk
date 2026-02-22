.PHONY: setup-docker-mcp

setup-docker-mcp:
	@echo "🐳 Docker MCPの設定をセットアップ中..."
	@bash scripts/setup-docker-mcp.sh
	@echo "✅ Docker MCPの設定が完了しました。"
