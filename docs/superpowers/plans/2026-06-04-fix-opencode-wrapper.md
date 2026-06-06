# Fix opencode-wrapper.sh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `_scripts/opencode-wrapper.sh` to validate input environment variables and check for empty model configurations in generated output, preventing errors down the line. In addition, remove `exec` calls to prevent temporary directory leaks.

**Architecture:** Add checks in the subshell block of `_scripts/opencode-wrapper.sh`. Validate existence of `TEMPLATE` and `TMP_DIR` before template substitution. Validate that no `"model": ""` entries are generated. Remove `exec` keyword from opencode command execution so that the shell process remains active to trigger traps for cleanup.

**Tech Stack:** Bash

---

## Task 1: Check requirements and modify _scripts/opencode-wrapper.sh

**Files:**
- Modify: `_scripts/opencode-wrapper.sh`

- [ ] **Step 1: Modify the subshell block inside `_scripts/opencode-wrapper.sh`**

Modify the subshell block (lines 64-72) to check `TEMPLATE` and `TMP_DIR`, and inspect the generated JSONC config for empty model fields.

```bash
# 2. Generate the dynamic config
(
    if [ -z "$TEMPLATE" ] || [ -z "$TMP_DIR" ]; then
        echo "❌ Error: TEMPLATE or TMP_DIR is not set" >&2
        exit 1
    fi

    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    # Use envsubst to process the template
    envsubst < "$TEMPLATE" > "$TMP_DIR/oh-my-openagent.jsonc"

    # Check if any model configuration has an empty value (fail-fast)
    if grep -qE '"model"\s*:\s*""' "$TMP_DIR/oh-my-openagent.jsonc"; then
        echo "❌ Error: Empty model configuration detected in generated JSONC" >&2
        exit 1
    fi
)
```

- [ ] **Step 2: Remove the `exec` prefix from `exec opencode ...` execution commands**

Modify lines 82 and 85 to remove `exec` so the script doesn't replace the bash process and can successfully execute the `EXIT` trap.

```diff
-    exec opencode --port "$PORT" "$@"
+    opencode --port "$PORT" "$@"
```
and
```diff
-    exec opencode "$@"
+    opencode "$@"
```

## Task 2: Verify the syntax and run a dry-run / verification

- [ ] **Step 1: Check bash syntax using `bash -n`**

Run: `bash -n _scripts/opencode-wrapper.sh`
Expected: No output (success).

- [ ] **Step 2: Test validation with missing env variables**

Mock running the script where some environment variables are missing (e.g. mock missing `SISYPHUS_MODEL`) to verify the empty model check catches it.
Since we don't have openagent binary easily runnable in a full test, we can mock running a simplified wrapper check or execute the script with a mocked `opencode` command in the path, or direct manual validation of the subshell part.

Let's test this by running the script with a dummy mock `opencode` command so we don't actually run the agent, or inspect what happens.
We can mock `opencode` locally by putting a dummy command in PATH:
`PATH="./_scripts/test-bin:$PATH"` where `test-bin/opencode` just echoes "Mock opencode executed".

Run:
```bash
mkdir -p _scripts/test-bin
echo '#!/bin/sh' > _scripts/test-bin/opencode
echo 'echo "Mock opencode executed with args: $@"' >> _scripts/test-bin/opencode
chmod +x _scripts/test-bin/opencode
```
Then run the script under different conditions:
1. Valid profile (should run mock opencode and clean up TMP_DIR)
2. Invalid model variables (e.g. empty `SISYPHUS_MODEL`) - should print empty model config error, exit 1, and clean up TMP_DIR.

Verify `TMP_DIR` is cleaned up in both cases.

- [ ] **Step 3: Commit the changes**

```bash
git add _scripts/opencode-wrapper.sh
git commit -m "fix(opencode): prevent TMP_DIR leak and validate empty model substitution"
```
