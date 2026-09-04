# Agent Skills System (Powered by SkillPort)

このディレクトリは、Anthropic 標準の「Agent Skills」仕様に基づいた AI エージェント用スキルの集中管理場所です。

## 概要

SkillPort を利用することで、Cursor、VS Code、Claude Code などの異なるエージェント間で共通のプロンプト、ルール、専門知識を共有（Write Once, Run Anywhere）できます。

- **Runtime SSOT**: `.agents/skills/` が全エージェント共通の runtime skills です。
- **プロジェクト固有スキル**: `.claude/skills/<name>/` にプロジェクト固有 skill を配置します（Claude Code / OpenCode 両対応）。
- **グローバル自作スキル**: `agent-skills/custom/` は `yohi/agent-skills` 由来の自作 skill を配置する場所です（APM 管理対象）。
- **外部スキル**: `agent-skills/external/` に APM からインストールした外部 skill を配置します。
- **管理ツール**: [skillport CLI](https://github.com/gotalab/skillport) を使用して、スキルの追加・検証・同期を行います。

## スキルの 3 層分類

| 分類 | 置き場 | 管理主体 | Git 管理 |
|---|---|---|---|
| プロジェクト固有 | `.claude/skills/<name>/` | リポジトリ | **管理対象** |
| グローバル自作 | `agent-skills/custom/<name>/` | `yohi/agent-skills`（APM 展開） | 実体は無視、ソースは別リポジトリ |
| 外部 | `agent-skills/external/<name>/` | APM registry / Git URL | 無視 |

## 前提条件

このシステムを利用するには以下のツールが必要です。

- **uvx**: [uv](https://github.com/astral-sh/uv) パッケージマネージャー。
- **skillport CLI**: `uvx skillport` で実行。

## 基本的な使い方

### 1. 新しいスキルを作成する (プロジェクト固有)

プロジェクト固有の自作スキルは `.claude/skills/<name>/` ディレクトリ配下で管理します。Claude Code と OpenCode の両方がこのパスを読みます。

```bash
# 例: my-new-skill というスキルを作成
mkdir -p .claude/skills/my-new-skill
cp agent-skills/.skillport/templates/SKILL_TEMPLATE.md .claude/skills/my-new-skill/SKILL.md
```

> [!IMPORTANT]
> `.claude/` 配下は原則として Git 管理対象外ですが、**`.claude/skills/<name>/` 内のプロジェクト固有 skill のみを `git add -f` 等で明示的に追跡**します。他の `.claude/` 内ファイルは APM 生成物または個人設定として無視してください。

### 1b. グローバル自作スキルを編集する

複数プロジェクトで共有する自作スキルは `yohi/agent-skills` リポジトリで管理し、APM により `agent-skills/custom/` に展開されます。編集が必要な場合は `yohi/agent-skills` を直接編集してください。

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
# プロジェクト固有 skill
uvx skillport validate .claude/skills/my-new-skill

# グローバル自作 skill（yohi/agent-skills 由来）
uvx skillport validate agent-skills/custom/my-new-skill
```

## プロジェクト固有の同期フロー

スキルの追加・修正後は、以下のコマンドでスキルカタログを更新します。

```bash
make sync-agents
```

`make sync-agents` は内部で `skillport doc` を実行し、以下の 3 つの skill tree を元に `agent-skills/AVAILABLE_SKILLS.md` を更新します。

- `.agents/skills/` の runtime tree（外部 skill）
- `agent-skills/custom/` の custom tree（グローバル自作 skill）
- `.claude/skills/` のうち Git 追跡対象となっているプロジェクト固有 skill

`global-rules/AGENTS.global.md` は APM から複数 AI エージェントへ共通配布する軽量なグローバル指示として扱い、SkillPort の全カタログは埋め込みません。グローバル指示から `agent-skills/AVAILABLE_SKILLS.md` を参照し、必要な skill だけを SkillPort の `search_skills` / `load_skill` で段階的に読み込む構成です。

自作スキルは `custom/<name>`、配布スキルは `anthropics/<name>` や `superpowers/<name>` といったネームスペース付きで識別されます。

## スキル設計の原則

- **DRY (Don't Repeat Yourself)**: 重複するルールは汎用的なスキルにまとめ、必要に応じて読み込む。
- **三人称記述**: `description` は常に「エージェントが何をするか」を三人称で記述する（例: "Analyzes code..."）。
- **メタプロンプトの活用**: 必要に応じて `REFERENCE.md` 等に詳細な仕様を分離し、`SKILL.md` はワークフローに集中させる。
