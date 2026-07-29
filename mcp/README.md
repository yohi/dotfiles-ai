# MCP (Model Context Protocol) 設定・運用ガイド

このディレクトリには、本リポジトリの各種 AI エージェントで使用される
MCP サーバーの設定、管理スクリプト、および接続仕様のリファレンスが含まれています。

## 1. 設定済み MCP サーバー

### APM 直接管理 MCP サーバー

すべての MCP サーバーは `apm.yml` の `dependencies.mcp` で定義され、
`make sync-mcp` によって各エージェントの設定ファイルに反映されます。
主なサーバーは以下の通りです。

- **Filesystem**: プロジェクトルート以下のファイルアクセス。
- **SQLite**: ローカル DB 操作 (`${HOME}/.mcp/sqlite/sqlite.db`)。
- **Sequential Thinking**: 複雑な思考プロセスの補助。
- **GitHub Official**: GitHub 連携。
- **AWS API / CDK / Diagram / Documentation / Terraform**: AWS 関連支援。
- **Sentry Remote**: Sentry リモート連携。
- **Skillport**: エージェントスキルの検索・ロード。

### Chronos Graph & Nexus (Direct APM)

APM によって直接管理されるローカル知識ベース・長期記憶システムです。

- **ステータス**: 有効 (`apm.yml` で定義され、stdio 経由で各エージェントから利用可能)
- **機能**:
  - **ChronosGraph**: ローカル SQLite (`~/.context-store/memories.db`) を
    バックエンドとした、コンテキストの長期記憶とナレッジグラフ管理。
  - **Nexus**: プロジェクトコードの高速なセマンティック検索・インデックス管理。
- **実装**: `apm.yml` で一括管理されます。

### Atlassian MCP (Direct / Streamable HTTP)

Atlassian 製品 (Jira, Confluence) 用の公式 MCP サーバーです。

- **ステータス**: 有効 (API Token 認証。`ATLASSIAN_EMAIL` / `ATLASSIAN_API_TOKEN`
  から `make sync-agents` が `ATLASSIAN_AUTH_HEADER`
  (`Basic base64(email:token)`) を自動生成し、Authorization ヘッダーとして送信)
- **エンドポイント**: `https://mcp.atlassian.com/v1/mcp`

---

## 2. 設定管理の仕組み (SSOT)

本プロジェクトでは、MCP 設定をリポジトリルートの **`apm.yml`** を
唯一の正解 (Single Source of Truth) として管理しています。

> [!WARNING]
> **各エージェントの生成済み設定ファイルを直接編集しないでください。**
> これらのファイルは `make sync-mcp` 実行時に `apm.yml` から自動生成されるため、
> 手動の変更は上書きされます。
> 設定を変更する場合は必ず `apm.yml` を修正し、`make sync-mcp` を実行してください。

- **`apm.yml`**:
  - 全 AI エージェント (Gemini, Claude, Cursor, VSCode, Antigravity,
    OpenCode, Codex 等) のマスター設定。
  - 各サーバーの定義 (stdio コマンド、環境変数、リモート URL 等) と、
    各エージェントがどのサーバーを利用するかを定義します。
- **自動生成されるファイル**:
  - `make sync-mcp` を実行すると、**APM (Agent Package Manager)** の
    標準機能によって以下のファイルが自動生成・更新されます。
    - **各エージェントの設定ファイル**:
      `gemini/settings.json`, `.mcp.json`, `opencode/opencode.jsonc`,
      `ide/cursor/mcp.json`, `codex/config.toml` 等。
- **プレースホルダー置換**:
  `__HOME__`, `__REPO_ROOT__` は生成時に動的に置換されます。
  また、`${VAR}` 形式の環境変数も APM によって展開されます。

---

## 3. 各ツールの接続仕様リファレンス

本プロジェクトでは **APM 直接管理** パターンを採用しており、
各ツールは `apm.yml` で定義された stdio コマンドまたはリモート SSE URL を直接使用します。
設定は `make sync-mcp` によって各エージェントの設定ファイルに自動反映されます。

### 接続設定キー・対応一覧

| ツール名 | 対応 | 正しいキー名 | 設定ファイル (例) | 形式 |
| :--- | :---: | :--- | :--- | :--- |
| Antigravity | ◎ | `serverUrl` | `~/.gemini/antigravity/...` | JSON |
| **Gemini CLI** | ◎ | `command` / `url` | `~/.gemini/settings.json` | JSON |
| **Claude Code** | ◎ | **`command` / `url`** | `.claude.json` | JSON |
| **Cursor** | 〇 | **`command` / `url`** | `.cursor/mcp.json` | JSON |
| **VSCode** | 〇 | **`url`** | `ide/vscode/settings.json` | JSON |
| **OpenCode** | 〇 | `command` / `url` | `opencode/opencode.jsonc` | JSONC |
| **Codex CLI** | 〇 | **`command`** | `~/.codex/config.toml` | TOML |

