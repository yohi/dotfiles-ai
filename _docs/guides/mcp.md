# MCP (Model Context Protocol) 使用ガイド

このプロジェクトでは、有効にする MCP サーバーを `apm.yml` で管理しています。
任意サーバーの定義は `mcp/optional-servers.yaml` にあり、自動同期されません。

## 設定の同期

- `make sync-mcp` — `apm.yml` を元に各エージェント（Claude Code, OpenCode, Codex, VSCode, Cursor, Antigravity）の MCP 設定を再生成（Gemini CLI は手動配置）

## 管理対象サーバー

`apm.yml` の `dependencies.mcp` に記載したサーバーが同期対象です。現在の主な
サーバーは以下の通りです。

- `cf-mcp-portal`, `cf-mcp-portal-work` — Cloudflare MCP Portal
- `com.atlassian/atlassian-mcp-server` — Atlassian MCP Registry サーバー
- `codegraph` — ローカルコード解析
- `filesystem` — プロジェクトルート以下のファイルアクセス
- `sonarqube`, `semgrep` — 品質・セキュリティ分析
- `nexus`, `chronos-graph`, `skillport` — ローカルコンテキスト・知識ベース

## トラブルシューティング

- 認証が必要なサーバーでは、`apm.yml` に参照された環境変数が設定されていることを
  確認してください。
- 任意サーバーを有効にする場合は、その定義を `mcp/optional-servers.yaml` から
  `apm.yml` の `dependencies.mcp` に移してから `make sync-mcp` を実行してください。
