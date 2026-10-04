# Claude Code / Opcode 使用ガイド

🤖 Claude Code のセットアップが完了しました！

## MCP 設定

Claude Code のMCP定義はリポジトリルートの `apm.yml` が正本です。
`make setup-claude` は、Claude Codeが対応するAPMのユーザースコープを使って、
グローバルMCPを同期します。

1. `~/.apm/apm.yml` がなければ、リポジトリの `apm.yml` へシンボリックリンクします。
2. `apm install --global --only mcp --target claude` を実行します。
3. APMが `$CLAUDE_CONFIG_DIR/.claude.json`、または未設定なら
   `~/.claude.json` の `mcpServers` を更新します。

APMは既存のClaudeユーザー設定とMCPを維持しながら管理対象を更新します。
`.claude.json` 自体はユーザー状態を含むため、プロジェクト出力へのリンクで置き換えません。
別の `~/.apm/apm.yml` が既にある場合は上書きせず、セットアップを停止します。
APMは更新時にatomic replaceを行うため、有効な `.claude.json` がシンボリックリンクの
場合も同期を停止し、リンク先を置き換えないようにします。
MCPだけを再同期する場合は `make sync-claude-apm-mcp` を実行してください。

## 🚀 使用方法
1. プロジェクトディレクトリに移動: `cd your-project-directory`
2. Claude Code を開始: `claude`

## 📋 初回セットアップコマンド
- `summarize this project`
- `/help`

## 🖥️ Opcode (GUI)
- **起動方法**: アプリケーションメニューから 'Opcode' を選択、または `/opt/opcode/opcode`
- **機能**: プロジェクト管理、使用状況分析、MCPサーバー管理等

## 🩺 トラブルシューティング
設定に不備があると感じた場合は、ターミナルで以下を実行してください。
```bash
make check-claude
```

## 📚 ドキュメント
- [Claude Code](https://docs.anthropic.com/claude-code)
- [Opcode](https://github.com/winfunc/opcode)
- [MCP 設定・運用ガイド](../../mcp/README.md)
