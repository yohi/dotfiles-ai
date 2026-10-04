# MCP 同期ガイド

有効な MCP サーバーの定義元は、リポジトリルートの `apm.yml` です。
生成済みのエージェント設定ファイルは直接編集しないでください。

## 同期方式

- `make sync-mcp` は `apm.yml` の `targets:` に記載された OpenCode、Codex、
  Antigravity を一括で同期します。APMのstale cleanupが別ターゲットの設定を
  消さないよう、これらを個別ターゲット指定で順番にインストールしません。
- Claude CodeはAPMのユーザースコープを使います。`make setup-claude` は
  `~/.apm/apm.yml` をリポジトリの `apm.yml` へリンクし、Claude向けMCPを
  `~/.claude.json` または `$CLAUDE_CONFIG_DIR/.claude.json` に反映します。
- OpenCodeのAPM出力 `opencode.json` はプロジェクトスコープです。
  `setup-opencode` がこの出力をグローバル設定から直接参照させます。
  `opencode/opencode.jsonc` も `apm.yml` から生成される別のOpenCode設定です。
- Codexは `.codex/config.toml`、Antigravity CLIは
  `.agents/mcp_config.json` をAPMプロジェクト出力として使い、セットアップで
  各クライアントのグローバル設定先へリンクします。

ユーザースコープClaude設定を適用するとき、既存の別 `~/.apm/apm.yml` は
上書きしません。設定手順の詳細、管理対象サーバー、環境変数、トラブル対応は
[MCP 設定・運用ガイド](../../mcp/README.md) を参照してください。
