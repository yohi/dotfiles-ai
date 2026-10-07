# MCP Client 設定ガイド (APM 直接管理)

有効にするMCPサーバーの正本は、`apm.yml` の `dependencies.mcp` です。
`mcp/optional-servers.yaml` は無効候補の参照カタログで、自動同期されません。
各ツールは stdio、リモート SSE、または Streamable HTTP で接続します。

## 同期方法

`make sync-mcp` は `apm.yml` の `targets:` に宣言された OpenCode、Codex、
Antigravity を1回のAPMインストールで同期します。APMのstale cleanupにより
別ターゲットの設定が消えないよう、これらをターゲットごとに別々にインストールしません。

```bash
make sync-mcp
```

Claude CodeはAPMユーザースコープを使うため、グローバル同期は `make setup-claude`
または `make sync-claude-apm-mcp` で行います。APM manifestがない場合、
`~/.apm/apm.yml` をこのリポジトリの `apm.yml` へリンクし、ClaudeのMCP設定を
ユーザー設定へマージします。別のユーザーAPM manifestがすでにある場合は上書きせず停止します。

## クライアント設定の出力先

| クライアント | APM出力 / 設定先 | グローバル同期 |
| :--- | :--- | :--- |
| Claude Code | `~/.claude.json` または `$CLAUDE_CONFIG_DIR/.claude.json` | APMがユーザースコープで更新。既存の他設定を保持 |
| OpenCode MCP | プロジェクト `opencode.json` | `setup-opencode` が `~/.config/opencode/opencode.json` からリンク |
| OpenCode profile | `opencode/opencode.jsonc` | `make sync-opencode` が `apm.yml` から生成 |
| Codex CLI | プロジェクト `.codex/config.toml` | `setup-codex` が `~/.codex/config.toml` からリンク |
| Antigravity CLI | プロジェクト `.agents/mcp_config.json` | `setup-antigravity` が `~/.gemini/antigravity-cli/mcp_config.json` からリンク |
| Gemini CLI | `~/.gemini/settings.json` | 専用同期 |
| Cursor | `ide/cursor/mcp.json` | 専用同期 |
| VSCode | `ide/vscode/settings.json` | 専用同期 |

CodexのAPM出力が初回生成の場合は、既存のグローバル設定を種として使い、
APMがMCP部分を更新して他のCodex設定を保持します。OpenCodeのAPM出力に含まれる
`${env:NAME}` は、リンク前に `setup-opencode` がOpenCode記法へ正規化します。

## サーバー一覧

`make sync-mcp` 実行時、`apm.yml` に記載したサーバーがクライアント形式に合わせて登録されます。APMはサーバー単位の `enabled` フラグを扱わないため、無効サーバーは `dependencies.mcp` に入れず、任意カタログに置きます。

- `cf-mcp-portal`, `cf-mcp-portal-work` — Streamable HTTP
- `com.atlassian/atlassian-mcp-server` — MCP Registry
- `codegraph` — ローカルコード解析
- `filesystem` — `npx @modelcontextprotocol/server-filesystem`
- `sonarqube`, `semgrep` — 品質・セキュリティ分析
- `nexus`, `chronos-graph`, `skillport` — ローカルコンテキスト

無効の任意サーバーは [`mcp/optional-servers.yaml`](../mcp/optional-servers.yaml) を参照してください。
