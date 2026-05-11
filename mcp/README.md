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

### Chronos Graph & Nexus (Docker Integration)
Docker MCP Gateway 経由で統合管理される、ローカル知識ベース・長期記憶システムです。
- **ステータス**: 有効（Docker イメージとして実行され、SSE 経由で全エージェントから利用可能）
- **機能**:
  - **ChronosGraph**: ローカル SQLite (`~/.context-store/memories.db`) をバックエンドとした、コンテキストの長期記憶とナレッジグラフ管理。
  - **Nexus**: プロジェクトコードの高速なセマンティック検索・インデックス管理。
- **実装**: `mcp/Dockerfile.*` でビルドされたイメージを使用。設定は `apm.yml` で一括管理されます。

### Atlassian MCP (Direct / Streamable HTTP)
Atlassian 製品（Jira, Confluence）用の公式 MCP サーバーです。
- **ステータス**: 有効（Gemini CLI / Claude Code から直接接続。OAuth 認証をネイティブに処理）
- **エンドポイント**: `https://mcp.atlassian.com/v1/mcp`


---

## 2. 設定管理の仕組み (SSOT)

本プロジェクトでは、MCP 設定をリポジトリルートの **`apm.yml`** を唯一の正解（Single Source of Truth）として管理しています。

> [!WARNING]
> **`mcp/config.yaml` や各エージェントの設定ファイルを直接編集しないでください。**
> これらのファイルは `make sync-mcp` 実行時に `apm.yml` から自動生成されるため、手動の変更は上書きされます。設定を変更する場合は必ず `apm.yml` を修正し、`make sync-mcp` を実行してください。

- **`apm.yml`**: 
  - 全 AI エージェント（Gemini, Claude, Cursor, VSCode, Antigravity, OpenCode, Codex 等）のマスター設定。
  - 各サーバーの定義（Docker イメージ、環境変数、ボリュームマウント等）と、各エージェントがどのサーバーを利用するかを定義します。
- **自動生成されるファイル**:
  - `make sync-mcp` を実行すると、`_scripts/render-mcp-configs.py` によって以下のファイルが自動生成・更新されます。
    - **`mcp/config.yaml`**: Docker MCP Gateway で有効化するサーバー一覧。
    - **`mcp/catalogs/custom.yaml`**: Docker MCP Gateway のカスタムカタログ定義。
    - **各エージェントの設定ファイル**: `gemini/settings.json`, `.mcp.json`, `opencode/opencode.jsonc`, `ide/cursor/mcp.json`, `codex/config.toml` 等。
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
Codex CLI は現在 SSE にネイティブ対応していないため、`npx mcp-remote` をブリッジとして使用する設定を自動生成します。
```toml
[mcp_servers.SQLite]
command = "npx"
args = ["-y", "mcp-remote", "http://127.0.0.1:10888/sse?server=SQLite", "-H", "Authorization: Bearer ..."]
```

#### ■ ChronosGraph & Nexus
Docker MCP Gateway を介して統合的に提供されます。ボリュームマウントにより、ホスト上の `~/.context-store` および `~/.nexus` にデータを永続化します。

---


## 4. メンテナンスコマンド

- **`make sync-mcp`**: `servers.yaml` と `config.yaml` から各エージェント固有の設定ファイルと Gateway 実行設定を同期。
- **`make setup-docker-mcp`**: Docker MCP Gateway の systemd サービスと環境をセットアップ。
- **`_scripts/check-skillport-version.sh`**: Skillport イメージが PyPI の最新版と一致するか確認。
