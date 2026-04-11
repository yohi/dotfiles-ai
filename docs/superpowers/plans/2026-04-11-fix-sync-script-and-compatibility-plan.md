# Fix Sync Script and Compatibility Implementation Plan (Completed)

Status: ✅ Implemented (Commits: abf29e2, 4b6556b, 450fe85)

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
<<<<
run_skillport_doc() {
    local output_file="$1"

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport doc --mode mcp --output "$output_file" --force || {
            echo "Error: skillport doc failed for '$output_file'." >&2
            exit 1
        }
        return 0
    fi

    if command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport doc --mode mcp --output "$output_file" --force || {
            echo "Error: uvx skillport doc failed for '$output_file'." >&2
            exit 1
        }
        return 0
    fi

    echo "Error: 'skillport' command not found. Please install it." >&2
    exit 1
}
====
run_skillport_doc() {
    local output_file="$1"
    local tmp_file
    tmp_file=$(mktemp)

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: skillport doc failed." >&2; rm "$tmp_file"; exit 1
        }
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: uvx skillport doc failed." >&2; rm "$tmp_file"; exit 1
        }
    else
        echo "Error: 'skillport' command not found." >&2; rm "$tmp_file"; exit 1
    fi

    if [[ -f "$output_file" ]] && grep -q "<!-- SKILLPORT_START -->" "$output_file" && grep -q "<!-- SKILLPORT_END -->" "$output_file"; then
        echo "Updating SkillPort section in existing ${output_file}..."
        # Extract the content between tags from the tmp file and replace it in output_file
        perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi
    rm "$tmp_file"
}
>>>>
```

- [x] **Step 2: Modify output file validation loop**

This is the original Task 1 fix. Ensure it is implemented correctly.

```bash
<<<<
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
====
# (Keep current loop structure as per Step 1, ensuring the hierarchical check is applied)
# If the previous implementer already did this, just verify it.
>>>>
```

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

- [x] **Step 1: Verify `global-rules/AGENTS.global.md` is NOT corrupted**

1. Ensure `global-rules/AGENTS.global.md` has been restored to its original state (with headers and workflow sections).
2. Run: `bash _scripts/sync_agents.sh`
3. Run: `git diff global-rules/AGENTS.global.md`
4. Expected: Changes should only occur BETWEEN `<!-- SKILLPORT_START -->` and `<!-- SKILLPORT_END -->`. No headers or other sections should be removed.

- [x] **Step 2: Run `_scripts/test-omo-profiles.sh`**

Run: `bash _scripts/test-omo-profiles.sh`
Expected: PASS all tests.
