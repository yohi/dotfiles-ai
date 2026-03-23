# dotfiles-ai

AIエージェント（Claude Code, Gemini CLI, OpenCode, Codex）の設定・スキル・ルールを一元管理するコンポーネントリポジトリです。
`dotfiles-core` と連携して動作します。

## 概要

**SSOT（Single Source of Truth）** 方式で、共通のスキル定義とコーディングルールを管理し、各エージェントへ自動配備します。

| ディレクトリ | 役割 |
|:------------|:-----|
| `agent-skills/` | **[SSOT]** 全エージェント共通のスキル定義群（skillport 管理） |
| `agent-commands/` | **[SSOT]** 全エージェント共通のスラッシュコマンド |
| `global-rules/` | **[SSOT]** コーディング規約・ルール・ユーザーレベル指示（マスター） |
| `AGENTS.md` | **[Project]** dotfiles-ai プロジェクト固有のルールとスキルリスト |
| `claude/` | Claude Code 固有設定 |
| `gemini/` | Gemini CLI / SuperGemini 設定 |
| `opencode/` | OpenCode 固有設定 |
| `codex/` | Codex 固有設定 |
| `ide/` | IDE (Cursor, VSCode) 設定と SuperCursor/SuperCopilot |
| `_mk/` | Makefile サブターゲット群 |

## ルール管理構造 (SSOT)

本プロジェクトでは、AIエージェントへの指示を以下の2層で管理しています。

1.  **グローバル指示 (`global-rules/AGENTS.global.md`)**:
    *   ユーザーのアイデンティティ、言語設定（日本語優先）、セキュリティ、全AI共通の行動指針。
    *   `~/.gemini/GEMINI.md` や `~/.claude/CLAUDE.md` などのホームディレクトリ設定の**リンク元（実体）**となります。
2.  **プロジェクト指示 (`AGENTS.md`)**:
    *   このリポジトリ（`dotfiles-ai`）固有のルール、利用可能なスキルのリスト、リポジトリ構成の解説。

## スキル管理 (SkillPort)

