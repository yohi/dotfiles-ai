# Agent Skills System (Powered by SkillPort)

このディレクトリは、Anthropic 標準の「Agent Skills」仕様に基づいた AI エージェント用スキルの集中管理場所です。

## 概要
SkillPort を利用することで、Cursor、VS Code、Claude Code などの異なるエージェント間で共通のプロンプト、ルール、専門知識を共有（Write Once, Run Anywhere）できます。

- **保存場所**: `~/dots/agent-skills` (dotfiles 管理)
- **同期先**: `~/.skillport/skills` (SkillPort デフォルトディレクトリへのシンボリックリンク)

## 前提条件

このシステムを利用するには以下のツールが必要です。

- **uvx**: [uv](https://github.com/astral-sh/uv) パッケージマネージャーに含まれるツール実行ツール。
- **skillport CLI**: `uvx skillport` で実行、または `pip install skillport` でインストール。
- **skillport-mcp** (任意): MCP 経由でスキルを利用する場合に必要。

**インストール・検証コマンド:**
```bash
uvx --version
uvx skillport --version
```
※ SkillPort の MCP エントリは `cursor/mcp.json.template` に定義されており、`uvx skillport-mcp` を介して呼び出されます。

## 基本的な使い方

### 1. 新しいスキルを作成する
`.skillport/templates/SKILL_TEMPLATE.md` をコピーして新しいディレクトリを作成します。

```bash
# 例: new-skill というスキルを作成
mkdir -p agent-skills/new-skill
cp agent-skills/.skillport/templates/SKILL_TEMPLATE.md agent-skills/new-skill/SKILL.md
```

### 2. スキルを検証する
仕様に準拠しているか確認します。

```bash
# uvx を使用する場合
uvx skillport validate agent-skills/new-skill

# zsh エイリアスを使用する場合 (zsh/config.zsh)
spv agent-skills/new-skill
```

### 3. 外部スキルを導入する (Task 4.2)
GitHub 等で公開されている有用なスキルを導入します。

```bash
# skillport add コマンドを使用して GitHub から取得
uvx skillport add https://github.com/user/repo/path/to/skill
```

## AI クライアントへの統合 (MCP)

### Cursor
実際の設定ファイル `cursor/mcp.json` は機密情報保護のため Git 管理外です。設定例は `cursor/mcp.json.template` に定義されており、`make setup-mcp-tools` 等で反映できます。
- **Command**: `uvx skillport-mcp` (テンプレートに `@1.1.0` 等のバージョン指定を含めることを推奨)

### Claude Code
Claude Code は標準で MCP をサポートしています。

```bash
# Claude Code 実行時に MCP を指定（または設定に追加）
claude --mcp uvx skillport-mcp
```

## スキル設計の原則
- **DRY (Don't Repeat Yourself)**: 重複するルールは汎用的なスキルにまとめ、必要に応じて読み込む。
- **三人称記述**: `description` は常に「エージェントが何をするか」を三人称で記述する（例: "Analyzes code..."）。
- **段階的開示 (Progressive Disclosure)**: 巨大なドキュメントは `REFERENCE.md` 等に分離する。
