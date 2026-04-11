# Fix sync_agents.sh to Protect Content and Improve Validation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent sync_agents.sh from overwriting the entire file and improve directory/file validation logic.

**Architecture:** Use temporary files and Perl for surgical tag-based replacement. Implement a hierarchical validation loop for output files and their parent directories.

**Tech Stack:** Bash, Perl, SkillPort CLI

---

### Task 1: Update `run_skillport_doc` function

**Files:**
- Modify: `_scripts/sync_agents.sh`

- [ ] **Step 1: Update `run_skillport_doc` function**

Replace the existing `run_skillport_doc` function with the new implementation that uses a temporary file and Perl for tag-based replacement.

```bash
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
        perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi
    rm "$tmp_file"
}
```

- [ ] **Step 2: Commit changes**

```bash
git add _scripts/sync_agents.sh
git commit -m "fix(sync): protect existing content in sync_agents.sh using tags"
```

### Task 2: Update validation loop

**Files:**
- Modify: `_scripts/sync_agents.sh`

- [ ] **Step 1: Update the output file validation loop**

Replace the existing loop that iterates over `OUTPUT_FILES` with the improved version.

```bash
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
    normalize_locations "$output_file" "$REPO_ROOT"
    restore_external_skills_note "$output_file"
done
```

- [ ] **Step 2: Commit changes**

```bash
git add _scripts/sync_agents.sh
git commit -m "fix(sync): improve output file and directory validation"
```

### Task 3: Verification

- [ ] **Step 1: Run the sync script**

```bash
./_scripts/sync_agents.sh
```

- [ ] **Step 2: Verify the output file `global-rules/AGENTS.global.md`**

Check that the SkillPort section is updated but other content is preserved.
Check that the `<!-- NOTE: External skills ... -->` is still there.

- [ ] **Step 3: Commit any final fixes if necessary**
