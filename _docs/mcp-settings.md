# MCP Client 設定ガイド (APM 直接管理)

このプロジェクトでは、有効にする MCP サーバーを `apm.yml` の
`dependencies.mcp` に定義し、`make sync-mcp` によって各クライアントの設定を生成します。
`mcp/optional-servers.yaml` の任意サーバーは自動同期されません。
各ツールは直接 stdio プロセス、リモート SSE、またはリモート Streamable HTTP
エンドポイントに接続します。

## 共通設定

設定ファイルは APM によって自動生成されるため、通常は手動で編集する必要はありません。
必要に応じて `apm.yml` の `dependencies.mcp` セクションを変更し、以下を実行してください。

```bash
make sync-mcp
```

## 各ツールでの設定ファイル場所

| ツール | 設定ファイル |
| :--- | :--- |
| Gemini CLI | `~/.gemini/settings.json` |
| Claude Code | `~/.claude.json` |
| Codex CLI | `~/.codex/config.toml` |
| OpenCode | `~/.config/opencode/opencode.jsonc` |
| Cursor | `~/.cursor/mcp.json` |
| Antigravity | `~/.gemini/antigravity/mcp_config.json` |

## サーバー一覧

`make sync-mcp` 実行時、`apm.yml` に記載された有効なサーバーがクライアントごとの対応形式で登録されます。APM はサーバー単位の `enabled` フラグを扱わないため、無効にしておくサーバーは `dependencies.mcp` に入れず、任意カタログに置きます。

- `cf-mcp-portal`, `cf-mcp-portal-work` — Streamable HTTP
- `com.atlassian/atlassian-mcp-server` — MCP Registry
- `codegraph` — ローカルコード解析
- `filesystem` — `npx @modelcontextprotocol/server-filesystem`
- `sonarqube`, `semgrep` — 品質・セキュリティ分析
- `nexus`, `chronos-graph`, `skillport` — ローカルコンテキスト

無効の任意サーバーは [`mcp/optional-servers.yaml`](../mcp/optional-servers.yaml) を参照してください。
