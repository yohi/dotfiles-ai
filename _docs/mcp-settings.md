# MCP Client 設定ガイド (Unified SSE Gateway)

このプロジェクトでは、Docker MCP Gateway を使用した **Unified SSE Gateway** (`http://localhost:10888/sse`) を通じて、すべての AI ツールで共通の MCP サーバーを利用します。

各ツールでの設定方法は以下の通りです。

## 1. Gemini CLI (SuperGemini)
Gemini CLI は `gemini/settings.json` を通じて MCP サーバーを管理します。

- **設定ファイルの場所**: `~/.gemini/settings.json` (プロジェクト内の `gemini/settings.json` から生成されます)
- **設定方法**:
  `mcpServers` オブジェクト内にサーバーを追加します。SSE 経由の場合は `url` プロパティを指定します。
  ```json
  {
    "mcpServers": {
      "my-server": {
        "url": "http://localhost:10888/sse?server=my-server"
      }
    }
  }
  ```

## 2. Claude Code
Claude Code は CLI コマンドまたは設定ファイルで SSE サーバーを追加できます。

- **CLIコマンド**:
  ```bash
  claude mcp add --transport sse <name> http://localhost:10888/sse?server=<name>
  ```
- **設定ファイルの場所**: `.claude.json` (プロジェクトルート)

## 3. Codex CLI
Codex CLI は TOML 形式の設定ファイルを使用します。

- **設定ファイルの場所**: `~/.codex/config.toml`
- **設定方法**:
  `[mcp_servers.<name>]` セクションを追加します。
  ```toml
  [mcp_servers.my-server]
  command = "curl"
  args = ["-s", "http://localhost:10888/sse?server=my-server"]
  ```
  *(注: Codex の SSE ネイティブ対応状況により、ブリッジコマンドが必要な場合があります)*

## 4. OpenCode (oh-my-opencode)
OpenCode は JSONC 形式の設定ファイルを使用します。

- **設定ファイルの場所**: `~/.config/opencode/opencode.jsonc`
- **設定方法**:
  `"mcp"` セクションに設定を追加します。
  ```jsonc
  "mcp": {
    "docker-mcp-gateway": {
      "type": "remote",
      "url": "http://127.0.0.1:10888/sse",
      "enabled": true
    }
  }
  ```

## 5. Cursor IDE
Cursor は設定 UI または JSON ファイルで設定できます。

- **GUI**: `Settings > Features > MCP Servers > Add New MCP Server`
  - **Type**: `SSE`
  - **URL**: `http://localhost:10888/sse?server=<name>`
- **設定ファイルの場所**: `~/.cursor/mcp.json`

## 6. Antigravity IDE
Antigravity は `mcp_config.json` を使用します。

- **設定ファイルの場所**: `~/.gemini/antigravity/mcp_config.json`
- **設定方法**:
  `serverUrl` プロパティを使用します。
  ```json
  {
    "mcpServers": {
      "my-server": {
        "serverUrl": "http://localhost:10888/sse?server=my-server"
      }
    }
  }
  ```
