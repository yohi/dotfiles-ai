# dotfiles-ai

AIエージェント（Claude Code, Gemini CLI, OpenCode, Codex）の設定・スキル・ルールを一元管理するコンポーネントリポジトリです。
`dotfiles-core` と連携して動作します。

## 概要

**SSOT（Single Source of Truth）** 方式で、共通のスキル定義とコーディングルールを管理し、各エージェントへ自動配備します。

| ディレクトリ | 役割 |
|:------------|:-----|
| `agent-skills/` | **[SSOT]** 全エージェント共通のスキル定義群（skillport 管理） |
| `agent-commands/` | **[SSOT]** 全エージェント共通のスラッシュコマンド |
| `global-rules/` | **[SSOT]** コーディング規約・ルール・ユーザーレベル指示 |
| `claude/` | Claude Code 固有設定 |
| `gemini/` | Gemini CLI / SuperGemini 設定 |
| `opencode/` | OpenCode 固有設定 |
| `codex/` | Codex 固有設定 |
| `_mk/` | Makefile サブターゲット群 |

## セットアップ

```bash
# 全エージェント環境の一括セットアップ
make setup

# SSOT → 各エージェントへの同期のみ
make sync-agents

# レガシーファイルのクリーンアップ + 同期
make ai-setup
```

## 主要コマンド

### 統合コマンド

| コマンド | 説明 |
|:---------|:-----|
| `make setup` | 全ツールのインストール・設定・同期を一括実行 |
| `make sync-agents` | SSOT のスキル・ルールを各エージェントへ同期 |
| `make ai-setup` | クリーンアップ + 同期を一括実行 |
| `make clean-legacy` | 統合後の不要なレガシーファイルを削除 |

### ツール別コマンド

| コマンド | 説明 |
|:---------|:-----|
| `make install-claude-code` | Claude Code CLI をインストール |
| `make install-claudia` | Claudia (Claude Code GUI) をインストール |
| `make install-claude-ecosystem` | Claude Code + SuperClaude + Claudia を一括インストール |
| `make install-gemini-cli` | Gemini CLI をインストール |
| `make install-supergemini` | SuperGemini フレームワークをインストール |
| `make install-gemini-ecosystem` | Gemini CLI + SuperGemini を一括インストール |
| `make install-opencode` | OpenCode をインストール |
| `make opencode-update` | OpenCode をアップデート |
| `make install-codex` | Codex CLI をインストール |
| `make skillport` | skillport CLI + MCP をインストール・セットアップ |
| `make check-skillport` | skillport の状態を確認 |
| `make check-opencode` | OpenCode の状態を確認 |

### skillport CLI コマンド

| コマンド | 説明 |
|:---------|:-----|
| `skillport list` | インストール済みスキル一覧 |
| `skillport lint [id]` | スキルファイルのバリデーション |
| `skillport add <source>` | スキルを追加（ローカル / GitHub URL） |
| `skillport update [--all]` | スキルを更新 |
| `skillport remove <id>` | スキルを削除 |
| `skillport doc --all` | instruction files にスキルテーブルを生成 |

### エージェント内スラッシュコマンド

**OpenCode** (`opencode/commands/`):

| コマンド | 説明 |
|:---------|:-----|
| `/build-skill` | 新しい agent skill を作成 |
| `/git-pr-flow` | PR 作成フロー |
| `/setup-gh-actions-test-ci` | GitHub Actions CI セットアップ |

**SuperClaude** (Claude Code 内):

| コマンド | 説明 |
|:---------|:-----|
| `/sc:implement <機能>` | 機能実装 |
| `/sc:design <UI>` | UI/UX デザイン |
| `/sc:analyze <コード>` | コード分析 |
| `/sc:test <テスト>` | テストスイート |
| `/sc:improve <コード>` | コード改善 |

**SuperGemini** (Gemini CLI 内):

| コマンド | 説明 |
|:---------|:-----|
| `/user-implement <機能>` | 機能実装 |
| `/user-analyze <コード>` | コード分析 |
| `/user-design <UI>` | UI/UX デザイン |
| `/user-troubleshoot <issue>` | デバッグ |

## SSOT 原則

- **スキルの編集**: `agent-skills/` 配下の `SKILL.md` を編集
- **ルールの編集**: `global-rules/` 配下のファイルを編集
- **同期**: `make sync-agents` で各エージェントの設定ファイルへ反映
- **禁止**: `claude/`, `opencode/` 等のディレクトリ内でルールを直接編集しない

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| スキル記述 | Markdown (SKILL.md) |
