# MCP SSE/Remote 接続 設定リファレンス (2026年3月版)

主要な AI エージェントおよび IDE における、MCP (Model Context Protocol) リモート接続（SSE / Streamable HTTP）の正確な設定キーと対応状況のまとめです。

---

## 1. 接続設定キー・対応一覧

Google 製品内でも「IDE vs CLI」でキーが異なる点、および SSE と Streamable HTTP での使い分けが重要です。

| ツール名 | SSE/Remote 対応 | 正しいキー名 | 設定ファイル (例) |
| :--- | :---: | :--- | :--- |
| **Antigravity (IDE)** | ◎ | **`serverUrl`** | `~/.gemini/antigravity/mcp_config.json` |
| **Gemini CLI** | ◎ | **`url`** / `httpUrl` | `~/.gemini/settings.json` |
| **Claude Code** | ◎ | **`url`** | `~/.claude/config.json` / `.mcp.json` |
| **Cursor** | 〇 | **`url`** | `.cursor/mcp.json` |
| **OpenCode** | 〇 | **`url`** | `opencode.json` |
| **Codex (CLI)** | 〇 | **`url`** | `~/.codex/config.toml` |

---

## 2. 各ツールの正確な設定コード例

### ■ Antigravity (Google IDE)
Google のエージェント特化型 IDE。一貫して **`serverUrl`** を使用します。`url` では認識されないため注意が必要です。

```json
{
  "mcpServers": {
    "remote-tool": {
      "serverUrl": "https://mcp-server.example.com/sse",
      "type": "sse"
    }
  }
}
```

### ■ Gemini CLI
公式ドキュメント（geminicli.com）の通り、SSE 接続には **`url`** を使用します。なお、上位プロトコルである Streamable HTTP を使用する場合は `httpUrl` を指定します。

```json
{
  "mcpServers": {
    "internal-tool": {
      "url": "https://api.gemini-mcp.dev/sse"
    }
  }
}
```

### ■ Claude Code (Anthropic)
標準 MCP 仕様に準拠。`type: "sse"` と **`url`** を組み合わせます。

```json
{
  "mcpServers": {
    "remote-fetcher": {
      "type": "sse",
      "url": "https://api.anthropic.com/mcp/sse"
    }
  }
}
```

### ■ Cursor
設定画面またはプロジェクトごとの JSON で管理。**`url`** キーのみを記述することでリモート接続として自動判定されます。

```json
{
  "mcpServers": {
    "cursor-remote": {
      "url": "https://api.cursor.sh/mcp/sse"
    }
  }
}
```

### ■ OpenCode / Codex
これらはシンプルに **`url`** を指定する形式が一般的です。

**OpenCode (`opencode.json`):**
```json
{
  "mcp": {
    "remote-agent": {
      "type": "remote",
      "url": "https://mcp.opencode.dev/mcp"
    }
  }
}
```

---

## 3. ローカル Docker MCP Gateway 運用メモ

このリポジトリでは、ローカルの Docker MCP Gateway を `http://127.0.0.1:10888/sse` で常駐させ、各クライアントをそこへ SSE 接続させます。

- クライアント設定の SSOT は `mcp/servers.yaml`
- 反映は `make sync-mcp`
- 現在のローカル Gateway 接続ではクライアント側 Bearer ヘッダーを必須としていません

---

## 4. 設定時のハマりどころ

1. **Google ツールのキー名の不一致:**
   - **Antigravity** (IDE) は **`serverUrl`**。
   - **Gemini CLI** は **`url`** (SSE用) または **`httpUrl`** (Streamable用)。
   同じ Google 製でも、これらを間違えると「接続失敗」や「設定が無視される」原因となります。
2. **自動検出の挙動:**
   - `Cursor` 等は `url` キーの存在だけで SSE と判断しますが、`Claude Code` は `type: "sse"` の明示的な指定が推奨されます。
3. **認証の有無は Gateway 実装依存:**
   - 一般論としては `headers.Authorization` を使う構成があります。
   - ただしこのリポジトリのローカル Docker MCP Gateway は、クライアント設定としてはヘッダー必須にしていません。
