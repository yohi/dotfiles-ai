# Design Doc: Fixing Repository Consistency Findings

Date: 2026-03-28
Status: Approved

## Problem Statement

Several inconsistencies were identified in the `dotfiles-ai` repository:
1. `AGENTS.md` contains a Japanese notice in an otherwise English-maintained document.
2. `Makefile` uses optional includes (`-include`) for mandatory core fragments (`core.mk`, `help.mk`).
3. `README.md` provides misleading instructions for standalone setup regarding `common-mk` placement.

## Proposed Changes

### 1. `AGENTS.md` - English Notice Update
Update the `[!IMPORTANT]` block at the top of `AGENTS.md` to English to maintain consistency with the rest of the file.

- **Current:** `共通の基本ルールは [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) を参照してください。`
- **New:** `Please refer to [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) for common base rules.`

### 2. `Makefile` - Mandatory Includes
Change `-include` to `include` for `_mk/core.mk` and `_mk/help.mk` to ensure the build fails fast if these critical dependencies are missing.

- **Current:**
  ```makefile
  -include _mk/core.mk
  -include _mk/help.mk
  ```
- **New:**
  ```makefile
  include _mk/core.mk
  include _mk/help.mk
  ```

### 3. `README.md` - Standalone Setup Clarification
Update the "Standalone Usage Note" to correctly instruct users to place `common-mk` contents within `_mk/` (or ensure they are reachable as symlinks) so that the Makefile and documentation references resolve correctly.

- **New Instruction:** Clarify that `common-mk` contents should be placed within `_mk/` or mapped correctly.

## Verification Strategy

1. **`AGENTS.md`**: Visual inspection of the file.
2. **`Makefile`**: Run `make help` to ensure the Makefile still works. Temporarily rename `_mk/core.mk` to verify that `make` now fails as expected.
3. **`README.md`**: Visual inspection of the updated instructions.
