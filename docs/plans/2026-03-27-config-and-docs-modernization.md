# 2026-03-27 設定ファイルとドキュメントの現代化 実装プラン

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** コードレビューの指摘事項に基づき、設定ファイル、ドキュメント、スクリプトを一括修正する。

**Architecture:** 設定ファイルの安全性向上、配置の適正化、ドキュメントの正確性向上、スクリプトの Bash 互換化。

**Tech Stack:** JSONC, Markdown, Bash, Git

---

### Task 1: OpenCode 基本設定の修正

**Files:**
- Modify: `opencode/opencode.jsonc`

**Step 1: ターゲットバージョンと npm publish 権限の修正**

- 3行目: `v1.2.x` -> `v1.3.x`
- 61行目: `"npm publish*": "ask"` -> `"npm publish*": "deny"`

**Step 2: 構文チェック**

Run: `node -e "const fs = require('fs'); const content = fs.readFileSync('opencode/opencode.jsonc', 'utf8').replace(/\/\/\s*.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, ''); JSON.parse(content);"`
Expected: PASS

**Step 3: コミット**

```bash
git add opencode/opencode.jsonc
git commit -m "fix(opencode): restore npm publish safety and update target version to v1.3"
```

### Task 2: oh-my-opencode 設定の修正

**Files:**
- Modify: `opencode/oh-my-opencode.jsonc`
- Modify: `opencode/oh-my-opencode.jsonc.template`

**Step 1: visual カテゴリの重複排除**

- `fallback_models` 配列の先頭の `"google/gemini-3.1-pro"` を削除。

**Step 2: コミット**

```bash
git add opencode/oh-my-opencode.jsonc opencode/oh-my-opencode.jsonc.template
git commit -m "fix(opencode): remove redundant model from visual fallback"
```

### Task 3: ドキュメントの修正

**Files:**
- Modify: `opencode/README.md`
- Modify: `opencode/ANALYSIS.ja.md`

**Step 1: frontier-asia プロファイルの修正**

- `README.md` 36行目付近: `GLM-5-free` -> `big-pickle (opencode)`

**Step 2: ANALYSIS.ja.md のモデル例を更新**

- 「マルチモデル・オーケストレーション」節のモデル例を、最新（Claude 4.x, GPT-5.x, Gemini 3.1 等）に更新。

**Step 3: コミット**

```bash
git add opencode/README.md opencode/ANALYSIS.ja.md
git commit -m "docs(opencode): update profile and model examples for consistency"
```

### Task 4: codex 設定の修正

**Files:**
- Modify: `codex/config.toml`

**Step 1: 絶対パスの削除**

- `[projects."/home/y_ohi/program/chronos-graph"]` セクションを削除。

**Step 2: コミット**

```bash
git add codex/config.toml
git commit -m "fix(codex): remove machine-specific absolute path"
```

### Task 5: 計画ドキュメントの修正

**Files:**
- Modify: `docs/plans/2026-03-26-optimized-config-design.md`
- Modify: `docs/plans/2026-03-26-optimized-config-implementation.md`
- Modify: `docs/plans/2026-03-27-opencode-permission-modernization-plan.md`
- Modify: `docs/plans/2026-03-27-opencode-permission-modernization.md`

**Step 1: 見出しレベルの修正 (MD001)**

- `### Task` -> `## Task`

**Step 2: sed コマンドと正規表現の修正**

- `sed 's#//.*$##'` -> `perl -pe 's|(?<!:)\/\/.*||g'` 等に修正。
- `node -e` の正規表現をブロックコメント対応版に修正。

**Step 3: 禁止パターン（deny）の追加**

- `docs/plans/2026-03-27-opencode-permission-modernization.md` に `curl | sh` 等を追加。

**Step 4: コミット**

```bash
git add docs/plans/*.md
git commit -m "docs(plans): fix markdown lint and improve validation scripts"
```

### Task 6: oh-my-openagent.jsonc の移動と修正

**Files:**
- Delete: `oh-my-openagent.jsonc`
- Create: `.opencode/oh-my-openagent.jsonc`

**Step 1: ファイルの移動とモデル ID の修正**

- ルートから `.opencode/` へ移動。
- モデル ID にプロバイダープレフィックス（`openai/`, `anthropic/`, `google/`）を付与。

**Step 2: コミット**

```bash
git rm oh-my-openagent.jsonc
git add .opencode/oh-my-openagent.jsonc
git commit -m "refactor(opencode): move oh-my-openagent config and use provider prefixes"
```

### Task 7: omo-profiles.sh の修正

**Files:**
- Modify: `opencode/omo-profiles.sh`

**Step 1: Bash 互換性と堅牢性の向上**

- `script_path` 取得部分を修正。
- `cd` と `pwd` を分離し、エラーチェックを導入。

**Step 2: コミット**

```bash
git add opencode/omo-profiles.sh
git commit -m "fix(opencode): improve bash compatibility and robustness of omo-profiles.sh"
```
