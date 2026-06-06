# dotfiles-ai

AIエージェント（Claude Code, Gemini CLI, OpenCode, Codex）の設定・スキル・ルールを一元管理するコンポーネントリポジトリです。
`dotfiles-core` と連携して動作します。
**SSOT（Single Source of Truth）** 方式で、共通のスキル定義とコーディングルールを管理し、各エージェントへ自動配備します。

## 管理と共存関係

> [!IMPORTANT]
> 本リポジトリは [dotfiles-core](https://github.com/yohi/dotfiles-core) によって管理されるコンポーネントの一つです。
> [!WARNING]
> **使用時の注意点**
> 本リポジトリは `dotfiles-core` の共通 Makefile ルール（`common-mk`）に依存しており、実行時には `common-mk` へのシンボリックリンクが必要です。そのため、**本リポジトリ単体での使用（クローンしての利用）はサポートされていません。**
>
> 推奨される使用方法は、`dotfiles-core` リポジトリから `make setup` を実行し、適切なディレクトリ構造とシンボリックリンクが構成された状態で利用することです。

## ディレクトリ構成

```text
.
├── Makefile
├── README.md
├── AGENTS.md
├── apm.yml                 # [SSOT] APM 設定・外部スキル依存関係
├── .env.example            # 環境変数テンプレート
├── .agents/skills/         # [APM 標準] 全エージェント向けスキル配置
├── agent-skills/           # [SSOT] Skill definitions (skillport)
├── agent-commands/         # [SSOT] Slash commands
├── global-rules/           # [SSOT] Global AI rules
├── claude/                 # Claude Code specific settings
├── gemini/                 # Gemini CLI specific settings
├── opencode/               # OpenCode specific settings
├── codex/                  # Codex specific settings
├── ide/                    # IDE AI settings (MCP)
└── mcp/                    # Docker MCP Gateway settings
```

## 主要機能

- **SkillPort**: 全エージェントで再利用可能なスキルの SSOT 管理。
- **Docker MCP Gateway**: SSE による複数エージェント/IDE 向け MCP サーバーの統合。
- **SSOT ルール管理**: 規約やユーザー指示の一元化と自動同期。
- **マルチエージェント対応**: Claude Code, Gemini CLI, OpenCode, Codex, Cursor/VSCode への自動配備。

## ルール管理構造 (SSOT)

本プロジェクトでは、AIエージェントへの指示を以下の2層で管理しています。

1.  **グローバル指示 (`global-rules/AGENTS.global.md`)**:
    *   ユーザーのアイデンティティ、言語設定（日本語優先）、セキュリティ、全AI共通の行動指針。
    *   `~/.gemini/GEMINI.md` や `~/.claude/CLAUDE.md` などのホームディレクトリ設定の**リンク元（実体）**となります。
2.  **プロジェクト指示 (`AGENTS.md`)**:
    *   このリポジトリ（`dotfiles-ai`）固有のルール、利用可能なスキルのリスト、リポジトリ構成の解説。

`global-rules/AGENTS.global.md` と `AGENTS.md` は責務が異なる独立した instruction file です。どちらか一方を他方のソースとして扱わず、共通のスキル一覧が必要な場合は `agent-skills/` からそれぞれへ直接反映します。

## スキル管理 (SkillPort)

[SkillPort](https://github.com/gotalab/skillport) は、複数の AI エージェント間で再利用可能な「スキル」を一元管理するためのツールです。

- **スキルの実体**: `agent-skills/` ディレクトリ配下に、各スキルの `SKILL.md`（インストラクション）が格納されています。
- **外部スキルの管理 (APM)**: `superpowers` などの高品質な外部スキルは、`apm.yml` の `dependencies` で管理され、`apm.lock.yaml` でバージョン（コミットハッシュ）が固定されます。
  - **スキルインストール**: `apm install` で `apm.yml` に記載された全外部スキルをインストールします。
  - この操作は `make setup` 実行時にも自動で行われます。
- **構成**: `.skillportrc` で設定され、`~/.skillport/skills` からリポジトリの `agent-skills/` へシンボリックリンクが張られます。
- **スキル配置**: `.agents/skills/` に集約（全エージェントが参照）
- **コマンド**:
  - `make skillport`: SkillPort と `skillport-mcp` をインストールし、本環境の**初期セットアップ**を行います。
  - `make check-skillport`: インストール状態とシンボリックリンクの整合性を確認します。
  - `make sync-agents` / `make sync-skills-to-agents`: `agent-skills/` をソースとして、`.agents/skills/` にスキルを同期します。
  - `make sync-agents-rules`: `agent-skills/` をソースとして、`AGENTS.md` と `global-rules/AGENTS.global.md` の SkillPort ブロックを直接更新します。
  - `skillport <command>`: スキルの追加・削除・更新などの**管理操作**は、`skillport` CLI を直接実行してください（`make` 経由ではありません）。
    - 例: `skillport add anthropics/skills skills/ --namespace anthropics`
  - `skillport check`: スキル定義ファイル（.md）の構文や整合性をチェックします。

## APM による一元管理

[Agent Package Manager (APM)](https://github.com/microsoft/apm) ([Docs](https://microsoft.github.io/apm/)) は AI エージェント設定の Single Source of Truth (SSOT) です。

- **管理対象**: 外部スキル依存関係（`obra/superpowers`, `anthropics/skills`）+ カスタムMCP（Docker Catalog にないもの）
- **Docker Catalog 標準 MCP**: GitHub, SQLite, sequentialthinking は Docker Desktop 側で管理
- **スキル配置**: `.agents/skills/` に集約（全エージェントが参照）
- **自動生成ファイルと Git**:
  `opencode.json` などのルート直下の設定ファイルは、`apm install` 時に APM が「プロジェクトの目印」として自動生成します。これらは `.gitignore` で除外されており、Git 管理（コミット）の対象外です。

### 環境変数の3層モデル

| Tier | ソース | コンテンツ |
| :--- | :--- | :--- |
| Tier 1 | OS / シェル環境 | API Keys, PATs |
| Tier 2 | `.env` (Git除外) | 環境固有設定 |
| Tier 3 | `apm.yml` | デフォルト値 |

`.env.example` を `.env` にコピーして使用してください。

## Docker MCP Gateway (Unified SSE)

[Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) は、複数の MCP サーバーを統合し、共通の **SSE (Server-Sent Events)** エンドポイントを提供します。

- **役割**: Claude Code, Gemini CLI, Cursor, OpenCode, VSCode, Codex から、単一の URL (`http://127.0.0.1:10888/sse`) 経由で複数の MCP サーバーにアクセス可能にします。
- **管理 (Systemd)**: バックグラウンドサービスとして常駐します。
  - `make start-mcp`: ゲートウェイを起動。
  - `make stop-mcp`: ゲートウェイを停止。
  - `make setup-docker-mcp`: Docker MCP Gateway 自体のセットアップを行います。
  - `make sync-mcp`: `apm.yml` のカスタム MCP 定義から各エージェント/IDE 向け設定と Gateway 実行設定を再生成し、Gateway を再読み込みします。
- **Source of Truth**:
  - **`apm.yml`**: 外部スキル依存関係と Docker Catalog にないカスタム MCP 定義の **SSOT** です。
- **自動生成されるファイル**: `make sync-mcp` を実行すると、以下のファイルが `apm.yml` から自動生成されます。
  - `mcp/config.yaml`: Docker MCP Gateway で有効化するサーバー一覧。
  - `mcp/catalogs/custom.yaml`: Docker MCP Gateway のカスタムカタログ定義。
- **初期セットアップ**: `make setup-docker-mcp` を実行すると、service 設定を含む Gateway の初期配置が完了します。
- **自動同期**: `apm.yml` の MCP 定義を編集したら `make sync-mcp` を実行してください。

### Antigravity CLI での注意点

Antigravity CLI 1.0.6 では、Docker MCP Gateway の SSE endpoint (`:10888/sse`) に対して、認証済み SSE 接続自体は成立しても `initialize` 送信時に `Bad Request` または `Unauthorized` になることがあります。OpenCode など他クライアントで同じ Gateway が接続できる場合、Gateway や token ではなく Antigravity CLI 側の SSE message endpoint 処理との相性問題として扱います。

そのため、Antigravity CLI では当面 `docker-mcp` 経由ではなく、`skillport` / `nexus` / `chronos-graph` を direct stdio MCP として使う構成を推奨します。Antigravity 設定は `make sync-antigravity` で `antigravity/mcp_config.json` を生成し、`~/.gemini/antigravity-cli/mcp_config.json` へリンクします。

## SkillPort & MCP の統合

`skillport-mcp` を MCP サーバーとして Docker MCP Gateway に登録することで、エージェントは `.agents/skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、各スキルを MCP ツールとして公開します。
2. **利用方法**: `mcp/config.yaml` で `skillport` を有効にしている限り、全エージェントは Docker MCP Gateway (`:10888/sse`) 経由で自動的に全スキルを利用できます。
3. **スキル配置先**: `.agents/skills/` (APM 標準クロスプラットフォーム)
4. **実体**: `agent-skills/` (SSOT)

## エージェント設定の自動同期 (APM)

`apm install` により、APM が各エージェントの設定ファイル（`mcp.json` や `settings.json` 等）を自動検出し、Docker MCP Gateway の SSE エンドポイントを注入します。

**Automated Flow**: `make setup` → `apm install` (triggers `post_install` hooks) → `make sync-mcp` (renders backend config & restarts service).

| エージェント | 接続方式 | 管理主体 |
|:-----------|:--------|:--------|
| **Claude Code** | Native SSE | APM (`apm install`) |
| **Gemini CLI** | Native SSE | APM (`apm install`) |
| **Antigravity CLI** | Direct stdio MCP 推奨 | Make (`make sync-antigravity`) |
| **Cursor** | Native SSE | APM (`apm install`) |
| **OpenCode** | Remote MCP | APM (`apm install`) |
| **VSCode** | Native SSE | Make (`make sync-mcp`) |

注記:
- SSE エンドポイントとして `http://127.0.0.1:10888/sse` と `http://localhost:10888/sse` が混在している場合がありますが、これらは実質的に同一であり、環境に合わせて自動的に設定されます。
- Gateway 自体のバックエンド構成（`mcp/config.yaml` の生成）は、`apm install` の `post_install` フックによって `make sync-mcp` が実行され、自動的に行われます。

## デプロイ構造 (シンボリックリンク)

`make setup` を実行すると、リポジトリ内の設定ファイルが各エージェントの構成ディレクトリへ配備されます。

| エージェント / ツール | シンボリックリンク (配置先) | 実体 (リポジトリ内) |
|:-------------------|:----------------------|:-------------------|
| **Global Rules** | `~/.gemini/GEMINI.md` | `global-rules/AGENTS.global.md` |
| **Docker MCP** | `~/.docker/mcp/catalogs/custom.yaml` | `mcp/catalogs/custom.yaml` (Generated) |
| **Gemini CLI** | `~/.gemini/settings.json` | Updated by sync script |
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | `antigravity/mcp_config.json` |
| **Cursor** | `.cursor/mcp.json` | `ide/cursor/mcp.json` |

## SSOT 原則

- **ルールの編集**: 
  - ユーザー共通設定は `global-rules/AGENTS.global.md` を編集。
  - 個別のスキルは `agent-skills/*/SKILL.md` を編集。
  - **カスタム MCP サーバーの追加・変更・有効化**、および**エージェント/IDE の接続設定変更**は、全て **`apm.yml`** を編集してください。
- **同期コマンド**:
  - `make setup-docker-mcp`: Docker MCP Gateway のセットアップ。
  - `make sync-mcp`: MCP 設定の再生成と同期。
  - `make sync-agents`: `agent-skills/` から各 AGENTS instruction file のスキル一覧を同期。

## 主要な make ターゲット

| ターゲット | 説明 |
| :--- | :--- |
| `make setup` | 全体のセットアップ |
| `make apm-install` | APM インストール + 同期 |
| `make setup-apm-env` | .env ファイルの雛形作成 |
| `make setup-docker-mcp` | Docker MCP Gateway のセットアップ |
| `make sync-agents` / `make sync-skills-to-agents` | スキルを .agents/skills/ に集約 |
| `make sync-mcp` | MCP 設定の再生成 |
| `make start-mcp` | MCP Gateway を起動 |
| `make stop-mcp` | MCP Gateway を停止 |
| `make skillport` | SkillPort の初期セットアップ |
| `make check-skillport` | インストール状態の確認 |

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) (SSE Mode) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| 構成管理 | Bash, jq, systemd |
