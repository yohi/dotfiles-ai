# 2026-03-27 設定ファイルとスクリプトの安全性向上（追記分） 実装プラン

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** コードレビューの二次指摘に基づき、エラーハンドリングの追加、設定値とコメントの不整合解消、セキュリティパターンの追加を行う。

**Architecture:** スクリプトの堅牢化、設定ファイルのセキュリティ強化。

**Tech Stack:** JSONC, Bash, Git

---

## Task 1: omo-profiles.sh のエラーハンドリングの検証

**Files:**
- Verify: `opencode/omo-profiles.sh`

**Step 1: 実装済みの envsubst ステータスチェックを確認する**

```bash
    # 環境変数を展開して上書き生成 (対象変数のみを置換)
    if envsubst "$vars_to_subst" < "$template_path" > "$output_path"; then
      echo "📄 Config generated: $output_path"
    else
      echo "❌ Error: Failed to generate config with envsubst" >&2
      return 1
    fi
```

**Step 2: 差分を確認し、変更がなければコミットをスキップする**

Run: `git diff opencode/omo-profiles.sh`
Expected: 既に修正が反映されていることを確認。

## Task 2: opencode.jsonc の整合性とセキュリティ強化

**Files:**
- Modify: `opencode/opencode.jsonc`

**Step 1: npm publish* のコメント修正と禁止パターンの追加**

- 61行目: `// 緩和: deny -> ask` -> `// 誤公開防止: deny を維持`
- `bash` ブロックの `deny` セクションに以下を追加:
    - `"curl*|sh": "deny"`
    - `"git clean -fd*": "deny"`

**Step 2: experimental フラグの安全性向上**

- 75行目: `"continue_loop_on_deny": true` -> `false`

**Step 3: コミット**

```bash
git add opencode/opencode.jsonc
git commit -m "fix(opencode): align npm publish comment, add deny patterns, and secure experimental flags"
```
