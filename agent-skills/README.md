# Agent Skills System (Powered by SkillPort)

このディレクトリは、Anthropic 標準の「Agent Skills」仕様に基づいた AI エージェント用スキルの集中管理場所です。

## 概要

SkillPort を利用することで、Cursor、VS Code、Claude Code などの異なるエージェント間で共通のプロンプト、ルール、専門知識を共有（Write Once, Run Anywhere）できます。

- **SSOT (Single Source of Truth)**: `agent-skills/` 配下の `SKILL.md` が全スキルの正のデータです。
- **管理ツール**: [skillport CLI](https://github.com/gotalab/skillport) を使用して、スキルの追加・検証・同期を行います。

## 前提条件

このシステムを利用するには以下のツールが必要です。

- **uvx**: [uv](https://github.com/astral-sh/uv) パッケージマネージャー。
- **skillport CLI**: `uvx skillport` で実行。

## 基本的な使い方

### 1. 新しいスキルを作成する (ローカル)

自作スキルは `agent-skills/custom/` ディレクトリ配下で管理します。 `agent-skills/.skillport/templates/SKILL_TEMPLATE.md` をコピーして新しいディレクトリを作成します。以下のコマンドはリポジトリのルートで実行してください。

```bash
# 例: my-new-skill というスキルを作成
mkdir -p agent-skills/custom/my-new-skill
cp agent-skills/.skillport/templates/SKILL_TEMPLATE.md agent-skills/custom/my-new-skill/SKILL.md
```

### 2. 外部スキルを導入する (GitHub等)

GitHub 等で公開されているスキルをプロジェクトに導入します。このプロジェクトでは原則として `apm` を使用して外部スキルを管理します（`apm.yml` 参照）。

```bash
# apm を使用する場合 (推奨)
# apm.yml に追加して実行
make apm-install
```

> [!IMPORTANT]
> **Git 管理のルール**
> `agent-skills/` ディレクトリでは、**`custom/` 配下の自作スキルのみが Git 管理対象**となります。
> 外部から導入したスキル（`anthropics/` や `superpowers/` 等）の実体またはリンクは `.gitignore` により除外されます。

<!-- -->

> [!TIP]
> **ディレクトリ指定の重要性**
> リポジトリのルートを直接指定（例: `anthropics/skills`）すると、ルートにある `template` フォルダなどがバリデーションエラーを引き起こし、導入に失敗することがあります。
> エラー（`frontmatter.name` の不一致など）が発生した場合は、リポジトリ内の有効なスキルが格納されているディレクトリ（通常は `skills/` や `src/`）を明示的に指定してください。

*   `--namespace`: スキルをサブディレクトリ（例: `superpowers/brainstorming`）に整理します。
*   `--force`: 既存のスキルを上書きする場合に指定。

### 3. スキルを更新する

導入済みの外部スキルを一括で最新に更新します。

```bash
uvx skillport update --all
```

### 4. スキルを検証する

`SKILL.md` の記述が仕様（名称、Objective、Workflow等）に準拠しているか確認します。

```bash
uvx skillport validate agent-skills/custom/my-new-skill
```

## プロジェクト固有の同期フロー

スキルの追加・修正後は、以下のコマンドでプロジェクト全体のドキュメントや各エージェント（OpenCode, Gemini 等）へ同期します。

```bash
# スキル一覧 (AGENTS.md) の更新と各エージェントへの配備
make sync-agents
```

※ `make sync-agents` は内部で `skillport doc` を実行し、`agent-skills/` をソースとして `agent-skills/AVAILABLE_SKILLS.md` の `<!-- SKILLPORT_START -->` マーカー内にスキルリストを直接反映します。各 `AGENTS.md` はコンテキストの肥大化を避けるため、このファイルへのリンクのみを保持します。自作スキルは `custom/<name>`、配布スキルは `anthropics/<name>` や `superpowers/<name>` といったネームスペース付きで識別されます。

## スキル設計の原則

- **DRY (Don't Repeat Yourself)**: 重複するルールは汎用的なスキルにまとめ、必要に応じて読み込む。
- **三人称記述**: `description` は常に「エージェントが何をするか」を三人称で記述する（例: "Analyzes code..."）。
- **メタプロンプトの活用**: 必要に応じて `REFERENCE.md` 等に詳細な仕様を分離し、`SKILL.md` はワークフローに集中させる。
