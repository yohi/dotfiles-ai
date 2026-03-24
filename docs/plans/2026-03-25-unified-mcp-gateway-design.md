# Unified MCP Gateway Design

## Overview
各AIエージェント（Gemini CLI, Antigravity, Claude Code）やIDE（Cursor, VSCode）で個別に管理されていたMCPサーバー設定を、**Docker MCP Gateway** をハブとして一元化します。

これにより、MCPサーバーの追加・変更は一箇所（`mcp/` 配下）を更新するだけで、全てのツールに反映されるようになります。

## Architecture

### 1. Source of Truth (唯一のソース)
*   **ファイル**: `mcp/catalog.json` (または `mcp/config.yaml`)
*   **役割**: 利用したい全てのMCPサーバー（GitHub, Playwright, Skillport等）の定義をここに集約します。

### 2. Synchronization Mechanism (同期メカニズム)
*   **スクリプト**: `scripts/sync-mcp-configs.sh`
*   **動作**:
    1.  `mcp/catalog.json` を Docker MCP Gateway が読み込める形式 (`~/.docker/mcp/catalogs/custom.yaml`) に変換・配置します。
    2.  各ツールの設定ファイルを、`docker mcp gateway run` (stdio方式) を使用する定義に書き換えます。
        *   `~/.gemini/settings.json`
        *   `antigravity/mcp_config.json`
        *   `ide/cursor/mcp.json` (または `~/.cursor/mcp.json`)

### 3. Unified Tool Configuration (統一されたツール設定)
全てのツールで以下の `stdio` 設定が共通して使われます。

```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "command": "docker",
      "args": [
        "mcp", "gateway", "run",
        "--catalog", "/home/y_ohi/.docker/mcp/catalogs/bootstrap.yaml",
        "--catalog", "/home/y_ohi/.docker/mcp/catalogs/custom.yaml"
      ]
    }
  }
}
```

## Implementation Steps
1.  既存の各設定ファイル（Cursor, Antigravity等）からMCPサーバー定義を抽出し、`mcp/catalog.json` に統合する。
2.  設定ファイルの絶対パス展開（`~` や `${HOME}` の置換）を含む同期スクリプトを実装する。
3.  各ツールの設定を Gateway 経由に切り替える。
4.  動作検証を行う。

## Success Criteria
*   Gemini CLI から `/mcp list` で Gateway 経由のツールが見えること。
*   Antigravity からツールが呼び出せること。
*   Cursor の MCP サーバー一覧が Gateway 1つに集約されていること。
