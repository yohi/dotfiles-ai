# Repository Consistency Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix inconsistencies in `AGENTS.md`, `Makefile`, and `README.md` to ensure language policy compliance, build reliability, and clear setup instructions.

**Architecture:** Surgical updates to documentation and configuration files.

**Tech Stack:** Markdown, GNU Make.

---

### Task 1: Update `AGENTS.md` Language Policy Compliance

**Files:**
- Modify: `AGENTS.md:3-4`

**Step 1: Replace Japanese notice with English equivalent**

Old string:
```markdown
> [!IMPORTANT]
> 共通の基本ルールは [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) を参照してください。
```

New string:
```markdown
> [!IMPORTANT]
> Please refer to [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) for common base rules.
```

**Step 2: Verify the change**

Run: `grep "Please refer to" AGENTS.md`
Expected: The updated English sentence is present.

### Task 2: Update `Makefile` to use Mandatory Includes

**Files:**
- Modify: `Makefile:3-4`

**Step 1: Change `-include` to `include` for core fragments**

Old string:
```makefile
-include _mk/core.mk
-include _mk/help.mk
```

New string:
```makefile
include _mk/core.mk
include _mk/help.mk
```

**Step 2: Verify the build still works**

Run: `make help`
Expected: The help menu is displayed correctly.

**Step 3: Verify "Fail Fast" behavior**

Run: `mv _mk/core.mk _mk/core.mk.bak && make help; mv _mk/core.mk.bak _mk/core.mk`
Expected: `make` fails with an error stating `_mk/core.mk` is missing.

### Task 3: Update `README.md` Standalone Setup Instructions

**Files:**
- Modify: `README.md:160-162`

**Step 1: Clarify `common-mk` placement for standalone usage**

Old string:
```markdown
## ⚠️  Standalone Usage Note
This repository depends on common Makefile fragments from [dotfiles-core](https://github.com/yohi/dotfiles-core). When using this repository standalone, ensure the **common-mk** directory is present in the parent directory, or use **dotfiles-core** as the orchestrator.
```

New string:
```markdown
## ⚠️  Standalone Usage Note
This repository depends on common Makefile fragments from [dotfiles-core](https://github.com/yohi/dotfiles-core). When using this repository standalone, ensure the **common-mk** contents are placed within the `_mk/` directory (so that `_mk/core.mk` and `_mk/help.mk` resolve), or use **dotfiles-core** as the orchestrator.
```

**Step 2: Verify the change**

Run: `grep -A 2 "Standalone Usage Note" README.md`
Expected: The updated instruction is present.
