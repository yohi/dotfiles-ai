# MCP (Model Context Protocol) 設定・運用ガイド

このディレクトリには、本リポジトリの各種 AI エージェントで使用される
MCP サーバーの設定、管理スクリプト、および接続仕様のリファレンスが含まれています。

## 1. 設定済み MCP サーバー

### APM 直接管理 MCP サーバー（ローカル stdio）

有効にする MCP サーバーは `apm.yml` の `dependencies.mcp` に定義し、
`make sync-mcp` によって各エージェントへ反映します。APM はサーバー単位の
`enabled` フラグを扱わず、宣言されたサーバーをすべて設定対象にします。
無効の候補は `mcp/optional-servers.yaml` に保管し、APM には読み込ませません。

主な有効なローカルサーバーは以下の通りです。

- **Filesystem**: プロジェクトルート以下のファイルアクセス。
- **SQLite**: ローカル DB 操作 (`${HOME}/.mcp/sqlite/sqlite.db`)。
- **Skillport**: エージェントスキルの検索・ロード。
- **SonarQube / Semgrep**: ローカル CLI と連携した品質・セキュリティ分析。
- **CodeGraph**: ローカルコード解析。

無効の任意サーバー（CodeRabbit、Greptile、Sequential Thinking、GitHub Official、
AWS IaC / Documentation / Managed、Sentry Remote）の定義は
[`optional-servers.yaml`](optional-servers.yaml) にあります。有効化するときは、
必要なエントリを `apm.yml` の `dependencies.mcp` に移してください。

### Chronos Graph & Nexus (Direct APM)

APM によって直接管理されるローカル知識ベース・長期記憶システムです。

- **ステータス**: 有効 (`apm.yml` で定義され、stdio 経由で各エージェントから利用可能)
- **機能**:
  - **ChronosGraph**: ローカル SQLite (`~/.context-store/memories.db`) を
    バックエンドとした、コンテキストの長期記憶とナレッジグラフ管理。
  - **Nexus**: プロジェクトコードの高速なセマンティック検索・インデックス管理。
- **実装**: `apm.yml` で一括管理されます。

### Cloudflare MCP Portal (Direct / Streamable HTTP)

Cloudflare One で管理されるリモート MCP ポータルです。

- **ステータス**: 有効 (`apm.yml` で定義、各エージェントから利用可能)
- **エンドポイント**: `https://mcp.y-ohi.com/mcp?codemode=search_and_execute`
- **トランスポート**: `streamable-http`
- **Code Mode**: `codemode=search_and_execute` をPortal URLに指定し、上流ツールをCode Mode経由で利用します。

Portal側には、次のリモート上流MCPを登録して集約します。

| 上流MCP | URL | 用途 |
| :--- | :--- | :--- |
| Exa | `https://mcp.exa.ai/mcp?tools=web_search_exa` | Web検索 |
| Context7 | `https://mcp.context7.com/mcp` | ライブラリドキュメント検索 |
| grep.app | `https://mcp.grep.app` | GitHubコード検索 |
| Greptile | `https://api.greptile.com/mcp` | コードレビュー・解析 |
| GitHub Official | `https://api.githubcopilot.com/mcp/` | GitHub連携 |
| AWS Managed | `https://aws-mcp.us-east-1.api.aws/mcp?oauth=initialize` | AWS連携 |
| Sentry Remote | `https://mcp.sentry.dev/mcp` | Sentry連携 |

上流の登録、認証、`Ready` 状態の確認はCloudflare Dashboardで行います。ExaはPortalのCustom Headersに `x-api-key` を設定します。APIキーやOAuthシークレットはこのリポジトリへ記載しません。
Portalの仕様は [MCP server portals](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/)、保護設定は [Secure MCP servers](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/secure-mcp-servers/)、内部アプリ連携は [Linked Apps](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/linked-apps/) を参照します。
`optimize_context=search_and_execute` は別機能のContext optimizationであり、Code Modeの指定には使用しません。
GitHub Official、Greptile、AWS Managed、Sentry RemoteのAPM直接接続は無効化し、Portal経由に統一します。

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
  - APM 経由で有効にする MCP サーバーの唯一の定義元です。
  - `dependencies.mcp` に記載した全サーバーが APM の設定対象になります。
- **対象ランタイム (`targets:`)**:
  - `opencode`, `codex`, `antigravity` を同じ APM インストールで同期します。
  - これらを `--target` で別々にインストールすると、APMのstale cleanupが
    別ターゲットの設定を削除するため、必ず一括で同期してください。
- **`mcp/optional-servers.yaml`**:
  - 有効化していないサーバーの参照用カタログです。APM はこのファイルを読みません。
  - サーバーを有効化するときは、エントリを `apm.yml` に移してください。
- **自動生成されるファイル**:
  - `make sync-mcp` は `apm.yml` の `targets:` にあるOpenCode、Codex、
    Antigravityを一括で更新します。
  - APMプロジェクト出力はOpenCodeの `opencode.json`、Codexの
    `.codex/config.toml`、Antigravity CLIの `.agents/mcp_config.json` です。
  - `opencode/opencode.jsonc` は同じ `apm.yml` から生成されるOpenCode用の
    全体設定です。環境変数プレースホルダーは、リンク前にOpenCodeの記法へ
    正規化されます。
