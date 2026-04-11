# Spec: Fix Script Compatibility and Output Validation

- **Date**: 2026-04-11
- **Status**: Draft
- **Topic**: Fix compatibility issues in `_scripts/test-omo-profiles.sh` and overly strict validation in `_scripts/sync_agents.sh`.

## 1. Background
Two scripts in the project have issues that hinder usability across different environments (macOS/Linux) or during initial setup:
- `_scripts/sync_agents.sh` fails if the output file does not exist, preventing the script from creating new files even if the parent directory is writable.
- `_scripts/test-omo-profiles.sh` uses `grep -oP`, which is specific to GNU grep and fails on macOS (BSD grep).

## 2. Objectives
- Ensure `_scripts/sync_agents.sh` can create new output files if they don't exist, as long as the parent directory is writable.
- Ensure `_scripts/test-omo-profiles.sh` can extract JSON values correctly on both Linux (GNU) and macOS (BSD) systems.

## 3. Design

### 3.1. `_scripts/sync_agents.sh` Validation Logic
Modify the loop that iterates over `OUTPUT_FILES` to perform hierarchical validation:
1. Identify the parent directory of the output file.
2. Verify that the parent directory exists and is writable (`[[ -d "$dir" ]] && [[ -w "$dir" ]]`).
3. If the output file already exists (`[[ -e "$output_file" ]]`):
    - Verify it is a regular file (`[[ -f "$output_file" ]]`).
    - Verify it is readable and writable (`[[ -r "$output_file" ]] && [[ -w "$output_file" ]]`).

### 3.2. `_scripts/test-omo-profiles.sh` Token Extraction
Replace the GNU-specific `grep -oP` with a POSIX-compliant `sed` command:
- **Old**: `grep -oP '"token"\s*:\s*"\K[^"]*'`
- **New**: `sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'`

This `sed` command:
- `-n`: Suppress automatic printing.
- `s/.../\1/p`: Search for the pattern and print the captured group (the value).
- `[[:space:]]*`: Match any whitespace character (POSIX compliant).

## 4. Verification Plan

### 4.1. `_scripts/sync_agents.sh`
1. **Existing File**: Run the script with existing files and verify it still works.
2. **Missing File**: Delete one of the output files and run the script. Verify it successfully creates the file.
3. **ReadOnly Directory**: Attempt to run the script where the output directory is not writable (e.g., `/tmp/no_write`) and verify it fails gracefully with a clear error message.

### 4.2. `_scripts/test-omo-profiles.sh`
1. **Run Tests**: Execute `_scripts/test-omo-profiles.sh` and ensure it still passes on the current system.
2. **Manual Check**: Run the `sed` command against a sample `oh-my-opencode.jsonc` file manually and verify it extracts the correct token value.

## 5. Constraints & Standards
- Maintain existing coding style (naming conventions, indentation).
- Ensure error messages are clear and directed to `stderr`.
- Adhere to POSIX shell standards where possible to maximize compatibility.
