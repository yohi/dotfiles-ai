# Design Document: Makefile and Pattern Configuration Refinement

## Overview
This document outlines the refinements to `_mk/superpowers.mk` and `opencode/patterns/pattern-2.jsonc` to improve robustness, security, and maintainability.

## 1. Makefile (`_mk/superpowers.mk`) Refinement

### 1.1 Robust Version Extraction
The current extraction of the version hash from `EXTERNAL_SKILLS.md` uses a loose `grep`. This will be replaced with a stricter `awk` command that ensures the namespace matches exactly.

**Current:**
```makefile
HASH=$$(grep "| $(SUPERPOWERS_NS) |" "$(MANIFEST_FILE)" | awk -F'|' '{print $$4}' | tr -d ' ');
```

**Proposed:**
```makefile
HASH=$$(awk -F'|' '$$2 ~ /^[[:space:]]*$(SUPERPOWERS_NS)[[:space:]]*$$/ {print $$4}' "$(MANIFEST_FILE)" | tr -d ' ');
```

### 1.2 Path Quoting for Script Execution
To prevent word-splitting in paths containing spaces, the invocation of `update-skill-manifest.sh` will be quoted.

**Current:**
```makefile
bash $(REPO_ROOT)/scripts/update-skill-manifest.sh "$(SUPERPOWERS_NS)" "https://github.com/obra/superpowers" "$$HASH" "$$DATE"
```

**Proposed:**
```makefile
bash "$(REPO_ROOT)/scripts/update-skill-manifest.sh" "$(SUPERPOWERS_NS)" "https://github.com/obra/superpowers" "$$HASH" "$$DATE"
```

### 1.3 Symlink Logic Refactoring
The duplicated loops in `link-superpowers-antigravity` will be refactored into a shell function `link_skills` to adhere to the DRY (Don't Repeat Yourself) principle.

**Proposed Functionality:**
- Accept a destination directory as an argument.
- Iterate over directories in `$(LOCAL_SUPERPOWERS_DIR)`.
- Use `ln -sfn` for safe symlinking.
- Check if the target is already a symlink or does not exist before creating it.

### 1.4 Heredoc for `GEMINI.md` Updates
The `printf` command used for appending workflow instructions will be replaced with a heredoc for better readability and reliability.

**Proposed:**
```makefile
cat <<'EOF' >> "$(HOME)/.gemini/GEMINI.md"

## BEGIN Superpowers Workflow
...
## END Superpowers Workflow
EOF
```

## 2. Pattern Configuration (`opencode/patterns/pattern-2.jsonc`) Security

### 2.1 Rule Evaluation Order
The `bash` permission rules for `git-specialist` will be reordered to ensure that specific restrictions (`deny` and `ask`) are evaluated before the general allowance (`git *`). This aligns with the secure patterns used in other configuration files.

**Proposed Order:**
1. `git push --force`: `deny`
2. `git push -f`: `deny`
3. `git clean *`: `ask`
4. `git add .`: `ask`
5. `git *`: `allow`
6. `*`: `deny`

## Success Criteria
- `make update-superpowers` and `make pin-superpowers` work correctly.
- `make link-superpowers-antigravity` creates correct symlinks without code duplication.
- `opencode/patterns/pattern-2.jsonc` denies/asks for dangerous git commands before allowing general git usage.
- `GEMINI.md` is updated correctly with the new heredoc approach.
