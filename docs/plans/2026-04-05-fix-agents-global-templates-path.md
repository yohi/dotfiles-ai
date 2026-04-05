# AGENTS.global.md のテンプレートパスの例示を修正 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `global-rules/AGENTS.global.md` 内の Tips セクションにある具体的すぎる（かつ不正確な）パスの例示を修正する。

**Architecture:** `replace` ツールを使用して文字列を置換し、`grep` で確認した後、コミットする。

**Tech Stack:** None

---

### Task 1: `global-rules/AGENTS.global.md` の修正

**Files:**
- Modify: `global-rules/AGENTS.global.md`

**Step 1: 文字列の置換を実行**

Run: `replace`
Old: `(e.g., {skill_dir}/templates/SKILL_TEMPLATE.md if it exists)`
New: `(e.g., {path}/templates/<filename> if they exist)`

**Step 2: 修正内容の確認**

Run: `grep -C 2 "{path}/templates/<filename>" global-rules/AGENTS.global.md`
Expected: 修正後の行が表示されること。

**Step 3: コミット**

Run: `git add global-rules/AGENTS.global.md && git commit -m "docs: AGENTS.global.md のテンプレートパスの例示を修正"`
Expected: コミット成功。
