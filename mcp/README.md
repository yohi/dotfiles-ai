# MCP (Model Context Protocol) 設定・運用ガイド

このディレクトリには、本リポジトリの各種 AI エージェントで使用される MCP サーバーの設定、管理スクリプト、および接続仕様のリファレンスが含まれています。

## 1. 設定済み MCP サーバー

### Docker MCP Gateway (SSE)
複数の MCP サーバーを Docker コンテナ内で一括実行する集中管理ゲートウェイです。
- **ステータス**: 有効
- **ゲートウェイ URL**: `http://127.0.0.1:10888/sse`
- **リファレンス**: [docker/mcp-registry](https://github.com/docker/mcp-registry)
- **Gateway で有効化されるサーバー (`mcp/config.yaml` で管理):**
  - **Filesystem**: ワークスペースおよび HOME ディレクトリへのアクセス。
  - **SQLite**: ローカル DB 操作。
  - **Sequential Thinking**: 複雑な思考プロセスの補助。
  - **Skillport**: エージェントスキルの検索・ロード。
  - **GitHub Official**: GitHub 連携。

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

本プロジェクトでは、MCP 設定を **`mcp/servers.yaml`** を唯一の正解（Single Source of Truth）として管理しています。

- **`mcp/servers.yaml`**: 
  - 全 AI エージェント（Gemini, Claude, Cursor, VSCode, Antigravity, OpenCode, Codex 等）のマスター設定。
  - 各サーバーの定義（Docker イメージ、環境変数、ボリュームマウント等）と、各エージェントがどのサーバーを利用するかを定義します。
- **自動生成されるファイル**:
  - `make sync-mcp` を実行すると、`_scripts/render-mcp-configs.py` によって以下のファイルが自動生成・更新されます。
    - **`mcp/config.yaml`**: Docker MCP Gateway で有効化するサーバー一覧。
    - **`mcp/catalogs/custom.yaml`**: Docker MCP Gateway のカスタムカタログ定義。
    - **各エージェントの設定ファイル**: `gemini/settings.json`, `claude/settings.json`, `opencode/opencode.jsonc`, `.cursor/mcp.json`, `codex/config.toml` 等。
- **プレースホルダー置換**: `__GATEWAY_URL__`, `__HOME__`, `__REPO_ROOT__` は生成時に動的に置換されます。また、`${VAR}` 形式の環境変数も `_scripts/render-mcp-configs.py` によって展開されます。

---

## 3. 各ツールの接続仕様リファレンス

本プロジェクトでは **Unified SSE Gateway** パターンを採用しており、各ツールは `http://127.0.0.1:10888/sse?server=サーバー名` という形式で個別のサーバーに接続します。

### 接続設定キー・対応一覧

| ツール名 | SSE/Remote 対応 | 正しいキー名 | 設定ファイル (例) | 形式 |
| :--- | :---: | :--- | :--- | :--- |
| **Antigravity (IDE)** | ◎ | **`serverUrl`** | `~/.gemini/antigravity/mcp_config.json` | JSON |
| **Gemini CLI** | ◎ | **`url`** | `~/.gemini/settings.json` | JSON |
| **Claude Code** | ◎ | **`url`** | `.claude.json` | JSON |
| **Cursor** | 〇 | **`url`** | `.cursor/mcp.json` | JSON |
| **VSCode** | 〇 | **`url`** | `ide/vscode/settings.json` | JSON |
| **OpenCode** | 〇 | **`url`** | `opencode/opencode.jsonc` | JSONC |
| **Codex CLI** | 〇 | **`command`** | `~/.codex/config.toml` | TOML |

### 特筆すべき設定仕様

#### ■ Codex CLI (TOML)
Codex CLI は現在 SSE にネイティブ対応していないため、`curl` をブリッジとして使用する設定を自動生成します。
```toml
[mcp_servers.SQLite]
command = "curl"
args = ["-s", "http://127.0.0.1:10888/sse?server=SQLite", "-H", "Authorization: Bearer ..."]
```

#### ■ ChronosGraph (Local)
`chronos-graph` はゲートウェイを経由せず、各エージェントから直接 `uv tool run` で実行されます。この設定も `servers.yaml` から各エージェントの設定ファイルに直接埋め込まれます。

---


## 4. メンテナンスコマンド

- **`make sync-mcp`**: `servers.yaml` と `config.yaml` から各エージェント固有の設定ファイルと Gateway 実行設定を同期。
- **`make setup-docker-mcp`**: Docker MCP Gateway の systemd サービスと環境をセットアップ。
- **`_scripts/check-skillport-version.sh`**: Skillport イメージが PyPI の最新版と一致するか確認。
