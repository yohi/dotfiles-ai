# Fix Script Compatibility Implementation Plan (Completed)

Status: ✅ Implemented (Commits: 450fe85, 4b6556b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix compatibility issues in `_scripts/test-omo-profiles.sh` and overly strict validation in `_scripts/sync_agents.sh`.

**Architecture:** 
- Update `_scripts/sync_agents.sh` to validate the parent directory before checking for the output file's existence.
- Update `_scripts/test-omo-profiles.sh` to use POSIX-compliant `sed` instead of GNU-specific `grep -oP`.

**Tech Stack:** Shell (bash), sed, POSIX tools.

---

## Task 1: Update `_scripts/sync_agents.sh` validation logic

**Files:**
- Modify: `_scripts/sync_agents.sh`

- [x] **Step 1: Modify output file validation loop**

Replace the existing validation block with a hierarchical directory-and-file check.

```bash
<<<<
for output_file in "${OUTPUT_FILES[@]}"; do
    if [[ ! -f "$output_file" ]]; then
        echo "Error: Output file '$output_file' not found." >&2
        exit 1
    fi

    if [[ ! -w "$output_file" ]] || [[ ! -r "$output_file" ]]; then
        echo "Error: Output file '$output_file' is not accessible or writable." >&2
        exit 1
    fi

    run_skillport_doc "$output_file"
====
for output_file in "${OUTPUT_FILES[@]}"; do
    output_dir=$(dirname "$output_file")
    if [[ ! -d "$output_dir" ]] || [[ ! -w "$output_dir" ]]; then
        echo "Error: Output directory '$output_dir' does not exist or is not writable." >&2
        exit 1
    fi

    if [[ -e "$output_file" ]]; then
        if [[ ! -f "$output_file" ]] || [[ ! -w "$output_file" ]] || [[ ! -r "$output_file" ]]; then
            echo "Error: Output file '$output_file' exists but is not a regular file or not accessible." >&2
            exit 1
        fi
    fi

    run_skillport_doc "$output_file"
>>>>
```

- [x] **Step 2: Commit changes**

```bash
git add _scripts/sync_agents.sh
git commit -m "fix: relax output file validation in sync_agents.sh to allow creation"
```

---

## Task 2: Update `_scripts/test-omo-profiles.sh` token extraction

**Files:**
- Modify: `_scripts/test-omo-profiles.sh`

- [x] **Step 1: Replace `grep -oP` with `sed`**

Replace the GNU-specific grep command with a POSIX-compliant sed command.

```bash
<<<<
    # Verify token is not empty
    token_val=$(grep -oP '"token"\s*:\s*"\K[^"]*' "oh-my-opencode.jsonc" || true)
====
    # Verify token is not empty
    token_val=$(sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "oh-my-opencode.jsonc" || true)
>>>>
```

- [x] **Step 2: Commit changes**

```bash
git add _scripts/test-omo-profiles.sh
git commit -m "fix: replace GNU-specific grep with POSIX sed in test-omo-profiles.sh"
```

---

## Task 3: Verification

- [x] **Step 1: Run `_scripts/sync_agents.sh` with existing files**

Run: `bash _scripts/sync_agents.sh`
Expected: Successfully synchronizes without error.

- [x] **Step 2: Run `_scripts/sync_agents.sh` with a missing file**

Run:
```bash
cp global-rules/AGENTS.global.md /tmp/AGENTS.global.md.bak
rm global-rules/AGENTS.global.md
bash _scripts/sync_agents.sh
```
Expected: Successfully creates `global-rules/AGENTS.global.md`.

- [x] **Step 3: Run `_scripts/test-omo-profiles.sh`**

Run: `bash _scripts/test-omo-profiles.sh`
Expected: PASS all tests, including token extraction.