[SkillPort](https://github.com/gotalab/skillport) は、複数の AI エージェント間で再利用可能な「スキル」を一元管理するためのツールです。

- **スキルの実体**: `agent-skills/` ディレクトリ配下に、各スキルの `SKILL.md`（インストラクション）が格納されています。
- **構成**: `.skillportrc` で設定され、`~/.skillport/skills` からリポジトリの `agent-skills/` へシンボリックリンクが張られます。
- **コマンド**:
  - `make skillport`: SkillPort と `skillport-mcp` をインストールし、ディレクトリをセットアップします。
  - `make check-skillport`: インストール状態とシンボリックリンクの整合性を確認します。
  - `skillport check`: スキル定義ファイル（.md）の構文や整合性をチェックします。

## Docker MCP Gateway

[Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) は、Model Context Protocol (MCP) サーバーを統合し、SSE (Server-Sent Events) プロキシとして提供するコンポーネントです。

- **役割**: Claude Code, Gemini CLI, Cursor などのエージェントから、単一のエンドポイント（`http://localhost:10888`）経由で複数の MCP サーバー（SQLite, Filesystem, SkillPort 等）にアクセス可能にします。
- **管理 (Systemd)**: ユーザーセッションの Systemd サービスとして動作します。
  - `make start-mcp`: ゲートウェイを起動します。
  - `make stop-mcp`: ゲートウェイを停止します。
  - `make status-mcp`: 稼働状態を確認します。
  - `make logs-mcp`: リアルタイムログを表示します (`journalctl -f`)。
- **設定**: `mcp/config.yaml` がマスター設定であり、`make setup-docker-mcp` によって `~/.docker/mcp/config.yaml` へ同期されます。

## SkillPort & MCP の統合

`skillport-mcp` を MCP サーバーとして Docker MCP Gateway に登録することで、エージェントは `agent-skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、各スキルを MCP ツールとして公開します。
2. **利用方法**: エージェント（Claude, Gemini, Cursor）で Docker MCP Gateway (`:10888`) を設定するだけで、すべてのスキルが自動的にロードされます。
3. **同期**: スキルを追加・修正した後は、エージェントが最新の状態を認識できるよう、必要に応じて `make sync-agents` やゲートウェイの再起動を行ってください。

## Antigravity (Standalone MCP Config)

[Antigravity](https://github.com/gotalab/antigravity) は、特定の AI エージェント（主に OpenCode 等）が Docker MCP Gateway を介さずに、直接 MCP サーバーに接続するためのスタンドアロン設定を管理します。

- **役割**: Docker MCP Gateway (`:10888`) を SSE Gateway として利用し、個別の MCP ツールをシームレスに統合します。
- **設定**: `~/.gemini/antigravity/mcp_config.json` にゲートウェイの URL (`http://localhost:10888/sse`) を定義します。
- **統合**: これにより、Antigravity を利用するエージェントは、Docker MCP Gateway で稼働している SkillPort MCP 等のツールを透過的に利用可能になります。

## デプロイ構造 (シンボリックリンク)

`make setup` を実行すると、リポジトリ内の設定ファイルが各エージェントの構成ディレクトリへシンボリックリンクとして配備されます。

| エージェント / ツール | シンボリックリンク (配置先) | 実体 (リポジトリ内) |
|:-------------------|:----------------------|:-------------------|
| **Global Rules** | `~/.gemini/GEMINI.md` | `global-rules/AGENTS.global.md` |
| | `~/.claude/CLAUDE.md` | `global-rules/AGENTS.global.md` |
| | `~/.config/opencode/AGENTS.md` | `global-rules/AGENTS.global.md` |
| **Docker MCP** | `~/.docker/mcp/config.yaml` | `mcp/config.yaml` |
| | `~/.docker/mcp/catalog.json` | `mcp/catalog.json` |
| | `~/.docker/mcp/catalogs/` | `mcp/catalogs/` |
| **Claude Code** | `~/.claude/settings.json` | `claude/claude-settings.json` |
| **Gemini CLI** | `~/.gemini/settings.json` | `gemini/settings.json` |
| | `~/.gemini/core` | `gemini/Core` |
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` | `antigravity/mcp_config.json` |
| **OpenCode** | `~/.config/opencode/opencode.jsonc` | `opencode/opencode.jsonc` |
| | `~/.config/opencode/antigravity.json` | `opencode/antigravity.json` |
| | `~/.opencode/commands` | `opencode/commands` |
| **Codex** | `~/.codex` | `codex/` |
| **SkillPort** | `~/.skillport/skills` | `agent-skills/` |
| **Cursor** | `~/.cursor/` | `ide/cursor/` |
| **VSCode** | `~/.config/Code/User/settings.json` | `ide/vscode/settings.json` |

## SSOT 原則

- **ルールの編集**: 
  - ユーザー共通設定は `global-rules/AGENTS.global.md` を編集。
  - `dotfiles-ai` プロジェクト固有の設定はルートの `AGENTS.md` を編集。
  - 個別のスキルは `agent-skills/*/SKILL.md` を編集。
- **同期コマンド**:
  - `make setup`: リポジトリの初期化、ツールのインストール、設定ファイルの初回配置（シンボリックリンク作成）を実行します。
  - `make sync-agents`: `agent-skills` や `global-rules` の変更を、各エージェントの個別設定ファイルへ伝搬・同期します。
- **禁止事項**: 
  - **ホームディレクトリ上の設定ファイル**（例: `~/.gemini/GEMINI.md`, `~/.claude/CLAUDE.md`）を直接編集しないでください。これらはリポジトリ内のファイルへのシンボリックリンクであり、直接編集するとリンクが壊れたり、リポジトリ管理外の変更が発生したりします。
  - 修正は必ずリポジトリ内の管理ファイル（`global-rules/AGENTS.global.md`, `AGENTS.md` 等）に対して行ってください。

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| スキル記述 | Markdown (SKILL.md) |
