# dotfiles-ai

AIエージェント（Claude Code, Gemini CLI, OpenCode, Codex）の設定・スキル・ルールを
一元管理するコンポーネントリポジトリです。
`dotfiles-core` と連携して動作します。

**SSOT（Single Source of Truth）** 方式で、共通のスキル定義とコーディングルールを
管理し、各エージェントへ自動配備します。

## 管理と共存関係

> [!IMPORTANT]
> 本リポジトリは [dotfiles-core](https://github.com/yohi/dotfiles-core)
> によって管理されるコンポーネントの一つです。
> [!WARNING]
> **使用時の注意点**
> 本リポジトリは `dotfiles-core` の共通 Makefile ルール（`common-mk`）に依存しており、
> 実行時には `common-mk` へのシンボリックリンクが必要です。そのため、
> **本リポジトリ単体での使用（クローンしての利用）はサポートされていません。**
>
> 推奨される使用方法は、`dotfiles-core` リポジトリから `make setup` を実行し、
> 適切なディレクトリ構造とシンボリックリンクが構成された状態で利用することです。

## Claude Code プラグインの管理 (APM)

[Claude Code](https://github.com/anthropics/claude-code) のプラグイン（コードベースの拡張）は、
`apm.yml` の `dependencies` セクションで一元管理されます。

- **管理方式**: 公式リポジトリの特定パス（例:
  `anthropics/claude-code//plugins/code-review`）を依存関係として定義します。
- **デプロイプロセス**:
  1. `apm install` によりプラグインが `apm_modules/` にダウンロードされます。
  2. `agent-commands/` に配置されたコマンド定義（`.md`）が、
     `make sync-agents` を通じて各エージェントへ自動配備されます。
     具体的には以下のパスへ配備・同期されます：
     - **Claude Code**: `claude/commands/` (および
       `~/.claude/agent-commands/` 等へのシンボリックリンク)
     - **OpenCode**: `opencode/commands/` (および
       `~/.config/opencode/commands/` 等へのシンボリックリンク)
     - **Gemini CLI**: `gemini/commands/` (TOML 形式に自動変換して配備)
     - **Cursor IDE**: `.cursor/rules/` (および
       `ide/cursor/commands/agent/` へのシンボリックリンク)
- **カスタマイズ**: `agent-commands/` 配下のファイルは、公式テンプレートをベースにしつつ、
  本プロジェクトの環境（MCPツール等）に最適化されたカスタマイズ版です。

## ディレクトリ構成

```text
.
├── Makefile
├── README.md
├── AGENTS.md
├── apm.yml                 # [SSOT] APM 設定・外部スキル依存関係
├── .env.example            # 環境変数テンプレート
├── .agents/skills/         # [RUNTIME] 全エージェント共通スキル実体
├── agent-skills/           # [AUTHORING] custom スキル編集元 + 生成インデックス
├── agent-commands/         # [SSOT] Slash commands
├── global-rules/           # [SSOT] Global AI rules
├── claude/                 # Claude Code specific settings
├── gemini/                 # Gemini CLI specific settings
├── opencode/               # OpenCode specific settings
├── codex/                  # Codex specific settings
├── ide/                    # IDE AI settings (MCP)
└── mcp/                    # MCP 設定・運用ガイド
```

## 主要機能

- **SkillPort**: 全エージェントで再利用可能なスキルの SSOT 管理。
- **APM 直接管理 MCP**: stdio / リモート SSE / Streamable HTTP による各エージェント向け
  MCP サーバーの一元管理。
- **SSOT ルール管理**: 規約やユーザー指示の一元化と自動同期。
- **マルチエージェント対応**: Claude Code, Gemini CLI, OpenCode, Codex,
  Cursor/VSCode への自動配備。

## ルール管理構造 (SSOT)

本プロジェクトでは、AIエージェントへの指示を以下の2層で管理しています。

1. **グローバル指示 (`global-rules/AGENTS.global.md`)**:
   - ユーザーのアイデンティティ、言語設定（日本語優先）、セキュリティ、
     全 AI 共通の行動指針。
   - `~/.gemini/GEMINI.md` や `~/.claude/CLAUDE.md` などの
     ホームディレクトリ設定の**リンク元（実体）**となります。
2. **プロジェクト指示 (`AGENTS.md`)**:
   - このリポジトリ（`dotfiles-ai`）固有のルール、
     利用可能なスキルのリスト、リポジトリ構成の解説。

`global-rules/AGENTS.global.md` と `AGENTS.md` は責務が異なる独立した
instruction file です。共通のスキル一覧が必要な場合は `agent-skills/`
からそれぞれへ直接反映します。

## スキル管理 (SkillPort)

[SkillPort](https://github.com/gotalab/skillport) は、複数の AI エージェント間で
再利用可能な「スキル」を一元管理するためのツールです。

- **スキルの 3 層配置**:
  - **外部 skill（Runtime）**: `.agents/skills/` 配下に APM インストール済みの
    外部 skill が配置されます。
  - **グローバル自作 skill**: `agent-skills/custom/` に
    `yohi/agent-skills` 由来の自作 skill を配置します（APM 管理）。
  - **プロジェクト固有 skill**: `.claude/skills/<name>/` に配置します
    （Claude Code / OpenCode 両対応）。
    `make sync-agents` により `AVAILABLE_SKILLS.md` 等へ反映されます。
- **外部スキルの管理 (APM)**: `superpowers` などの高品質な外部スキルは、
  `apm.yml` の `dependencies` で管理され、
  `apm.lock.yaml` でバージョン（コミットハッシュ）が固定されます。
  - **スキルインストール**: `apm install` で `apm.yml` に記載された
    全外部スキルをインストールします。
  - この操作は `make setup` 実行時にも自動で行われます。
- **構成**: `.skillportrc` の `skills_dir` は `./.agents/skills` を指します。
  `~/.skillport/skills`・`~/.opencode/skills`・`~/.claude/skills` は、
  `.agents/skills/` への symlink アダプタです。
- **スキル配置**: `.agents/skills/` に外部 skill を集約。
  プロジェクト固有 skill は `.claude/skills/` に、
  グローバル自作 skill は `agent-skills/custom/` に配置。
- **コマンド**:
  - `skillport <command>`: スキルの追加・削除・更新などの管理操作は、
    `skillport` CLI を直接使用してください（`make` 経由ではありません）。
  - `skillport check`: スキル定義ファイル（.md）の構文や整合性をチェックします。

## APM による一元管理と MCP 直接管理

[Agent Package Manager (APM)](https://github.com/microsoft/apm)
([Docs](https://microsoft.github.io/apm/)) は AI エージェント設定の
Single Source of Truth (SSOT) です。
本プロジェクトでは、すべての MCP サーバーを APM (`apm.yml`) から
直接管理する**単一レイヤーアーキテクチャ**を採用しています。

- **APM 直接管理**: Filesystem / SQLite / GitHub / AWS 各種 / Sentry など、
  すべての MCP サーバーを `apm.yml` で定義し、
  `make sync-mcp` で各エージェントへ反映します。
- **安全な実行**: ホストに直接アクセスするツールも、
    APM による標準的な stdio、リモート SSE、または Streamable HTTP 接続で管理します。
- **スキル配置**: `.agents/skills/` に集約（全エージェントが参照）
- **自動生成ファイルと Git**:
  これらは `.gitignore` で除外されており、Git 管理の対象外です。

### 環境変数の3層モデル

| Tier | ソース | コンテンツ |
| :--- | :--- | :--- |
| Tier 1 | OS / シェル環境 | API Keys, PATs, GITHUB_TOKEN, GREPTILE_API_KEY |
| Tier 2 | `.env` (Git除外) | 環境固有設定 |
| Tier 3 | `apm.yml` | デフォルト値 |

`.env.example` を `.env` にコピーして使用してください。

## MCP (Model Context Protocol)

すべての MCP サーバーは `apm.yml` の `dependencies.mcp` セクションで
一元管理されます。

- **役割**: AI エージェントが利用する各種ツール（ファイルシステム、データベース、
  GitHub、AWS、Sentry 等）を標準的な MCP 経由で提供します。
- **設定の同期**: `make sync-mcp` を実行すると、`apm.yml` から
  対応するエージェント/IDE 向け（Claude Code, OpenCode, VSCode, Cursor, Antigravity）の MCP 設定ファイルが自動生成されます。Gemini CLI や Codex CLI については自動同期の対象外であるため、個別の設定同期コマンドを実行するか、各ツールの手順に従って手動で設定してください。

そのため、Antigravity CLI では `skillport` / `nexus` / `chronos-graph` を
 direct stdio MCP として使う構成を推奨します。
Antigravity 設定は `make sync-antigravity` で
`antigravity/mcp_config.json` を生成し、
`~/.gemini/antigravity-cli/mcp_config.json` へリンクします。

## SkillPort & MCP の統合

`skillport-mcp` を直接各エージェントの stdio MCP サーバーとして登録することで、
エージェントは `.agents/skills/` 内の全スキルを MCP Tool として動的に利用できます。

1. **仕組み**: `skillport-mcp` が起動時にスキルディレクトリをスキャンし、
   各スキルを MCP ツールとして公開します。
2. **利用方法**: `apm.yml` で `skillport` を有効にしている限り、
   全エージェントは stdio 経由で自動的に全スキルを利用できます。
3. **スキル配置先**: `.agents/skills/` (APM 標準クロスプラットフォーム)
4. **実体 (Runtime)**: `.agents/skills/`
   （ローカル custom スキルの編集元は `agent-skills/custom/`）

## エージェント設定の自動同期 (APM)

`make sync-mcp` によって、APM は各エージェントの設定ファイル
（`mcp.json` や `settings.json` 等）を自動生成・更新します。

- **Automated Flow**:
  `make setup` -> `apm install` -> `make sync-mcp` -> `make setup-agents`。

| エージェント | 接続方式 | 管理主体 |
| :--- | :--- | :--- |
| Claude Code | stdio / remote | `make sync-mcp` (生成元 `.claude.json` 等) |
| Gemini CLI | stdio | `make sync-mcp`（非自動同期。手動配置） |
| Antigravity CLI | Direct stdio MCP | `make sync-antigravity` |
| Cursor | stdio | `make sync-mcp` (生成元 `.cursor/mcp.json`) |
| OpenCode | stdio / remote | `make sync-opencode` |
| VSCode | stdio | `make sync-mcp` (生成元 `ide/vscode/settings.json`) |
| Codex | stdio | `make sync-mcp`（非自動同期。手動配置） |

`make setup` を実行すると、リポジトリ内の設定ファイルが各エージェントの
構成ディレクトリへ配備されます。

| エージェント / ツール | シンボリックリンク (配置先) | 実体 (リポジトリ内) |
| :--- | :--- | :--- |
| Global Rules | `~/.gemini/GEMINI.md` | `global-rules/AGENTS.global.md` |
| MCP Config | `~/.config/...` | `mcp/README.md` (ガイド) |
| Gemini CLI | `~/.gemini/settings.json` | Updated by sync script |
| Antigravity | `~/.gemini/antigravity/...` | `antigravity/mcp_config.json` |
| Cursor | `.cursor/mcp.json` | `ide/cursor/mcp.json` |

## SSOT 原則

- **ルールの編集**:
  - ユーザー共通設定は `global-rules/AGENTS.global.md` を編集。
  - ローカル custom スキルは `agent-skills/custom/*/SKILL.md` を編集
    （外部スキルは `apm.yml` で管理）。
  - **カスタム MCP サーバーの追加・変更・有効化**、および
    **エージェント/IDE の接続設定変更**は、全て **`apm.yml`** を編集してください。
- **同期コマンド**:
  - `make sync-mcp`: MCP 設定の再生成と同期。
  - `make sync-agents`: `.agents/skills/` の runtime tree と
    `agent-skills/custom/` から `agent-skills/AVAILABLE_SKILLS.md` を再生成。

## 主要な make ターゲット

| ターゲット | 説明 |
| :--- | :--- |
| `make setup` | 全体のセットアップ |
| `make apm-install` | APM インストール + 同期 |
| `make setup-apm-env` | .env ファイルの雛形作成 |
| `make sync-mcp` | MCP 設定の再生成と各エージェントへの反映 |
| `make sync-gemini-codex` | Gemini / Codex の MCP 設定を `apm.yml` から生成 |
| `make sync-claude` | Claude の MCP 設定を `apm.yml` から生成 |
| `make skillport` | SkillPort の初期セットアップ |
| `make check-skillport` | インストール状態の確認 |

## 技術スタック

| カテゴリ | テクノロジー |
| :--- | :--- |
| スキル管理 | [skillport](https://github.com/gotalab/skillport) CLI |
| ツール管理 | APM (`apm.yml`) による stdio / remote SSE / Streamable HTTP |
| ビルド自動化 | GNU Make (`_mk/*.mk`) |
| 構成管理 | Bash, jq, systemd |
