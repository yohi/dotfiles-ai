# Fix SuperGemini Symlink Portability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the absolute symbolic link `gemini/supergemini/supergemini` with a relative one pointing to `.`.

**Architecture:** Remove the existing absolute symlink and recreate it as a relative symlink.

**Tech Stack:** Shell (rm, ln, ls)

---

### Task 1: Replace Absolute Symlink with Relative Symlink

**Files:**
- Modify: `gemini/supergemini/supergemini`

**Step 1: Write the verification script**

Create `_scripts/verify_symlink.sh`:
```bash
#!/bin/bash
TARGET=$(readlink gemini/supergemini/supergemini)
if [ "$TARGET" == "." ]; then
    echo "✅ Success: Symlink is relative (.)"
    exit 0
else
    echo "❌ Failure: Symlink is $TARGET"
    exit 1
fi
```

**Step 2: Run verification to confirm it fails**

Run: `bash _scripts/verify_symlink.sh`
Expected: FAIL with "❌ Failure: Symlink is /home/y_ohi/..."

**Step 3: Replace the symlink**

Run: `rm gemini/supergemini/supergemini && ln -s . gemini/supergemini/supergemini`
Expected: Symlink replaced.

**Step 4: Run verification to confirm it passes**

Run: `bash _scripts/verify_symlink.sh`
Expected: PASS with "✅ Success: Symlink is relative (.)"

**Step 5: Commit changes**

Run: `git add gemini/supergemini/supergemini docs/plans/2026-04-05-fix-supergemini-symlink-design.md docs/plans/2026-04-05-fix-supergemini-symlink.md`
Run: `git commit -m "fix: replace absolute symlink with relative one for portability"`
Expected: Commit successful.

**Step 6: Cleanup**

Run: `rm _scripts/verify_symlink.sh`
Expected: Script removed.
