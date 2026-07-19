# MCP (Model Context Protocol) 使用ガイド

このプロジェクトでは、すべての MCP サーバーを `apm.yml` で直接管理しています。

## 設定の同期

- `make sync-mcp` — `apm.yml` を元に各エージェント（Claude Code, OpenCode, VSCode, Cursor, Antigravity）の MCP 設定を再生成（Gemini CLI や Codex CLI は自動同期対象外）

## 管理対象サーバー

`apm.yml` の `dependencies.mcp` に定義されたサーバーがそのまま各 AI ツールで
利用可能になります。主なサーバーは以下の通りです。

- `sqlite` — ローカル SQLite DB 操作
- `filesystem` — プロジェクトルート以下のファイルアクセス
- `sequentialthinking` — 段階的な思考支援
- `github-official` — GitHub 連携
- `aws-api`, `aws-cdk-mcp-server`, `aws-diagram`, `aws-documentation`,
  `aws-terraform` — AWS 関連支援
- `sentry-remote` — Sentry リモート連携
- `nexus`, `chronos-graph`, `skillport` — ローカルコンテキスト・知識ベース

## トラブルシューティング

- `.env` が存在し、必要なトークンが設定されていることを確認してください。
- `github-mcp-server` バイナリが `PATH` に含まれている必要があります。
  未インストールの場合は以下を実行してください。

  ```bash
  go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest
  ```

- AWS サーバーを使用する場合は `AWS_PROFILE` / `AWS_REGION` が設定されていることを
  確認してください。
