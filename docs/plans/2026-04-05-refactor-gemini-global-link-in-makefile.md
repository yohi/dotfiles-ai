# Refactor Gemini Global Link in Makefile Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve reliability of Gemini global configuration linking by adding backup logic and refactoring to a dedicated target in `_mk/gemini.mk`.

**Architecture:** 
1. Define `link-gemini-global-md` target in `_mk/gemini.mk`.
2. Add logic to back up existing `GEMINI.md` if it's a regular file.
3. Call this new target from `setup-supergemini`.

**Tech Stack:** Makefile, Shell

---

### Task 1: Refactor _mk/gemini.mk

**Files:**
- Modify: `_mk/gemini.mk`

**Step 1: Add link-gemini-global-md target**

Add variables and the new target before `setup-supergemini`:

```makefile
GEMINI_GLOBAL_MD := $(HOME_DIR)/.gemini/GEMINI.md
AGENTS_GLOBAL_MD := $(REPO_ROOT)/global-rules/AGENTS.global.md

.PHONY: link-gemini-global-md
link-gemini-global-md: ## GEMINI.md をグローバルルールにリンク
	@echo "🔗 Linking Gemini global configuration..."
	@mkdir -p $(dir $(GEMINI_GLOBAL_MD))
	@if [ -f $(GEMINI_GLOBAL_MD) ] && [ ! -L $(GEMINI_GLOBAL_MD) ]; then \
		echo "📦 Backing up existing GEMINI.md to .bak"; \
		mv $(GEMINI_GLOBAL_MD) $(GEMINI_GLOBAL_MD).bak; \
	fi
	@ln -sf $(AGENTS_GLOBAL_MD) $(GEMINI_GLOBAL_MD)
	@echo "✅ Linked $(GEMINI_GLOBAL_MD) -> $(AGENTS_GLOBAL_MD)"
```

**Step 2: Update setup-supergemini**

Remove the inline `ln -sf` for `GEMINI.md` and add `link-gemini-global-md` to the command list or as a dependency.

**Step 3: Verify the Makefile syntax**

Run: `make -n setup-supergemini`
Expected: No syntax errors, and the new link command is visible in the output.

**Step 4: Commit changes**

Run: `git add _mk/gemini.mk docs/plans/2026-04-05-refactor-gemini-global-link-in-makefile.md`
Run: `git commit -m "refactor(gemini): improve global GEMINI.md linking with backup logic"`
Expected: Commit successful.