### 特筆すべき設定仕様

#### Codex CLI (TOML)

Codex CLI は stdio 専用クライアントです。
APM は各サーバーの `command` / `args` をそのまま生成します。

```toml
[mcp_servers.sqlite]
command = "uvx"
args = ["mcp-server-sqlite", "--db-path", "${HOME}/.mcp/sqlite/sqlite.db"]
```

#### ChronosGraph & Nexus

APM によって直接管理されます。
ホスト上の `~/.context-store` および `~/.nexus` にデータを永続化します。

---

## 4. メンテナンスコマンド

- **`make sync-mcp`**: `apm install` を実行し、`apm.yml` の定義に基づいて
  各エージェントの MCP 設定ファイルを同期。

---

## 5. 前提条件

直接実行型の MCP サーバーを使用するため、以下がインストールされている必要があります。

- **uv / uvx**: Python MCP サーバー (`sqlite`, AWS 各種) を実行するために必要。
- **npx**: Node.js MCP サーバー (`filesystem`, `sequentialthinking`)
  を実行するために必要。
- **github-mcp-server**: GitHub 公式バイナリ。
  未インストールの場合は以下を実行してください。

  ```bash
  go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest
  ```

- **AWS CLI 認証情報**: AWS 各サーバーを使用する場合、
  `~/.aws/credentials` または環境変数で認証情報が必要です。

### トラブルシューティング

| エラー | 原因 | 対処 |
| :--- | :--- | :--- |
| `command not found: uvx` | uv 未インストール | `make install-requirements` を実行 |
| `command not found: github-mcp-server` | バイナリ未インストール | `go install` でインストール |
| `Error: AWS credentials not found` | AWS 認証情報未設定 | `aws configure` か環境変数で設定 |
| `SQLite database is locked` | 同じ DB を複数プロセスが開いている | DB ファイルの排他アクセスを確認 |

---

## 6. MCP サーバー公式リンク集

### MCP 本体 & 公式実装

| MCP | リンク |
| :--- | :--- |
| **MCP 仕様** | https://modelcontextprotocol.io |
| **公式リポジトリ** | https://github.com/modelcontextprotocol/modelcontextprotocol |
| **公式サーバー実装** | https://github.com/modelcontextprotocol/servers |
| **公開 Registry** | https://registry.modelcontextprotocol.io/ |

### コード分析・検索系

| サーバー | GitHub | ドキュメント |
| :--- | :--- | :--- |
| **Greptile** | (非公開) | https://www.greptile.com/docs/mcp/setup |
| **CodeGraph** | https://github.com/colbymchenry/codegraph | https://colbymchenry.github.io/codegraph/ |
| **Nexus** | https://github.com/yohi/nexus | https://github.com/yohi/nexus/tree/v1.26.3 |

### クラウド・API 統合系

| サーバー | GitHub | ドキュメント |
| :--- | :--- | :--- |
| **GitHub Official** | https://github.com/github/github-mcp-server | https://github.com/github/github-mcp-server/tree/main/docs |
| **Atlassian Rovo** | https://github.com/atlassian/atlassian-mcp-server | https://support.atlassian.com/atlassian-rovo-mcp-server/ |
| **Sentry** | https://github.com/getsentry/sentry-mcp | https://docs.sentry.io/product/sentry-mcp/ |

### AWS 統合系

| サーバー | GitHub | ドキュメント | PyPI |
| :--- | :--- | :--- | :--- |
| **AWS IaC** | https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server | https://awslabs.github.io/mcp/servers/aws-iac-mcp-server | https://pypi.org/project/awslabs.aws-iac-mcp-server/ |
| **AWS Documentation** | https://github.com/awslabs/mcp/tree/main/src/aws-documentation-mcp-server | https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server | https://pypi.org/project/awslabs.aws-documentation-mcp-server/ |

### コード品質・セキュリティ系

| サーバー | GitHub | ドキュメント |
| :--- | :--- | :--- |
| **SonarQube** | https://github.com/SonarSource/sonarqube-mcp-server | https://docs.sonarsource.com/sonarqube-mcp-server |
| **Semgrep** | https://github.com/semgrep/semgrep | https://github.com/semgrep/semgrep/tree/develop/cli/src/semgrep/mcp |
| **CodeRabbit** | https://github.com/coderabbitai/mcp-server | https://docs.coderabbit.ai |

### スキル・メモリ・思考系

| サーバー | GitHub | ドキュメント |
| :--- | :--- | :--- |
| **SkillPort** | https://github.com/gotalab/skillport | https://github.com/gotalab/skillport#readme |
| **Chronos Graph** | https://github.com/yohi/chronos-graph | https://github.com/yohi/chronos-graph/tree/v3.0.0 |
| **Sequential Thinking** | https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking | npm: @modelcontextprotocol/server-sequential-thinking |
| **Filesystem** | https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem | npm: @modelcontextprotocol/server-filesystem |
