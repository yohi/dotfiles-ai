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
  - `make sync-mcp` を実行すると、**APM (Agent Package Manager)** の標準機能によって以下のファイルが自動生成・更新されます。
    - **`mcp/config.yaml`**: Docker MCP Gateway で有効化するサーバー一覧。
    - **`mcp/catalogs/custom.yaml`**: Docker MCP Gateway のカスタムカタログ定義。
    - **各エージェントの設定ファイル**: `gemini/settings.json`, `.mcp.json`, `opencode/opencode.jsonc`, `ide/cursor/mcp.json`, `codex/config.toml` 等。
- **プレースホルダー置換**: `__GATEWAY_URL__`, `__HOME__`, `__REPO_ROOT__` は生成時に動的に置換されます。また、`${VAR}` 形式の環境変数も APM によって展開されます。

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

- **`make sync-mcp`**: `apm install` を実行し、`apm.yml` の定義に基づいて各エージェントの設定ファイルと Gateway 実行設定を同期。
- **`make setup-docker-mcp`**: Docker MCP Gateway の systemd サービスと環境をセットアップ。
- **`_scripts/check-skillport-version.sh`**: Skillport イメージが PyPI の最新版と一致するか確認。

---

## 5. Docker MCP Gateway の OAuth 認証 (Docker Desktop 不要 / CLI Only)

Docker Desktop アプリを起動せず、`docker mcp` CLI だけでリモート OAuth 系サーバー（Sentry Remote, Apify 等）の認証を完了させる手順。

### 前提条件

1. **`docker mcp` CLI プラグインが最新版であること**
   - 古いビルドには CE (Community Edition) Mode の OAuth 実装が存在せず、常に Docker Desktop のバックエンドソケット (`~/.docker/desktop/tools.sock`) への接続を試みて `dial unix ...: no such file or directory` で失敗する。
   - 確認: `docker mcp version`
   - 更新:

     ```bash
     curl -sL -o /tmp/docker-mcp.tar.gz \
       https://github.com/docker/mcp-gateway/releases/latest/download/docker-mcp-linux-amd64.tar.gz
     tar -xzf /tmp/docker-mcp.tar.gz -C /tmp
     rm -f ~/.docker/cli-plugins/docker-mcp   # 実行中バイナリの "text file busy" 対策
     cp /tmp/docker-mcp ~/.docker/cli-plugins/docker-mcp
     chmod +x ~/.docker/cli-plugins/docker-mcp
     ```

2. **Docker Credential Helper が設定されていること**
   - 未設定だと `invalid config: empty credsStore` → `docker-credential-notfound: executable file not found` で失敗する。
   - Linux Desktop 環境（`org.freedesktop.secrets` が D-Bus 上で稼働中、gnome-keyring 等）の場合:

     ```bash
     curl -sL -o ~/.local/bin/docker-credential-secretservice \
       https://github.com/docker/docker-credential-helpers/releases/latest/download/docker-credential-secretservice-v0.9.8.linux-amd64
     chmod +x ~/.local/bin/docker-credential-secretservice
     ```

     `~/.docker/config.json` に `"credsStore": "secretservice"` を追加する。
   - ヘッドレス環境では `pass`（GPG バックエンド）用の `docker-credential-pass` を使用する。

### 認証手順

```bash
export DOCKER_MCP_USE_CE=true
docker mcp oauth authorize <server-name> --open-browser
docker mcp oauth ls   # 認証状態の確認
```

- ローカルに `http://127.0.0.1:<port>/callback` が立ち、ブラウザでの認可完了を待機する。
- 認可後は Docker のプロキシページ (`https://mcp.docker.com/oauth/callback`) を経由するが、これは `state` パラメータからポート番号を読み取ってブラウザ側 JS で `127.0.0.1:<port>` へクライアントサイド・リダイレクトする設計であり、Docker Desktop 非稼働でも機能する。
- **待機コマンドにタイムアウトを付けずに実行すること**（ブラウザでの操作が完了するまで待つ必要がある）。

### 公式カタログ未収録のリモートサーバーを追加する

[docker/mcp-registry](https://github.com/docker/mcp-registry) に定義済みでも、Docker 公式カタログ (`desktop.docker.com`) への反映にはラグがあり、`docker mcp oauth authorize <name>` が `server <name> not found in catalog` で失敗することがある。その場合はローカルに独自カタログとして登録する。

```bash
# 1. registry から定義を取得
mkdir -p /tmp/mcp-def && curl -sL \
  -o /tmp/mcp-def/server.yaml \
  https://raw.githubusercontent.com/docker/mcp-registry/main/servers/<name>/server.yaml

# 2. oauth フィールドのスキーマ差異を手動で修正する場合がある（配列 -> providers: 配下）
#    oauth:
#      providers:
#        - provider: <name>
#          secret: <name>.personal_access_token
#          env: <NAME>_PERSONAL_ACCESS_TOKEN

# 3. 独立カタログとして登録（file:// は ~/.docker/mcp/catalogs/ 配下の相対/絶対パス）
docker mcp catalog create local-<name> --title "Local <Name>" \
  --server "file:///tmp/mcp-def/server.yaml"
```

> [!WARNING]
> `docker mcp profile server add` はプロファイルへの追加にしかならず、`docker mcp oauth authorize` からは引き続き "not found in catalog" となる。**`docker mcp catalog create` での正式なカタログ登録が必須**。
> また、本リポジトリの `mcp/catalogs/custom.yaml`（`~/.docker/mcp/catalogs/custom.yaml` へのシンボリックリンク）は `apm.yml` から自動生成される SSOT 管理対象のため、上記の一時的な調査・登録には**絶対に使用しないこと**。独立カタログ名（`local-<name>` 等）で登録すること。

### トラブルシューティング

| エラー | 原因 | 対処 |
| :--- | :--- | :--- |
| `dial unix .../tools.sock: no such file or directory` | `docker mcp` バイナリが古く CE Mode 未対応。常に Docker Desktop 接続を試みる | バイナリを最新版に更新 |
| `invalid config: empty credsStore` → `docker-credential-notfound` | Credential Helper 未設定 | `docker-credential-secretservice`（Desktop環境）または `docker-credential-pass`（ヘッドレス）を導入し `credsStore` を設定 |
| `server <name> not found in catalog` | サーバーが公式カタログ未収録、または `catalog create` で正式登録されていない | `docker mcp catalog create local-<name> --server file://...` で登録 |
| `callback timeout: context canceled` | ブラウザでの認可待ちの間にコマンド自体がタイムアウト/中断された | タイムアウトなしで再実行し、表示された URL をブラウザで開いて認可を完了する |
| `invalid_target` (The resource parameter does not match...) | Sentryなどの一部の認可サーバーが、`docker mcp` が自動付与する `resource` パラメータを拒否している | 認可URLから `&resource=...` を手動で削除してブラウザで開く。※本リポジトリの `make auth-mcp` （`_scripts/auth-mcp.py`）では自動的にこのパラメータを除去してブラウザを開くよう対策されています |

