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
- **First attempt**: If `brew` is available, run `brew install apm`.
- **Fallback**: If Homebrew is missing or fails, download the official script to a temporary file via `curl -sSL`, **verify its SHA256 hash**, and execute it.
- **Verification**: Ensure `apm` is available after installation, or exit with status 1.

### 3. Main Workflow (`_mk/main.mk`)
Modify `setup` target:
- Add `install-apm` as a prerequisite or call it at the beginning of the recipe.
- Ensure `apm install` runs after `install-apm`.

## Success Criteria
- Running `make setup` on a machine without `apm` installs the `apm` command.
- `apm install` is executed correctly during `make setup`.
- `make setup` remains idempotent if `apm` is already installed.
