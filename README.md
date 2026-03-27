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
- **初期セットアップ**: `make setup-docker-mcp` を実行すると、`custom.yaml.template` から `custom.yaml` が生成され、Gateway の初期配置が完了します。
- **自動同期**: `mcp/servers.yaml` または catalog/template を編集したら `make sync-mcp` を実行してください。

## SkillPort & MCP の統合

`skillport-mcp` を MCP サーバーとして Docker MCP Gateway に登録することで、エージェントは `agent-skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、各スキルを MCP ツールとして公開します。
2. **利用方法**: 全てのエージェントは Docker MCP Gateway (`:10888/sse`) を参照するように統一されているため、自動的に全スキルがロードされます。

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
