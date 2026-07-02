# CodeGraph Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CodeGraph auto-initialize `.codegraph/` on first use through the existing APM SSOT so OpenCode, Claude Code, and other generated clients share the same behavior.

**Architecture:** Keep `apm.yml` as the source of truth, but change the `codegraph` MCP entry to launch a small repository-local bootstrap wrapper instead of invoking `codegraph serve --mcp` directly. The wrapper resolves the repository root from its own location, changes into that directory, checks for `.codegraph/`, runs `codegraph init` only when the directory is missing, then `exec`s `codegraph "$@"` so the existing `serve --mcp` arguments continue to flow through unchanged. This keeps the initialization policy centralized and avoids client-specific logic.

**Tech Stack:** Bash, APM-generated MCP config, CodeGraph CLI, shell-based verification

---

## Scope and invariants

Required invariants after implementation:

1. `apm.yml` remains the SSOT for the `codegraph` MCP entry.
2. The bootstrap wrapper creates no `.codegraph/` directory when one already exists.
3. The wrapper never attempts interactive setup in a non-TTY MCP launch path.
4. The final MCP process remains `codegraph serve --mcp` so client behavior stays unchanged after bootstrap.
5. The change must work for every APM-generated client that uses the same `codegraph` entry.

## File structure

- Modify `_scripts/codegraph-bootstrap.sh`: new bootstrap wrapper that resolves repo root, initializes `.codegraph/` once, and then starts the MCP server.
- Modify `apm.yml`: point the `codegraph` MCP `command` at the new bootstrap wrapper instead of `codegraph` directly.
- Modify `opencode/opencode.jsonc`: regenerate or mirror the generated MCP entry so it references the bootstrap wrapper.
- Modify any other generated MCP config that APM emits for the current workspace, if regeneration updates them.
- Create `_scripts/test-codegraph-bootstrap.sh`: verify the wrapper is idempotent and forwards to `codegraph serve --mcp` after initialization.
- Modify `.gitignore`: add `.codegraph-bootstrap.lock`, the transient `flock` guard file created by the wrapper.

### Task 1: Add a failing bootstrap test

**Files:**
- Create: `_scripts/test-codegraph-bootstrap.sh`

- [ ] **Step 1: Write the failing test**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

mkdir -p "$WORKDIR/bin" "$WORKDIR/project/_scripts"
ln -sf "$REPO_ROOT/_scripts/codegraph-bootstrap.sh" "$WORKDIR/project/_scripts/codegraph-bootstrap.sh"

# Realistic codegraph stub that logs all invocations
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${CODEGRAPH_LOG_FILE:-}"

case "${1:-}" in
  init)
    mkdir -p .codegraph
    printf 'codegraph init\n' >&2
    printf 'codegraph init\n' >>"$LOG_FILE"
    ;;
  serve)
    printf 'codegraph %s\n' "$*" >&2
    printf 'codegraph %s\n' "$*" >>"$LOG_FILE"
    ;;
  *)
    printf 'unexpected codegraph command: %s\n' "$*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/bin/codegraph"

# ---- First run: bootstrap and serve ----
cd "$WORKDIR/project"
export PATH="$WORKDIR/bin:$PATH"
export CODEGRAPH_LOG_FILE="$WORKDIR/codegraph.log"

bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"

[ -d "$WORKDIR/project/.codegraph" ] || fail ".codegraph was not created"
grep -q 'codegraph init' "$WORKDIR/stderr" || fail "init was not attempted"
grep -q 'codegraph serve --mcp' "$WORKDIR/stderr" || fail "server was not started"
grep -q '^codegraph init$' "$WORKDIR/codegraph.log" || fail "init was not logged"
grep -q '^codegraph serve --mcp$' "$WORKDIR/codegraph.log" || fail "serve was not logged"

# ---- Second run: idempotency check ----
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr"
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >/dev/null 2>"$WORKDIR/stderr"

# init must NOT be called when .codegraph/ already exists
grep -q 'codegraph init' "$WORKDIR/stderr" && fail "init was called on second run"
grep -q 'codegraph serve --mcp' "$WORKDIR/stderr" || fail "server was not started on second run"

printf 'PASS\n'
```
Run: `bash _scripts/test-codegraph-bootstrap.sh`

### Task 2: Implement the bootstrap wrapper

**Files:**

Expected: fail because `_scripts/codegraph-bootstrap.sh` does not exist yet.
- Create: `_scripts/codegraph-bootstrap.sh`

- [ ] **Step 1: Write the minimal wrapper**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Atomic guard: prevents a TOCTOU race when multiple MCP clients
# (OpenCode, Claude Code, ...) launch this wrapper concurrently on a
# fresh checkout and would otherwise both observe .codegraph as missing.
LOCK_FILE="$REPO_ROOT/.codegraph-bootstrap.lock"
exec 200>"$LOCK_FILE"
flock 200

if [ ! -d ".codegraph" ]; then
    codegraph init
fi

flock -u 200
exec 200>&-

exec codegraph "$@"
```

- [ ] **Step 2: Make the wrapper executable**

Run: `chmod +x _scripts/codegraph-bootstrap.sh _scripts/test-codegraph-bootstrap.sh`

- [ ] **Step 3: Run the test and verify it passes**

Run: `bash _scripts/test-codegraph-bootstrap.sh`
Expected: PASS with `.codegraph/` created once and the server invocation observed.

### Task 3: Repoint the SSOT MCP entry

**Files:**
- Modify: `apm.yml`
- Modify: `opencode/opencode.jsonc` and any generated MCP config files produced by APM refresh

- [ ] **Step 1: Update the SSOT entry**

```yaml
- name: codegraph
  title: "CodeGraph MCP"
  registry: false
  transport: stdio
  command: "_scripts/codegraph-bootstrap.sh"
  args:
    - "serve"
    - "--mcp"
  enabled: true
```

- [ ] **Step 2: Regenerate generated MCP config**

Run: `make sync-agents` (which runs `apm install` → `apm compile` and refreshes all generated configs).
Expected: `opencode/opencode.jsonc` and any sibling generated MCP configs now reference the bootstrap wrapper.

- [ ] **Step 3: Verify the generated config**

Run: `grep -R -n --exclude-dir=.git --include='*.json' --include='*.jsonc' "codegraph-bootstrap.sh" .`
Expected: all generated `codegraph` entries reference the wrapper, and no generated config still points to `codegraph serve --mcp` directly.

**cwd invariant:** Check that the generated MCP entry includes an explicit `cwd` field pointing to the repo root (e.g., `.` or `$PWD` at generation time). If absent, the wrapper's own `cd` logic is the safety net, but explicit `cwd` prevents launch-directory mismatch across clients. If the generated config lacks `cwd`, add a line to the YAML entry before regeneration.

### Task 4: End-to-end verification

**Files:**
- No new files
- [ ] **Step 1: Run the bootstrap test again**

Run: `bash _scripts/test-codegraph-bootstrap.sh`
Expected: PASS (both first-run bootstrap and second-run idempotency).

- [ ] **Step 2: Verify MCP startup through the generated config**

Run the existing OpenCode or Claude Code startup path that consumes APM-generated MCP config, then confirm `codegraph` is listed as connected and the repo-specific `.codegraph/` directory exists.
Expected: the first launch bootstraps once, later launches skip `init`.
