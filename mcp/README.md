# MCP (Model Context Protocol) 設定

このディレクトリには、本リポジトリの各種 AI エージェントで使用される MCP サーバーの設定および管理スクリプトが含まれています。

## 設定済み MCP サーバー

### 1. Docker MCP Gateway (SSE)
複数の MCP サーバーを Docker コンテナ内で一括実行する集中管理ゲートウェイです。
- **ステータス**: 有効
- **ゲートウェイ URL**: `http://localhost:10888/sse`
- **リファレンス**: [docker/mcp-registry](https://github.com/docker/mcp-registry)
- **含まれるツール (`mcp/config.yaml` で管理):**
  - **GitHub Official**: [リファレンス](https://github.com/docker/mcp-registry/blob/main/servers/github.yaml)
  - **Filesystem**: [リファレンス](https://github.com/docker/mcp-registry/blob/main/servers/filesystem.yaml)
  - **SQLite**: [リファレンス](https://github.com/docker/mcp-registry/blob/main/servers/sqlite.yaml)
  - **Sequential Thinking**: [リファレンス](https://github.com/docker/mcp-registry/blob/main/servers/sequentialthinking.yaml)
  - **Playwright**, **Tavily**, **Chrome DevTools** など。

### 2. Atlassian MCP (httpUrl 直接接続)
Atlassian 製品（Jira, Confluence）用の公式 MCP サーバーです。
- **ステータス**: 有効（Gemini CLI から httpUrl で直接接続。Streamable HTTP を使用して OAuth 認証をネイティブに処理）
- **リポジトリ**: [atlassian/atlassian-mcp-server](https://github.com/atlassian/atlassian-mcp-server)
- **エンドポイント**: `https://mcp.atlassian.com/v1/mcp`

### 3. Skillport (カスタム Docker イメージ)
専門スキルの開発および AI スキル管理ツールです。
- **ステータス**: 有効（Docker MCP Gateway 経由で実行）
- **リポジトリ**: [gotalab/skillport](https://github.com/gotalab/skillport)
- **イメージ**: `ghcr.io/yohi/skillport:latest`
- **機能**: エージェントスキルのインデックス検索およびロード。

## 設定ファイル
- `servers.yaml`: 全 AI エージェント（Gemini, Claude 等）のマスター設定ファイル。
- `config.yaml`: Docker MCP Gateway 内で有効にするサーバーを定義。
- `catalogs/custom.yaml.template`: カスタムサーバー（Skillport 等）の定義テンプレート。

## メンテナンススクリプト
- `make sync-mcp`: `servers.yaml` から各エージェント固有の設定ファイルへ同期を実行。
- `make setup-docker-mcp`: Docker MCP Gateway の systemd サービスと環境をセットアップ。
- `scripts/check-skillport-version.sh`: Skillport イメージが PyPI の最新版と一致するか確認。
