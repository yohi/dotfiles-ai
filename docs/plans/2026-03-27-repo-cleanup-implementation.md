# Repo Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove `.cursor`, `.gemini`, and `.opencode` from Git tracking and clean up the filesystem.

**Architecture:** 
1. Prevent future tracking via `.gitignore`.
2. Stop current tracking via `git rm -r --cached`.
3. Physical removal of junk directories.

**Tech Stack:** Git, Shell

---

## Task 1: Update .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Add patterns to .gitignore**
Add the following to the bottom of the "OpenCode" section:
```text
.opencode/
.cursor/
.gemini/
```

**Step 2: Verification**
Run: `grep -E ".opencode/|.cursor/|.gemini/" .gitignore`
Expected: ALL three lines listed.

**Step 3: Commit**
```bash
git add .gitignore
git commit -m "chore: .gitignore にエージェント生成ディレクトリを追加"
```

---

## Task 2: Untrack directories from Git Index

**Files:**
- Untrack: `.cursor/`, `.gemini/`, `.opencode/`

**Step 1: Run git rm --cached**
Run: `git rm -r --cached .cursor .gemini .opencode`

**Step 2: Verification**
Run: `git status`
Expected: `deleted` entries for those directories, with "nothing to commit" for those files once committed.

**Step 3: Commit**
```bash
git commit -m "chore: .cursor, .gemini, .opencode を Git 追跡から解除"
```

---

## Task 3: Physical Cleanup of legacy directories

**Files:**
- Delete: `.opencode/`, `.gemini/`

**Step 1: Delete directories**
Run: `rm -rf .opencode .gemini`

**Step 2: Verification**
Run: `ls -d .opencode .gemini`
Expected: "No such file or directory" error for both.

---

## Task 4: Final Verification

**Step 1: Check git status**
Run: `git status`
Expected: Working tree clean (ignoring the untracked .cursor directory which is handled by gitignore now).

**Step 2: Run sync-agents to ensure .cursor is still regenerated correctly**
Run: `make sync-agents`
Expected: Successful execution. Note that the `sync-agents` target intentionally recreates the `.cursor/rules` directory by executing `mkdir -p "$(REPO_ROOT)/.cursor/rules"`. This ensures readers understand that the `.cursor/` directory is regenerated on demand, while `.cursor/rules` remains untracked by design.
