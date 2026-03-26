# OpenCode 権限設定の極限緩和 実装プラン

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** OpenCode の権限設定を「デフォルト許可」に変更し、自律性を最大化する。

**Architecture:** `opencode/opencode.jsonc` の `permission` セクションを再構成し、ブラックリスト方式を採用する。

**Tech Stack:** JSONC (OpenCode Configuration)

---

### Task 1: 現状の設定のバックアップと確認

**Files:**
- Read: `opencode/opencode.jsonc`

**Step 1: 現在の設定内容を再確認する**

Run: `cat opencode/opencode.jsonc`
Expected: 現在の `permission` 設定が表示されること。

---

### Task 2: 権限設定の更新（緩和の実施）

**Files:**
- Modify: `opencode/opencode.jsonc`

**Step 1: 設定ファイルを更新する**

以下の内容に基づき、`permission` セクションを全面的に書き換える。

```jsonc
  "permission": {
    "read": "allow",
    "list": "allow",
    "glob": "allow",
    "grep": "allow",
    "codesearch": "allow",
    "todoread": "allow",
    "edit": "allow",
    "todowrite": "allow",
    "websearch": "allow",
    "webfetch": "allow", // 緩和: ask -> allow
    "external_directory": "allow", // 緩和: ask -> allow
    "bash": {
      "*": "allow", // 極限緩和: ask -> allow (デフォルト許可)
      
      // --- 安全弁 (ask) ---
      "git push*": "ask",
      "git reset*": "ask",
      "npm publish*": "ask", // 緩和: deny -> ask
      
      // --- 禁止 (deny) ---
      "git add .": "deny", // 一括追加は禁止を維持
      "rm *": "deny",
      "rm -rf *": "deny",
      "ssh *": "deny",
      "sudo *": "deny",
      "su *": "deny"
    }
  },
```

**Step 2: JSON の構文チェックを行う**

Run: `node -e "const fs = require('fs'); const content = fs.readFileSync('opencode/opencode.jsonc', 'utf8').replace(/\/\/.*/g, ''); JSON.parse(content);"`
Expected: エラーが出ないこと（コメントを除去してパース確認）。

**Step 3: コミット**

```bash
git add opencode/opencode.jsonc
git commit -m "feat(opencode): modernize permissions to allow-by-default for maximum autonomy"
```

---

### Task 3: 設定の反映と検証

**Files:**
- Execute: `opencode/omo-profiles.sh`

**Step 1: プロファイルを再ロードして設定を反映させる**

Run: `source ./opencode/omo-profiles.sh && omo-set-profile hybrid`
Expected: `oh-my-opencode.jsonc` が新設定で更新されること。

**Step 2: 許可されたコマンドの動作確認（モックまたは説明）**

実際の OpenCode 環境で `git commit` 等を実行し、確認が出ないことを確認する（本セクションでは設定の整合性確認まで）。

**Step 3: 禁止コマンドの拒否確認**

`git add .` を実行し、権限エラーで拒否されることを確認する。
