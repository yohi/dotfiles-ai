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
| `make mcp` | Docker MCP Gateway をセットアップ |
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

## Docker MCP Gateway

[Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) は、MCP サーバーを Docker コンテナとして安全かつポータブルに実行するためのオーケストレーターです。

### 特徴
- **セキュアな実行**: 各 MCP サーバーはホストから隔離されたコンテナ内で動作します。
- **豊富なカタログ**: 300 以上の MCP サーバー（SQLite, GitHub, AWS, Slack 等）が即座に利用可能です。
- **一元管理**: 複数のサーバーを 1 つのゲートウェイ経由で AI エージェントに提供します。

### 起動方法
セットアップ完了後、以下のコマンドで Gateway を起動できます：

```bash
# 全てのサーバーを有効にして 10888 ポートで起動
docker mcp gateway run --port 10888 --enable-all-servers

# 特定のサーバー（例: sqlite）のみを起動
docker mcp gateway run --servers sqlite
```

## デプロイ構造 (シンボリックリンク)

`make setup` を実行すると、リポジトリ内の設定ファイルが各エージェントの XDG 構成ディレクトリへシンボリックリンクとして配備されます。

| エージェント / ツール | シンボリックリンク (配置先) | 実体 (リポジトリ内) |
|:-------------------|:----------------------|:-------------------|
| **Docker MCP** | `~/.docker/mcp/config.yaml` | `mcp/config.yaml` |
| | `~/.docker/mcp/catalog.json` | `mcp/catalog.json` |
| | `~/.docker/mcp/catalogs/` | `mcp/catalogs/` |
| **Claude Code** | `~/.claude/settings.json` | `claude/claude-settings.json` |
| | `~/.claude/CLAUDE.md` | `claude/CLAUDE.md` |
| **Gemini CLI** | `~/.gemini/settings.json` | `gemini/settings.json` |
| | `~/.gemini/core` | `gemini/Core` |
| **OpenCode** | `~/.config/opencode/opencode.jsonc` | `opencode/opencode.jsonc` |
| | `~/.config/opencode/antigravity.json` | `opencode/antigravity.json` |
| | `~/.opencode/commands` | `opencode/commands` |
| **Codex** | `~/.codex` | `codex/` |
| **SkillPort** | `~/.skillport/skills` | `agent-skills/` |

## SSOT 原則

- **スキルの編集**: `agent-skills/` 配下の `SKILL.md` を編集
- **ルールの編集**: `global-rules/` 配下のファイルを編集
- **同期**: `make sync-agents` で各エージェントの設定ファイルへ反映
- **禁止**: `claude/`, `opencode/` 等のディレクトリ内でルールを直接編集しない

## 技術スタック

| カテゴリ | テクノロジー |
|:---------|:------------|
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/) |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| スキル記述 | Markdown (SKILL.md) |
