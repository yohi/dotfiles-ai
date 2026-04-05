# Link Global Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Manage Gemini CLI global context via symbolic link to version-controlled AGENTS.global.md.

**Architecture:** Replace existing `~/.gemini/GEMINI.md` with a symbolic link to `global-rules/AGENTS.global.md`.

**Tech Stack:** Shell (ln, mv, cat, realpath)

---

### Task 1: Backup and Symlink Creation

**Files:**
- Backup: `~/.gemini/GEMINI.md` -> `~/.gemini/GEMINI.md.bak`
- Create Link: `~/.gemini/GEMINI.md` -> `/home/y_ohi/dotfiles/components/dotfiles-ai/global-rules/AGENTS.global.md`

**Step 1: Backup existing GEMINI.md**

Run: `mv ~/.gemini/GEMINI.md ~/.gemini/GEMINI.md.bak`
Expected: File moved.

**Step 2: Create Symbolic Link**

Run: `ln -s /home/y_ohi/dotfiles/components/dotfiles-ai/global-rules/AGENTS.global.md ~/.gemini/GEMINI.md`
Expected: Symbolic link created.

**Step 3: Verify Link and Content**

Run: `ls -l ~/.gemini/GEMINI.md && cat ~/.gemini/GEMINI.md | tail -n 5`
Expected: 
- `ls -l` shows the link pointing to the correct absolute path.
- `cat` shows the content of `AGENTS.global.md` (e.g., the Superpowers Workflow section).

**Step 4: Commit design doc and plan**

Run: `git add docs/plans/2026-04-05-link-global-agents-to-gemini-md-design.md docs/plans/2026-04-05-link-global-agents-to-gemini-md.md`
Run: `git commit -m "docs: add design and plan for linking global AGENTS.md"`
Expected: Commit successful.
