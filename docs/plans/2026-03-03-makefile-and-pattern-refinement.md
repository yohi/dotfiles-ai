# Makefile and Pattern Refinement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve robustness of `_mk/superpowers.mk` and ensure secure rule ordering in `opencode/patterns/pattern-2.jsonc`.

**Architecture:** Refactor Makefile symlink logic into a bash function, tighten version extraction with `awk`, quote script paths, and reorder JSONC permission rules.

**Tech Stack:** GNU Make, Bash, JSONC (JSON with comments).

---

### Task 1: Tighten Version Extraction in `_mk/superpowers.mk`

**Files:**
- Modify: `_mk/superpowers.mk:23-23`

**Step 1: Update the HASH extraction logic**

Replace the current `grep | awk` pipeline with a single `awk` command that performs an exact match on the namespace column.

```makefile
	@HASH=$$(awk -F'|' '$$2 ~ /^[[:space:]]*$(SUPERPOWERS_NS)[[:space:]]*$$/ {print $$4}' "$(MANIFEST_FILE)" | tr -d ' '); 
```

**Step 2: Verify the change**

Run: `make update-superpowers`
Expected: Successfully extracts the hash if it exists in `agent-skills/EXTERNAL_SKILLS.md`.

**Step 3: Commit**

```bash
git add _mk/superpowers.mk
git commit -m "refactor(makefile): tighten HASH extraction with exact namespace match"
```

---

### Task 2: Quote Script Paths in `_mk/superpowers.mk`

**Files:**
- Modify: `_mk/superpowers.mk:45-45`

**Step 1: Quote the `update-skill-manifest.sh` path**

Wrap `$(REPO_ROOT)/scripts/update-skill-manifest.sh` in double quotes.

```makefile
	bash "$(REPO_ROOT)/scripts/update-skill-manifest.sh" "$(SUPERPOWERS_NS)" "https://github.com/obra/superpowers" "$$HASH" "$$DATE" && 
```

**Step 2: Verify the change**

Run: `make pin-superpowers`
Expected: Executes without error even if the path contains spaces.

**Step 3: Commit**

```bash
git add _mk/superpowers.mk
git commit -m "fix(makefile): quote script path to handle spaces in REPO_ROOT"
```

---

### Task 3: Refactor Symlink Logic into `link_skills` Function

**Files:**
- Modify: `_mk/superpowers.mk:64-90`

**Step 1: Define `link_skills` function and replace duplicated loops**

Introduce a local bash function to handle the symlinking logic and call it for both destination directories.

```makefile
link-superpowers-antigravity: ## Antigravity IDE へスキルを個別にリンク
	@echo "🔗 superpowers: Antigravity IDE へスキルをリンク中..."
	@link_skills() { 
		local dest="$$1"; 
		mkdir -p "$$dest"; 
		if [ -d "$(LOCAL_SUPERPOWERS_DIR)" ]; then 
			for skill in "$(LOCAL_SUPERPOWERS_DIR)"/*; do 
				if [ -d "$$skill" ]; then 
					local base=$$(basename "$$skill"); 
					local target="$$dest/$$base"; 
					if [ -L "$$target" ] || [ ! -e "$$target" ]; then 
						ln -sfn "$$skill" "$$target"; 
					else 
						echo "⚠️  $$target exists and is NOT a symlink. Skipping."; 
					fi; 
				fi; 
			done; 
		fi; 
	}; 
	link_skills "$(ANTIGRAVITY_SKILLS_DIR)"; 
	link_skills "$(HOME)/.gemini/.agent/skills"
```

**Step 2: Verify the change**

Run: `make link-superpowers-antigravity`
Expected: Symlinks are created correctly in both locations.

**Step 3: Commit**

```bash
git add _mk/superpowers.mk
git commit -m "refactor(makefile): extract symlink logic into link_skills function"
```

---

### Task 4: Modernize `GEMINI.md` Update with Heredoc

**Files:**
- Modify: `_mk/superpowers.mk:108-112`

**Step 1: Replace `printf` with a heredoc**

Use `cat <<'EOF'` to append the workflow instructions.

```makefile
update-gemini-md-superpowers: ## ~/.gemini/GEMINI.md にワークフロー指示を追記
	@echo "📝 superpowers: GEMINI.md を更新中..."
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then 
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then 
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; 
		fi; 
		cat <<'EOF' >> "$(HOME)/.gemini/GEMINI.md"

## BEGIN Superpowers Workflow
# Superpowers Workflow
このプロジェクトでは [obra/superpowers](https://github.com/obra/superpowers) ワークフローを採用しています。

## 核心的ルール
- **スキル優先:** いかなるアクションの前にも必ず `using-superpowers` スキルを確認し、関連するスキルがあれば `activate_skill` で有効にしてください。
- **計画と設計:** 実装前に `brainstorming` で設計を固め、`writing-plans` で詳細なタスクリストを作成してください。
- **TDD:** すべての実装は `test-driven-development` スキルに従い、テストを先に書いてから実装してください。
- **検証:** 完了前に `verification-before-completion` を実行し、エビデンスに基づいた成功報告を行ってください。
## END Superpowers Workflow
EOF
	fi
```

**Step 2: Verify the change**

Run: `make update-gemini-md-superpowers`
Expected: `~/.gemini/GEMINI.md` is updated correctly.

**Step 3: Commit**

```bash
git add _mk/superpowers.mk
git commit -m "refactor(makefile): use heredoc for GEMINI.md updates"
```

---

### Task 5: Secure Permission Rules in `pattern-2.jsonc`

**Files:**
- Modify: `opencode/patterns/pattern-2.jsonc:48-53`

**Step 1: Reorder `bash` permission rules**

Move specific `deny` and `ask` rules before the permissive `git *` rule.

```jsonc
          "git push --force": "deny",
          "git push -f": "deny",
          "git clean *": "ask",
          "git add .": "ask",
          "git *": "allow",
          "*": "deny"
```

**Step 2: Verify the change**

Run: `grep -A 10 "git-specialist" opencode/patterns/pattern-2.jsonc`
Expected: Rules are in the correct order.

**Step 3: Commit**

```bash
git add opencode/patterns/pattern-2.jsonc
git commit -m "security(config): reorder git permission rules for safety"
```
