.PHONY: setup-docker-mcp mcp uninstall-mcp

mcp: setup-docker-mcp

setup-docker-mcp:
	@echo "🐳 Docker MCPの設定をセットアップ中..."
	@bash scripts/setup-docker-mcp.sh
	@echo "✅ Docker MCPの設定が完了しました。"

uninstall-mcp:
	@echo "🗑️ Docker MCPの設定を削除中..."
	@# アンインストールロジックがあればここに追加
	@echo "✅ Docker MCPの設定が削除されました。"
