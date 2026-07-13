# MCP Client 設定ガイド (APM 直接管理)

このプロジェクトでは、すべての MCP サーバーを `apm.yml` で定義し、
`make sync-mcp` によって各クライアントの設定ファイルを生成します。
各ツールは直接 stdio プロセスまたはリモート SSE エンドポイントに接続します。

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
| Claude Code | `~/.claude/CLAUDE.md` 配下の MCP 設定 |
| Codex CLI | `~/.codex/config.toml` |
| OpenCode | `~/.config/opencode/opencode.jsonc` |
| Cursor | `~/.cursor/mcp.json` |
| Antigravity | `~/.gemini/antigravity/mcp_config.json` |

## サーバー一覧

`make sync-mcp` 後、上記各ツールに以下のサーバーが登録されます。

- `sqlite` — `uvx mcp-server-sqlite`
- `filesystem` — `npx @modelcontextprotocol/server-filesystem`
- `sequentialthinking` — `npx @modelcontextprotocol/server-sequential-thinking`
- `github-official` — `github-mcp-server stdio`
- `aws-api` — `uvx awslabs.aws-api-mcp-server`
- `aws-cdk-mcp-server` — `uvx awslabs.cdk-mcp-server`
- `aws-diagram` — `uvx awslabs.aws-diagram-mcp-server`
- `aws-documentation` — `uvx awslabs.aws-documentation-mcp-server`
- `aws-terraform` — `uvx awslabs.terraform-mcp-server`
- `sentry-remote` — `https://mcp.sentry.dev/mcp`
- 既存の `nexus`, `chronos-graph`, `skillport` 等
