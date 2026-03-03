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
| `_mk/` | Makefile サブターゲット群 |

## ルール管理構造 (SSOT)

本プロジェクトでは、AIエージェントへの指示を以下の2層で管理しています。

1.  **グローバル指示 (`global-rules/AGENTS.global.md`)**:
    *   ユーザーのアイデンティティ、言語設定（日本語優先）、セキュリティ、全AI共通の行動指針。
    *   `~/.gemini/GEMINI.md` や `~/.claude/CLAUDE.md` などのホームディレクトリ設定の**実体**となります。
2.  **プロジェクト指示 (`AGENTS.md`)**:
    *   このリポジトリ（`dotfiles-ai`）固有のルール、利用可能なスキルのリスト、リポジトリ構成の解説。

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
| **OpenCode** | `~/.config/opencode/opencode.jsonc` | `opencode/opencode.jsonc` |
| | `~/.config/opencode/antigravity.json` | `opencode/antigravity.json` |
| | `~/.opencode/commands` | `opencode/commands` |
| **Codex** | `~/.codex` | `codex/` |
| **SkillPort** | `~/.skillport/skills` | `agent-skills/` |

## SSOT 原則

- **グローバルルールの編集**: `global-rules/AGENTS.global.md` を編集（全エージェントに即時反映）。
- **プロジェクトルールの編集**: ルートの `AGENTS.md` を編集。
- **スキルの編集**: `agent-skills/` 配下の `SKILL.md` を編集。
- **同期**: `make sync-agents` で各エージェントの設定ファイルへ反映。
- **禁止**: ホームディレクトリの `~/.gemini/GEMINI.md` や各サブディレクトリ内の `CLAUDE.md` 等を直接編集しない（シンボリックリンクが壊れます）。

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| スキル記述 | Markdown (SKILL.md) |
