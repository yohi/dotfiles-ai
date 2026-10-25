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

### Cloudflare MCP Portal (3 scopes / Streamable HTTP)

Cloudflare MCP Portal connections are declared only in `apm.yml` (SSOT).
Do not edit generated `opencode.json(c)` files. The client configuration does
**not** create or reconfigure the Portals in Cloudflare.

| OpenCode server ID | Endpoint | Intended scope |
| :--- | :--- | :--- |
| `cf-mcp-portal` | `https://mcp.y-ohi.com/mcp` | Default: shared/public documentation |
| `cf-mcp-portal-personal` | `https://personal.mcp.y-ohi.com/mcp` | Personal account data |
| `cf-mcp-portal-work` | `https://work.mcp.y-ohi.com/mcp` | Work account data |

**Migration safety hold:** The existing Default Portal still contains
personal/account-bound upstream MCP servers. It is **disabled by default** by
`_scripts/opencode-wrapper.sh` for **both** OpenCode profiles. Before enabling
Default, curate it in the Cloudflare dashboard to contain only authorized,
non-confidential, shared tools; verify the Access policy, upstream identities,
and tool allowlist. Once confirmed, launch the wrapper with
`CF_MCP_DEFAULT_ENABLED=1`. Do not use that switch prematurely.

`opencode personal` (wrapper) enables Personal and disables Work.
`opencode work` enables Work and disables Personal. Common stays disabled
until explicitly enabled. The wrapper merges its `mcp.<id>.enabled` overrides
into any existing `OPENCODE_CONFIG_CONTENT`, preserving unrelated settings;
invalid JSON stops startup. **Launching the raw `opencode` binary bypasses
this profile selection.** The wrapper is a usability feature, not an
authorization boundary. Restrict each Portal with Cloudflare Access and
least-privilege upstream credentials.

APM exports all three Portal definitions to other configured clients as well
(including Codex and Claude Code). Their connections are NOT profile-gated by
this OpenCode wrapper. Do not apply the three-scope mapping to other clients
until their own enablement/routing and Cloudflare Access restrictions have been
verified; never rely on a descriptive Portal name to separate credentials.

Portal Code Mode is currently `enforced` in Cloudflare. The above URLs omit
`?codemode=search_and_execute` in preparation for manually switching each
Portal to `opt_in`; while `enforced` is configured, the Portal remains in
Code Mode regardless of the URL. Once changed, plain `/mcp` exposes direct
tools for OpenCode V1 discovery. If Code Mode is intentionally required, append
`?codemode=search_and_execute` for that client only. Do not stack Code Mode
on an upstream that itself requires a nested Code Mode search.

The AWS Managed MCP Server without authentication is useful for public AWS
documentation. `No Auth` does **not** mean the server is universally
read-only; curate exposed tools on the Default Portal. Keep AWS account API
operations on the separately authenticated STS/SigV4 path.

---

### AWS管理型MCP（SigV4 / STS）

`apm.yml` の `aws-mcp` は、AWSが運用する管理型MCPへ
`mcp-proxy-for-aws-cli==1.7.0` から接続します。
旧 `awslabs.aws-api-mcp-server` は使用しません。東京のエンドポイント
`https://aws-mcp.ap-northeast-1.api.aws/mcp` に接続し、
API実行リージョンは `--metadata AWS_REGION=ap-northeast-1` で指定します。

MCPの資格情報は **`aws login --remote` → STS AssumeRole →
ReadOnlyAccess Session Policy → SigV4** の順に取得・使用します。
長期IAMアクセスキーは不要です。ARNや認証情報を公開リポジトリに固定しないでください。

1. AWS CLI v2で `aws login --remote --profile signin` を実行します。
   `~/.aws/config` に `[profile signin]` と `login_session` が必要です。
2. **ローカルの** `~/.aws/config` に以下を追記します。
   スクリプトのパスとロールARNは実際の値に置き換えてください。
   `credential_process` は `${VAR}` を展開しません。

   ```ini
   [profile aws-mcp-readonly]
   region = ap-northeast-1
   credential_process = python3 /absolute/path/to/dotfiles-ai/_scripts/aws-mcp-sts-credentials.py --source-profile signin --role-arn arn:aws:iam::111122223333:role/EXISTING_READONLY_ROLE
   ```

3. `aws sts get-caller-identity --profile aws-mcp-readonly` を実行し、
   ロールを引き受けられることを確認します。この操作は権限制限の証明ではありません。
4. `make sync-mcp` でAPM設定を同期し、`opencode mcp list` で
   `aws-mcp` が接続できるか確認します。

`_scripts/aws-mcp-sts-credentials.py` はSTS AssumeRole時に
`arn:aws:iam::aws:policy/ReadOnlyAccess` をSession Policyとして指定します。
ロールの信頼ポリシーと呼び出し元のAssumeRole権限が必要です。
同ヘルパーはCLI v2の `login_session` に依存します。
`mcp-proxy-for-aws-cli` は旧AWS API MCPと異なり、
`awscli==1.46.0` を内部依存として追加しません。
ただしホストのPATHでCLI v2を選択できることを実環境で確認してください。

**読み取り制限について:** 汎用のAWS API呼び出しに必要な
`aws___run_script` は書き込み可能ツールとして扱われ得るため、
プロキシの `--read-only` は付けていません。これは読み取り専用の
動作が証明されたことを意味しません。AWS側の権限制限は
**必須のSTS Session Policy** に依存します。
人間承認なしの書き込み実行は認可しません。
AWS CLIプロファイルの外部変更や実効権限については別途検証が必要です。

`AWS_MCP_PROXY_PROFILES=aws-mcp-readonly` で使用可能なプロファイルを
明示的に一つへ制限しています。AWS管理型MCPはCloudflare MCP Portalの
上流にも登録済みであり、この直接接続とは**別経路**です。重複ツールが
生じ得るため、利用する経路を統一してください。

**重要:** このリポジトリの変更は設定とオフライン検証のみです。
AWS接続、ロール引受け成功、実効的なNo-Writeはいずれも未検証です。

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
  - `opencode`, `codex` を同じ APM インストールで同期します。
  - Antigravity は APM CLI の仕様上 explicit-only ターゲットのため、`apm compile --target antigravity` で明示的に生成されます。
- **`mcp/optional-servers.yaml`**:
  - 有効化していないサーバーの参照用カタログです。APM はこのファイルを読みません。
  - サーバーを有効化するときは、エントリを `apm.yml` に移してください。
- **自動生成されるファイル**:
  - `make sync-mcp` は `apm.yml` の `targets:` にあるOpenCode、Codexを一括で更新します。
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
  `targets:` にあるOpenCode、Codexのプロジェクト設定を一括同期（Antigravity は個別生成）。
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