- **Claude Code のユーザースコープ**:
  - `setup-claude` は `~/.apm/apm.yml` がなければリポジトリの `apm.yml` へ
    リンクし、`apm install --global --only mcp --target claude` を実行します。
  - APMは `~/.claude.json` または `$CLAUDE_CONFIG_DIR/.claude.json` の
    `mcpServers` を更新し、他のClaudeユーザー設定を保持します。
  - APMはファイルをatomic replaceするため、有効な `.claude.json` が
    シンボリックリンクの場合は同期を停止します。
  - 別のユーザースコープAPM manifestが存在する場合は、上書きせず停止します。
- **グローバル設定への接続**:
  - OpenCodeはAPMプロジェクト出力 `opencode.json` を
    `~/.config/opencode/opencode.json` からシンボリックリンクで参照します。
  - Codexは `.codex/config.toml` を `~/.codex/config.toml` へリンクします。
    初回生成時は既存のグローバルCodex設定を土台として使い、通常ファイルは
    リンク前にバックアップします。
  - Antigravity CLIは `.agents/mcp_config.json` を
    `~/.gemini/antigravity-cli/mcp_config.json` へリンクします。
- **プレースホルダー置換**:
  `__HOME__`, `__REPO_ROOT__` は生成時に動的に置換されます。
  また、`${VAR}` 形式の環境変数も APM によって展開されます。

---

## 3. 各ツールの接続仕様リファレンス

本プロジェクトでは **APM + Cloudflare MCP Portal** パターンを採用しています。
ローカルMCPは `apm.yml` で定義された stdio コマンドを直接使用し、リモートMCPは
Cloudflare MCP PortalのStreamable HTTP URLへ集約します。
設定は `make sync-mcp` によって各エージェントの設定ファイルに自動反映されます。

### 接続設定キー・対応一覧

| ツール名 | 対応 | 正しいキー名 | 設定ファイル (例) | 形式 |
| :--- | :---: | :--- | :--- | :--- |
| Antigravity CLI | ◎ | `command` / `url` | `.agents/mcp_config.json` → `~/.gemini/antigravity-cli/mcp_config.json` | JSON |
| **Gemini CLI** | ◎ | `command` / `url` | `~/.gemini/settings.json` | JSON |
| **Claude Code** | ◎ | **`command` / `url`** | `~/.claude.json` または `$CLAUDE_CONFIG_DIR/.claude.json` | JSON |
| **Cursor** | 〇 | **`command` / `url`** | `.cursor/mcp.json` | JSON |
| **VSCode** | 〇 | **`url`** | `ide/vscode/settings.json` | JSON |
| **OpenCode** | 〇 | `command` / `url` | `opencode.json` → `~/.config/opencode/opencode.json` | JSON |
| **Codex CLI** | 〇 | **`command` / `url`** | `.codex/config.toml` → `~/.codex/config.toml` | TOML |

### 特筆すべき設定仕様

#### Codex CLI (TOML)

Codex CLI は stdio と Streamable HTTP に対応しています。
APM は有効なサーバーの `command` / `args` または `url` を生成します。

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
  `targets:` にあるOpenCode、Codex、Antigravityのプロジェクト設定を一括同期。
- **`make sync-claude-apm-mcp`**: `apm.yml` をユーザースコープのAPM manifestとして
  参照し、Claude CodeのグローバルMCPを同期。
- **`make setup-claude`**: Claude用の設定適用時に、上記のユーザースコープ同期も実行。

### Portal移行後の確認手順

1. Cloudflare Dashboardの **Zero Trust > Access controls > AI controls >
   MCP servers** で、上流サーバーが `Ready` であることを確認する。
2. `cf-mcp-portal` へ必要な上流サーバーとツールだけを追加する。
3. 直接接続を使わない場合、該当サーバーが `apm.yml` の
   `dependencies.mcp` に含まれず、参照用カタログにのみ存在することを確認する。
4. クライアント側の生成済み設定ファイル（`.claude.json`、`.cursor/mcp.json`、
   `ide/vscode/settings.json` 等）から、これらの直接リモートMCPエントリを
   削除または無効化する。
5. `make sync-mcp` を実行し、直接リモートMCPの無効化とローカルstdio MCPの同期を
   再反映する。
6. `portal_list_servers` でPortalから上流一覧を確認し、直接接続とPortal接続が
   重複していないことを確認する。
7. Portal経由で代表ツールを呼び出し、応答を確認する。

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
| **Nexus** | https://github.com/yohi/nexus | https://github.com/yohi/nexus/tree/v2.0.0 |

### クラウド・API 統合系

| サーバー | GitHub | ドキュメント |
| :--- | :--- | :--- |
| **Cloudflare MCP Portal** | (Cloudflare One) | https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/ |
| **GitHub Official** | https://github.com/github/github-mcp-server | https://github.com/github/github-mcp-server/tree/main/docs |
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
