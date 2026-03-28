# dotfiles-ai

AIエージェント（Claude Code, Gemini CLI, OpenCode, Codex）の設定・スキル・ルールを一元管理するコンポーネントリポジトリです。
`dotfiles-core` と連携して動作します。
**SSOT（Single Source of Truth）** 方式で、共通のスキル定義とコーディングルールを管理し、各エージェントへ自動配備します。

### 💡 設計思想: `dotfiles-ide` との境界線
当リポジトリ（`dotfiles-ai`）は、**「AIの振る舞いとルール（頭脳）」** を一元管理する役割を担います。
対して、`dotfiles-ide` は **「エディタとしての基本的な器と振る舞い（UI/UX）」** を管理します。
*   **`dotfiles-ide`**: VS CodeやCursorのUI設定（`settings.json`）、キーバインド（`keybindings.json`）、 拡張機能リストなどを管理。
*   **`dotfiles-ai`** (本リポジトリ): AIエージェントへの指示（プロンプト）、SkillPortによるスキル管理、MCPハブ設定、エディタ向けAI設定（`mcp.json` や `supercursor` など）を管理。

この「関心の分離」により、すべてのAIツールで統一されたペルソナを維持しつつ、エディタのUI設定と切り離して スケーラブルに運用します。

## 管理と依存関係

本リポジトリは [dotfiles-core](https://github.com/yohi/dotfiles-core) によって管理されるコンポーネントの一つです。

### ⚠️ 単体使用時の注意点
本リポジトリは `dotfiles-core` の共通 Makefile ルール（`common-mk`）に依存しています。単体で使用（クローン）する場合は、以下の手順が必要です：

1. `common-mk` ディレクトリを本リポジトリの親ディレクトリに配置するか、パスを適切に設定してください。
2. `make help` を実行して、正しく設定されていることを確認してください。

推奨される使用方法は、`dotfiles-core` から `make setup` を実行することです。

### 依存関係

- Python スクリプト（`scripts/render-mcp-configs.py`）の実行には `PyYAML` が必要です。
- 初回セットアップ時に以下を実行してください。

```bash
python3 -m pip install -r requirements.txt
```

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

## スキル管理 (SkillPort)

[SkillPort](https://github.com/gotalab/skillport) は、複数の AI エージェント間で再利用可能な「スキル」を 一元管理するためのツールです。

- **スキルの実体**: `agent-skills/` ディレクトリ配下に、各スキルの `SKILL.md`（インストラクション）が格納されています。
- **構成**: `.skillportrc` で設定され、`~/.skillport/skills` からリポジトリの `agent-skills/` へシンボリ ックリンクが張られます。
- **コマンド**:
  - `make skillport`: SkillPort と `skillport-mcp` をインストールし、ディレクトリをセットアップします。
  - `make check-skillport`: インストール状態とシンボリックリンクの整合性を確認します。
  - `skillport check`: スキル定義ファイル（.md）の構文や整合性をチェックします。

## Docker MCP Gateway (Unified SSE)

[Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) は、複数の MCP サーバーを統合し、共通の **SSE (Server-Sent Events)** エンドポイントを提供します。

- **役割**: Claude Code, Gemini CLI, Antigravity, Cursor, OpenCode, VSCode から、単一の URL (`http://127.0.0.1:10888/sse`) 経由で複数の MCP サーバーにアクセス可能にします。
- **管理 (Systemd)**: バックグラウンドサービスとして常駐します。
  - `make start-mcp`: ゲートウェイを起動。
  - `make stop-mcp`: ゲートウェイを停止。
  - `make setup-docker-mcp`: Docker MCP Gateway 自体のセットアップを行います。
  - `make sync-mcp`: `mcp/servers.yaml` から各エージェント/IDE 向け設定を再生成し、Gateway を再読み込みします。
- **Source of Truth**: 
  - **`mcp/catalogs/custom.yaml.template`**: Docker MCP Gateway の custom catalog 定義です。
  - **`mcp/config.yaml`**: Gateway 上で有効化するサーバーを管理します。
  - **`mcp/servers.yaml`**: 各エージェント/IDE に配る MCP クライアント設定の SSOT です。
- **初期セットアップ**: `make setup-docker-mcp` を実行すると、`custom.yaml.template` から `custom.yaml`  が生成され、Gateway の初期配置が完了します。
- **自動同期**: `mcp/servers.yaml` または catalog/template を編集したら `make sync-mcp` を実行してくださ い。

## SkillPort & MCP の統合

`skillport-mcp` を MCP サーバーとして Docker MCP Gateway に登録することで、エージェントは `agent-skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、各スキルを MCP ツールとして公開 します。
2. **利用方法**: 全てのエージェントは Docker MCP Gateway (`:10888/sse`) を参照するように統一されているた め、自動的に全スキルがロードされます。

## エージェント設定の自動同期

`scripts/sync-mcp-configs.sh` により、各エージェントの設定ファイルは以下の状態に自動的に保たれます。

| エージェント | 接続方式 | 備考 |
|:-----------|:--------|:-----|
| **Claude Code** | Native SSE (`type` + `url`) | `claude/claude-settings.json` を再生成 |
| **Gemini CLI** | Native SSE (`url`) | `gemini/settings.json` を再生成 |
| **Antigravity** | Native SSE (`serverUrl`) | `antigravity/mcp_config.json` を生成 |
| **Cursor** | Native SSE (`url`) | `ide/cursor/mcp.json` を生成 |
| **OpenCode** | Remote MCP (`type: remote`) | `opencode/opencode.jsonc` の MCP ブロックを再生成 |
| **VSCode** | Native SSE (`url`) | `ide/vscode/settings.json` の `mcpServers` を再生成 |

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
  - **MCP サーバーの追加**は `mcp/catalogs/custom.yaml.template` を編集。
  - **エージェント/IDE の接続設定変更**は `mcp/servers.yaml` を編集。
- **同期コマンド**:
  - `make setup-docker-mcp`: Docker MCP Gateway のセットアップ。
  - `make sync-mcp`: MCP クライアント設定の再生成と同期。
  - `make sync-agents`: ルールとスキルの同期。

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) (SSE Mode) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| 構成管理 | Bash, jq, systemd |
