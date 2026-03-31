# Unified MCP Gateway Design (SSE Mode)

## Overview
各AIエージェント（Gemini CLI, Antigravity, Claude Code）やIDE（Cursor, VSCode）で個別に管理されていたMCPサーバー設定を、**Docker MCP Gateway (SSE Mode)** をハブとして一元化します。

SSE（Server-Sent Events）方式を採用することで、エージェント起動時のタイムアウト問題を解消し、バックグラウンドで常に最新のMCPサーバー群が利用可能な状態を維持します。

## Architecture

### 1. Source of Truth (唯一のソース)
*   **ファイル**: `mcp/catalogs/custom.yaml.template`
*   **役割**: 利用したい全てのMCPサーバーの定義をここに集約します。
*   **パス展開**: `make mcp-render` コマンドにより、`__HOME__` プレースホルダを実パスに置換した `mcp/catalogs/custom.yaml` を生成します。

### 2. Background Service (ハブ)
*   **サービス名**: `docker-mcp-gateway.service` (systemd ユーザーサービス)
*   **起動コマンド**:
    ```bash
    docker mcp gateway run \
      --transport sse \
      --port 10888 \
      --catalog ~/.docker/mcp/catalogs/bootstrap.yaml \
      --catalog ~/.docker/mcp/catalogs/custom.yaml \
      --secrets .env
    ```
*   **認証**: `MCP_GATEWAY_AUTH_TOKEN` を使用し、安全な SSE 通信を確立します。

### 3. Client Configurations (クライアント)
全てのクライアントを `http://localhost:10888/sse` に向けます。

*   **Gemini CLI (`~/.gemini/settings.json`)**:
    ```json
    "mcpServers": {
      "docker-mcp-gateway": {
        "url": "http://localhost:10888/sse"
      }
    }
    ```
*   **Antigravity (`antigravity/mcp_config.json`)**:
    上記と同様。
*   **Cursor (`ide/cursor/mcp.json`)**:
    Cursor は直接 SSE URL をサポートしていないため、プロキシスクリプトを介して接続します。

## Implementation Steps
1.  `docker-mcp-gateway.service` の systemd ユニットファイルを作成・有効化する。
2.  各クライアントの設定ファイルを、SSE URL を参照するように更新する。
3.  Cursor 用に `scripts/mcp-sse-proxy.js` を作成する。
4.  `make setup-docker-mcp` でこれらの一括適用ができるように Makefile を更新する。

## Success Criteria
*   `systemctl --user is-active docker-mcp-gateway.service` が `active` であること。
*   Gemini CLI の `/mcp list` でツール群が表示され、`Connected` となること。
*   Antigravity, Cursor からも同様にツールが利用可能なこと。
