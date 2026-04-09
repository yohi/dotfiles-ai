# MCP (Model Context Protocol) 設定・運用ガイド

このディレクトリには、本リポジトリの各種 AI エージェントで使用される MCP サーバーの設定、管理スクリプト、および接続仕様のリファレンスが含まれています。

## 1. 設定済み MCP サーバー

### Docker MCP Gateway (SSE)
複数の MCP サーバーを Docker コンテナ内で一括実行する集中管理ゲートウェイです。
- **ステータス**: 有効
- **ゲートウェイ URL**: `http://127.0.0.1:10888/sse`
- **リファレンス**: [docker/mcp-registry](https://github.com/docker/mcp-registry)
- **含まれるツール (`mcp/config.yaml` で管理):**
  - **Filesystem**: ワークスペースおよび HOME ディレクトリへのアクセス。
  - **SQLite**: ローカル DB 操作。
  - **Sequential Thinking**: 複雑な思考プロセスの補助。
  - **Skillport**: エージェントスキルの検索・ロード。
  - **Chronos Graph**: (Docker 内) コンテキスト永続化およびグラフ管理。

### Chronos Graph (Local / uv)
各クライアント（エージェント）側で `uv` を介して直接実行される MCP サーバーです。
- **ステータス**: 有効（`mcp/servers.yaml` で全エージェントに共通設定）
- **機能**: ローカル SQLite (`~/.context-store/memories.db`) をバックエンドとした、コンテキストの長期記憶とナレッジグラフ管理。
- **実装**: `git+https://github.com/yohi/chronos-graph.git` を `uv tool run` で実行（最新の動作検証済みコミットハッシュによるピン留め情報は `mcp/servers.yaml` で管理）。

### Atlassian MCP (Direct / Streamable HTTP)
Atlassian 製品（Jira, Confluence）用の公式 MCP サーバーです。
- **ステータス**: 有効（Gemini CLI から直接接続。OAuth 認証をネイティブに処理）
- **エンドポイント**: `https://mcp.atlassian.com/v1/mcp`

---

## 2. 設定管理の仕組み (SSOT)

本プロジェクトでは、`mcp/servers.yaml` を **SSOT (Single Source of Truth)** としており、ここから各ツール固有の設定ファイルを自動生成します。

- **`mcp/servers.yaml`**: 全 AI エージェント（Gemini, Claude, Cursor, VSCode, Antigravity, OpenCode 等）のマスター設定。
- **プレースホルダー置換**: `__GATEWAY_URL__`, `__HOME__`, `__REPO_ROOT__` は生成時に動的に置換されます。また、`${VAR}` 形式の環境変数も `_scripts/render-mcp-configs.py` によって展開されます。
- **差異の明示的な管理**: `serverUrl` と `url` のようなツールごとのキー名の違いは、`mcp/servers.yaml` 内でツールごとに定義されています。同期スクリプト（`_scripts/render-mcp-configs.py`）は、これらのキー構造を維持したまま値の展開のみを行います。

---

## 3. 各ツールの接続仕様リファレンス

ツールによって、SSE 接続時に使用する設定キーが異なります。手動で設定を確認・修正する際の参考にしてください。本ガイドは旧 `mcp-support.md` の内容を完全に統合しています。

### 接続設定キー・対応一覧

| ツール名 | SSE/Remote 対応 | 正しいキー名 | 設定ファイル (例) |
| :--- | :---: | :--- | :--- |
| **Antigravity (IDE)** | ◎ | **`serverUrl`** | `~/.gemini/antigravity/mcp_config.json` |
| **Gemini CLI** | ◎ | **`url`** / `httpUrl` | `~/.gemini/settings.json` |
| **Claude Code** | ◎ | **`url`** | `~/.claude/config.json` |
| **Cursor** | 〇 | **`url`** | `.cursor/mcp.json` |
| **OpenCode** | 〇 | **`url`** | `opencode.json` |

### 各ツールの正確な設定コード例

#### ■ Antigravity (Google IDE)
Google のエージェント特化型 IDE。一貫して **`serverUrl`** を使用します。`url` では認識されないため注意が必要です。
```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "serverUrl": "http://127.0.0.1:10888/sse",
      "type": "sse"
    }
  }
}
```

#### ■ Gemini CLI
SSE 接続には **`url`** を使用します。なお、上位プロトコルである Streamable HTTP を使用する場合は `httpUrl` を指定します。
```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "url": "http://127.0.0.1:10888/sse"
    }
  }
}
```

#### ■ Claude Code (Anthropic)
標準 MCP 仕様に準拠。`type: "sse"` と **`url`** を組み合わせます。
```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "type": "sse",
      "url": "http://127.0.0.1:10888/sse"
    }
  }
}
```

---

## 4. メンテナンスコマンド

- **`make sync-mcp`**: `servers.yaml` から各エージェント固有の設定ファイルへ同期を実行。
- **`make setup-docker-mcp`**: Docker MCP Gateway の systemd サービスと環境をセットアップ。
- **`_scripts/check-skillport-version.sh`**: Skillport イメージが PyPI の最新版と一致するか確認。
