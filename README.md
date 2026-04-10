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
├── agent-skills/           # [SSOT] Skill definitions (skillport)
├── agent-commands/         # [SSOT] Slash commands
├── global-rules/           # [SSOT] Global AI rules
├── claude/                 # Claude Code specific settings
├── gemini/                 # Gemini CLI / SuperGemini settings
├── opencode/               # OpenCode specific settings
├── codex/                  # Codex specific settings
├── ide/                    # IDE AI settings (MCP, SuperCursor)
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
- **外部スキルの管理 (Lock-file)**: `superpowers` などの高品質な外部スキルは、`agent-skills/EXTERNAL_SKILLS.md` でバージョン（コミットハッシュ）が固定（Lock）されています。
  - 実体ファイルは `.gitignore` によりリポジトリには含まれません。
  - `make setup-superpowers` を実行することで、マニフェストに基づいた正確なバージョンのスキルが各環境に展開されます。
- **構成**: `.skillportrc` で設定され、`~/.skillport/skills` からリポジトリの `agent-skills/` へシンボリックリンクが張られます。
- **コマンド**:
  - `make skillport`: SkillPort と `skillport-mcp` をインストールし、本環境の**初期セットアップ**を行います。
  - `make check-skillport`: インストール状態とシンボリックリンクの整合性を確認します。
  - `make sync-agents`: `agent-skills/` をソースとして、`AGENTS.md` と `global-rules/AGENTS.global.md` の SkillPort ブロックを直接更新します。
  - `skillport <command>`: スキルの追加・削除・更新などの**管理操作**は、`skillport` CLI を直接実行してください（`make` 経由ではありません）。
    - 例: `skillport add anthropics/skills skills/ --namespace anthropics`
  - `skillport check`: スキル定義ファイル（.md）の構文や整合性をチェックします。

## Docker MCP Gateway (Unified SSE)

[Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) は、複数の MCP サーバーを統合し、共通の **SSE (Server-Sent Events)** エンドポイントを提供します。

- **役割**: Claude Code, Gemini CLI, Antigravity, Cursor, OpenCode, VSCode から、単一の URL (`http://127.0.0.1:10888/sse`) 経由で複数の MCP サーバーにアクセス可能にします。
- **管理 (Systemd)**: バックグラウンドサービスとして常駐します。
  - `make start-mcp`: ゲートウェイを起動。
  - `make stop-mcp`: ゲートウェイを停止。
  - `make setup-docker-mcp`: Docker MCP Gateway 自体のセットアップを行います。
  - `make sync-mcp`: `mcp/servers.yaml` と `mcp/config.yaml` から各エージェント/IDE 向け設定と Gateway 実行設定を再生成し、Gateway を再読み込みします。
- **Source of Truth**: 
  - **`mcp/catalogs/custom.yaml.template`**: Docker MCP Gateway の custom catalog 定義です。
  - **`mcp/config.yaml`**: Docker MCP Gateway で有効化するサーバー一覧の SSOT です。同期時に systemd service の `--servers` 引数へ反映されます。
  - **`mcp/servers.yaml`**: 各エージェント/IDE に配る MCP クライアント設定の SSOT です。
- **初期セットアップ**: `make setup-docker-mcp` を実行すると、catalog と service 設定を含む Gateway の初期配置が完了します。
- **自動同期**: `mcp/servers.yaml`、`mcp/config.yaml`、または catalog/template を編集したら `make sync-mcp` を実行してください。

## SkillPort & MCP の統合

`skillport-mcp` を MCP サーバーとして Docker MCP Gateway に登録することで、エージェントは `agent-skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、各スキルを MCP ツールとして公開します。
2. **利用方法**: `mcp/config.yaml` で `skillport` を有効にしている限り、全エージェントは Docker MCP Gateway (`:10888/sse`) 経由で自動的に全スキルを利用できます。

## エージェント設定の自動同期

`_scripts/sync-mcp-configs.sh` により、各エージェントの設定ファイルは以下の状態に自動的に保たれます。

注記:
- `*.template` は初回セットアップ時の scaffold として使われます。
- 生成先ファイルが既に存在する場合、`make sync-mcp` はテンプレートから全面再生成せず、MCP 関連の設定部分だけを更新します。

| エージェント | 接続方式 | 備考 |
|:-----------|:--------|:-----|
| **Claude Code** | Native SSE (`type` + `url`) | 初回のみ template から生成し、以後は `mcpServers` を同期 |
| **Gemini CLI** | Native SSE (`url`) | 初回のみ template から生成し、以後は `mcpServers` を同期 |
| **Antigravity** | Native SSE (`serverUrl`) | `antigravity/mcp_config.json` を生成 |
| **Cursor** | Native SSE (`url`) | `ide/cursor/mcp.json` を生成 |
| **OpenCode** | Remote MCP (`type: remote`) | 初回のみ template から生成し、以後は `mcp` ブロックを同期 |
| **VSCode** | Native SSE (`url`) | 初回のみ template から生成し、以後は `mcpServers` を同期 |

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
  - **MCP サーバーの追加**は `mcp/catalogs/custom.yaml.template` を編集.
  - **Gateway で有効化するサーバー変更**は `mcp/config.yaml` を編集。
  - **エージェント/IDE の接続設定変更**は `mcp/servers.yaml` を編集。
- **同期コマンド**:
  - `make setup-docker-mcp`: Docker MCP Gateway のセットアップ。
  - `make sync-mcp`: MCP クライアント設定の再生成と同期。
  - `make sync-agents`: `agent-skills/` から各 AGENTS instruction file のスキル一覧を同期。

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) (SSE Mode) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| 構成管理 | Bash, jq, systemd |
