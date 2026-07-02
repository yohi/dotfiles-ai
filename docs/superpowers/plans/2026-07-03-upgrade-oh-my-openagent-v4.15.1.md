# Upgrade oh-my-openagent to v4.15.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `oh-my-openagent` のバージョンを `v4.15.1` にアップデートし、設定の同期と検証を行います。

**Architecture:** `apm.yml` に定義された `oh-my-openagent` のパッケージバージョンを更新し、`make sync-opencode` を介して設定ファイル一式を再生成した上で、`make check-sync-opencode` を用いて整合性を検証します。

**Tech Stack:** `apm`, `make`, `bash`

## Global Constraints
- CLI出力やソースコード内の文字列はASCIIの印字可能文字（U+0020–U+007E）に収めること（日本語で書かれたドキュメント内の日本語は除く）。
- コミットは Git Standards に従い、Conventional Commits の規則を遵守すること。

---

### Task 1: apm.yml の更新と設定ファイル再生成

**Files:**
- Modify: `apm.yml`
- Test: 実行コマンドによる動作確認

- [ ] **Step 1: `apm.yml` のバージョンを更新する**
  `apm.yml` の `plugin:` セクションにある `"oh-my-openagent@4.13.0"` を `"oh-my-openagent@4.15.1"` に変更します。

- [ ] **Step 2: `make sync-opencode` を実行する**
  以下のコマンドを実行し、設定ファイルを再生成します。
  Run: `make sync-opencode`
  Expected: コマンドがエラーなく正常終了し、`opencode/oh-my-openagent.jsonc` などのファイルが再生成されること。

- [ ] **Step 3: `make check-sync-opencode` を実行して整合性を検証する**
  以下のコマンドを実行してモデル設定とスキーマの整合性を検証します。
  Run: `make check-sync-opencode`
  Expected: 正常終了し、モデルミスマッチなどのエラーが報告されないこと。

- [ ] **Step 4: コミットする**
  Run:
  ```bash
  git add apm.yml opencode/oh-my-openagent.jsonc.template opencode/oh-my-openagent.jsonc opencode/opencode.jsonc
  git commit -m "feat(opencode): oh-my-openagentをv4.15.1にアップデート"
  ```

---

### Task 2: opencode/README.md の更新

**Files:**
- Modify: `opencode/README.md`
- Test: ドキュメントの構文および内容確認

- [ ] **Step 1: Target Version の記述を更新する**
  `opencode/README.md` に記載されている `Target Version` や推奨モデル記述などのバージョン関連テキストを `v4.15.1` に変更します。既存の環境切り替え手順や zsh 連携スクリプトなどのプロジェクト固有情報は保護します。

- [ ] **Step 2: リポジトリ全体の Lint 状態を検証する**
  CI-mirror コマンド（Ruff や YAML 構造などのチェック）を実行して、ドキュメントの文法やインデントエラーがないことを確認します。
  Run: `uv run --extra dev ruff check src/ tests/` (または README.md に対する markdown チェック)

- [ ] **Step 3: コミットする**
  Run:
  ```bash
  git add opencode/README.md
  git commit -m "docs(opencode): READMEの対応バージョンをv4.15.1に更新"
  ```
