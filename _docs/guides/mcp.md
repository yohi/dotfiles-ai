# MCP (Model Context Protocol) 使用ガイド

🐳 Docker MCP Gateway のセットアップが完了しました！

## 🚀 サービス管理:
- `make start-mcp`                - MCP Gateway を起動
- `make stop-mcp`                 - MCP Gateway を停止
- `make restart-mcp`              - MCP Gateway を再起動
- `make status-mcp`               - ステータス確認
- `make logs-mcp`                 - ログを表示 (`journalctl`)

## 🔄 設定の同期:
- `make sync-mcp`                 - `mcp/config.yaml` などの設定を反映して再起動

## 📂 設定ディレクトリ:
- **実体**: `mcp/`
- **配置先**: `~/.docker/mcp/` (Docker MCP Gateway が参照)

## 🛠️ トラブルシューティング:
もしサービスが起動しない場合は、`make logs-mcp` でエラー内容を確認してください。Docker が起動している必要があります。
