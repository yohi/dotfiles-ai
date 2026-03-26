# OpenCode A2A Provider Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** OpenCode の設定ファイルに A2A プロバイダーを追加し、ローカルのプロバイダーパッケージを利用可能にする。

**Architecture:** `opencode/opencode.jsonc` の `provider` セクションを編集し、`file://` プロトコルを用いてローカルパスを指定したプロバイダー定義を追加する。

**Tech Stack:** JSONC (JSON with Comments), OpenCode Configuration

---

### Task 1: `opencode/opencode.jsonc` への A2A プロバイダー追加

**Files:**
- Modify: `opencode/opencode.jsonc`

**Step 1: `provider` セクションに A2A プロバイダー設定を挿入する**

```jsonc
    "opencode-geminicli-a2a": {
      "npm": "file:///home/y_ohi/program/opencode-geminicli-a2a",
      "models": {
        "gemini-3.1-pro-preview": true,
        "gemini-3-flash-preview": true,
        "gemini-2.5-pro": true
      }
    },
```

**Step 2: 構文エラーがないか確認する**

JSONC 形式として正しいか、カンマの過不足などがないか目視で確認する。

**Step 3: コミット**

```bash
git add opencode/opencode.jsonc
git commit -m "feat(opencode): add opencode-geminicli-a2a provider with local path"
```

---

### Task 2: 最終確認

**Step 1: ファイル内容の確認**

`cat opencode/opencode.jsonc` を実行し、正しく挿入されていることを確認する。
特に `npm` フィールドが `file:///home/y_ohi/program/opencode-geminicli-a2a` になっていることを重点的に確認する。
