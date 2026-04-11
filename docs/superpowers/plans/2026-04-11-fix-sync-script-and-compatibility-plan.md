# Fix Sync Script and Compatibility Implementation Plan (Completed)

Status: ✅ Implemented (Commits: abf29e2, 4b6556b, 450fe85, a0e287a, 907543d, 79290d3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix script compatibility and update `_scripts/sync_agents.sh` to prevent data loss by only updating skill sections within tags.

**Architecture:** 
- Modify `_scripts/sync_agents.sh` to update only the content between `<!-- SKILLPORT_START -->` and `<!-- SKILLPORT_END -->`.
- Relax `_scripts/sync_agents.sh` output validation to allow file creation.
- Replace GNU-specific `grep -oP` in `_scripts/test-omo-profiles.sh` with `sed`.

**Tech Stack:** Shell (bash), Perl, sed, POSIX tools.

---

## Task 1: Fix `run_skillport_doc` in `_scripts/sync_agents.sh`

**Files:**
- Modify: `_scripts/sync_agents.sh`

- [x] **Step 1: Rewrite `run_skillport_doc` function**

Update the function to output to a temporary file and then selectively update the target file using Perl.

```bash
run_skillport_doc() {
    local output_file="$1"
    local tmp_file
    tmp_file=$(mktemp)

    # (Generation logic using skillport or uvx omitted for brevity)

    if [[ -f "$output_file" ]] && grep -q "<!-- SKILLPORT_START -->" "$output_file" && grep -q "<!-- SKILLPORT_END -->" "$output_file"; then
        echo "Updating SkillPort section in existing ${output_file}..."
        # Slurp the entire tmp_file into $s and perform a tag-based replacement in the output_file.
        # This replaces everything between SKILLPORT_START and SKILLPORT_END tags.
        perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi
    rm "$tmp_file"
}
```

- [x] **Step 2: Modify output file validation loop**

**Verified and Validated:**
- **Loop Structure:** Maintained the for loop iterating over `OUTPUT_FILES` (`for output_file in "${OUTPUT_FILES[@]}"`).
- **Hierarchical Checks:**
    - **Directory Level:** Added existence and writability checks for the parent directory using `dirname "$output_file"`. If the directory is missing or read-only, the script exits immediately to prevent invalid file creation attempts.
    - **File Level:** If the target file already exists, confirmed it is a regular file with read and write permissions. If it doesn't exist, the script proceeds to create it (relaxed from previous "file must exist" requirement).
- **Function Execution:** `run_skillport_doc` is invoked for each file, followed by `normalize_locations` (to ensure relative paths) and `restore_external_skills_note` (to maintain critical warnings).

- [x] **Step 3: Commit changes**

```bash
git add _scripts/sync_agents.sh
git commit -m "fix(sync): protect existing content in sync_agents.sh using tags"
```

---

## Task 2: Update `_scripts/test-omo-profiles.sh` token extraction

**Files:**
- Modify: `_scripts/test-omo-profiles.sh`

- [x] **Step 1: Replace `grep -oP` with `sed`**

```bash
# 旧実装:
token_val=$(grep -oP '"token"\s*:\s*"\K[^"]*' "oh-my-opencode.jsonc" || true)

# 新実装:
token_val=$(sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "oh-my-opencode.jsonc" || true)
```

- [x] **Step 2: Commit changes**

```bash
git add _scripts/test-omo-profiles.sh
git commit -m "fix: replace GNU-specific grep with POSIX sed in test-omo-profiles.sh"
```

---

## Task 3: Verification

- [x] **Step 1: Verify `global-rules/AGENTS.global.md` is NOT corrupted**

1. Ensure `global-rules/AGENTS.global.md` has been restored to its original state (with headers and workflow sections).
2. Run: `bash _scripts/sync_agents.sh`
3. Run: `git diff global-rules/AGENTS.global.md`
4. Expected: Changes should only occur BETWEEN `<!-- SKILLPORT_START -->` and `<!-- SKILLPORT_END -->`. No headers or other sections should be removed.

- [x] **Step 2: Run `_scripts/test-omo-profiles.sh`**

Run: `bash _scripts/test-omo-profiles.sh`
Expected: PASS all tests.
