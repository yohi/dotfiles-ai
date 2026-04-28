# dotfiles-ai: APM Auto-Installation Design

## Goal
Automate the installation of the `apm` (Agent Package Manager) command and its execution (`apm install`) within the `make` workflow to ensure a seamless setup experience.

## Approaches
- **Full Automation**: `make setup` will automatically install the `apm` command if it is missing, then proceed to run `apm install`.

## Changes

### 1. Variables (`_mk/variables.mk`)
Add `APM_INSTALL_URL` to point to the official Microsoft APM installation script for Unix systems.

### 2. SkillPort Module (`_mk/skillport.mk`)
Add `install-apm` target:
- Check if `apm` is in `PATH`.
- If not, run `curl -sSL https://aka.ms/apm-unix | sh`.
- Support both Homebrew (if available) and the direct script as a fallback.

### 3. Main Workflow (`_mk/main.mk`)
Modify `setup` target:
- Add `install-apm` as a prerequisite or call it at the beginning of the recipe.
- Ensure `apm install` runs after `install-apm`.

## Success Criteria
- Running `make setup` on a machine without `apm` installs the `apm` command.
- `apm install` is executed correctly during `make setup`.
- `make setup` remains idempotent if `apm` is already installed.
