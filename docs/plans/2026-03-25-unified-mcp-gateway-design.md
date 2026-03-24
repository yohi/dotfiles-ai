# Unified MCP Gateway Design

## Overview
各AIエージェント（Gemini CLI, Antigravity, Claude Code）やIDE（Cursor, VSCode）で個別に管理されていたMCPサーバー設定を、**Docker MCP Gateway** をハブとして一元化します。

これにより、MCPサーバーの追加・変更は一箇所（`mcp/` 配下）を更新するだけで、全てのツールに反映されるようになります。

## Architecture

### 1. Source of Truth (唯一のソース)
*   **ファイル**: `mcp/catalogs/custom.yaml.template`
*   **役割**: 利用したい全てのMCPサーバー（GitHub, Playwright, Skillport等）の定義をここに集約します。環境変数（`__REPO_ROOT__`等）をプレースホルダとして含めることができます。

### 2. Synchronization & Deployment (同期とデプロイ)
*   **スクリプト**: `scripts/setup-docker-mcp.sh` および `Makefile` (`mcp-render` ターゲット)
*   **動作**:
    1.  `mcp/catalogs/custom.yaml.template` をレンダリングし、実際のパスに展開された `~/.docker/mcp/catalogs/custom.yaml` を生成します。
    2.  SSE 常駐 Gateway (systemd サービス) を起動し、レンダリングされたカタログを読み込ませます。
    3.  各ツール（Gemini CLI, Cursor, Antigravity等）は、`scripts/mcp-sse-proxy.js` を介してこの SSE Gateway に接続します。

### 3. Unified Tool Configuration (統一されたツール設定)
全てのツールで以下の `proxy` 設定が共通して使われます（Cursor 等の stdio 経由の場合）。

```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "command": "node",
      "args": [
        "$HOME/dotfiles/components/dotfiles-ai/scripts/mcp-sse-proxy.js",
        "http://localhost:10888/sse"
      ]
    }
  }
}
```

直接 SSE をサポートするツール（Antigravity 等）は、直接 `http://localhost:10888/sse` に接続します。

## Implementation Steps
1.  既存の各設定ファイル（Cursor, Antigravity等）からMCPサーバー定義を抽出し、`mcp/catalog.json` に統合する。
2.  設定ファイルの絶対パス展開（`~` や `${HOME}` の置換）を含む同期スクリプトを実装する。
3.  各ツールの設定を Gateway 経由に切り替える。
4.  動作検証を行う。

## Success Criteria
*   Gemini CLI から `/mcp list` で Gateway 経由のツールが見えること。
*   Antigravity からツールが呼び出せること。
*   Cursor の MCP サーバー一覧が Gateway 1つに集約されていること。
