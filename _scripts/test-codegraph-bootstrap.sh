#!/usr/bin/env bash
set -euo pipefail

# Regression test for _scripts/codegraph-bootstrap.sh.
# Verifies idempotent init, partial-init cleanup, macOS flock fallback,
# status/dry-run modes, argument validation, logging, stdin isolation, and
# cross-platform timeout handling.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

reset_bootstrap_state() {
    rm -f "$WORKDIR/stdout" "$WORKDIR/stderr" "$WORKDIR/codegraph.log" \
        "$WORKDIR/stdout1" "$WORKDIR/stderr1" "$WORKDIR/stdout2" "$WORKDIR/stderr2"
    rm -f "$WORKDIR/project/.codegraph-bootstrap.log"
    rm -f "$WORKDIR/project/.codegraph-bootstrap.lock"
    rm -f "$WORKDIR/init-count"
}

reset_codegraph_dir() {
    rm -rf "$WORKDIR/project/.codegraph"
}

install_default_codegraph_stub() {
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
}

mkdir -p "$WORKDIR/bin" "$WORKDIR/project/_scripts"
ln -sf "$REPO_ROOT/_scripts/codegraph-bootstrap.sh" \
    "$WORKDIR/project/_scripts/codegraph-bootstrap.sh"

install_default_codegraph_stub

cd "$WORKDIR/project"
export PATH="$WORKDIR/bin:$PATH"
export CODEGRAPH_LOG_FILE="$WORKDIR/codegraph.log"

# ---- First run: bootstrap and serve ----
reset_codegraph_dir
reset_bootstrap_state
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
[ -d "$WORKDIR/project/.codegraph" ] || fail ".codegraph was not created"
grep -q 'codegraph init' "$WORKDIR/stderr" || fail "init was not attempted"
grep -q 'codegraph serve --mcp' "$WORKDIR/stderr" || fail "server was not started"
grep -q '^codegraph init$' "$WORKDIR/codegraph.log" || fail "init was not logged"
grep -q '^codegraph serve --mcp$' "$WORKDIR/codegraph.log" || fail "serve was not logged"

# ---- Second run: idempotency ----
# Keep .codegraph/ from the first run to verify init is skipped.
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr" "$WORKDIR/stdout" \
    "$WORKDIR/project/.codegraph-bootstrap.log"
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
grep -q 'codegraph init' "$WORKDIR/stderr" && fail "init was called on second run"
grep -q 'codegraph serve --mcp' "$WORKDIR/stderr" || fail "server was not started on second run"

# ---- Partial init failure cleanup ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p .codegraph/partial
exit 1
EOF
chmod +x "$WORKDIR/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
! bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected bootstrap to fail"
[ -d "$WORKDIR/project/.codegraph" ] && fail "partial .codegraph directory was not removed"
[ -f "$WORKDIR/project/.codegraph-bootstrap.log" ] || fail "bootstrap log should survive cleanup"
grep -q 'init failed; removing partially-created .codegraph/' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "cleanup was not logged"

# ---- Logging must not create .codegraph before init ----
install_default_codegraph_stub
reset_codegraph_dir
reset_bootstrap_state
PATH="/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected --dry-run to succeed"
[ -d "$WORKDIR/project/.codegraph" ] && fail "logging/dry-run must not create .codegraph"
[ -f "$WORKDIR/project/.codegraph-bootstrap.log" ] || fail "bootstrap log should be created"

# ---- --status when codegraph is missing ----
reset_codegraph_dir
reset_bootstrap_state
PATH="/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --status \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" && fail "status must report missing when codegraph is not installed"
grep -q 'CodeGraph CLI: missing' "$WORKDIR/stdout" || fail "missing CLI was not reported"
grep -q '.codegraph/ dir: missing' "$WORKDIR/stdout" || fail "missing dir was not reported"
grep -q 'bootstrap lock: missing' "$WORKDIR/stdout" || fail "missing lock was not reported"

# ---- --status when codegraph is installed ----
reset_codegraph_dir
reset_bootstrap_state
mkdir -p "$WORKDIR/project/.codegraph"
PATH="$WORKDIR/bin:/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --status \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "status must report installed when codegraph is present"
grep -q 'CodeGraph CLI: installed' "$WORKDIR/stdout" || fail "installed CLI was not reported"
grep -q '.codegraph/ dir: present' "$WORKDIR/stdout" || fail "present dir was not reported"
# ---- --dry-run when .codegraph exists ----
reset_codegraph_dir
reset_bootstrap_state
mkdir -p "$WORKDIR/project/.codegraph"
PATH="/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected --dry-run to succeed with existing .codegraph"
grep -q 'dry-run: skip codegraph init' "$WORKDIR/stdout" || fail "dry-run did not skip init"
grep -q 'dry-run: exec codegraph serve --mcp' "$WORKDIR/stdout" || fail "dry-run did not report exec"

# ---- --dry-run when .codegraph is missing ----
reset_codegraph_dir
reset_bootstrap_state
PATH="/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected --dry-run to succeed with missing .codegraph"
grep -q 'dry-run: codegraph init' "$WORKDIR/stdout" || fail "dry-run did not report init"
grep -q 'dry-run: exec codegraph serve --mcp' "$WORKDIR/stdout" || fail "dry-run did not report exec"

# ---- Invalid arguments are rejected ----
reset_codegraph_dir
reset_bootstrap_state
for bad_args in '' 'serve' 'serve --foo' 'serve --mcp extra' '--status extra' '--dry-run' '--dry-run serve' 'unknown'; do
    # shellcheck disable=SC2086
    bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" $bad_args \
        >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" && fail "expected failure for args: '$bad_args'"
    [ -d "$WORKDIR/project/.codegraph" ] && fail "argument error must not create .codegraph for: '$bad_args'"
done

# ---- GNU timeout path ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .codegraph/partial
    printf 'codegraph init slow\n' >&2
    sleep 10
    ;;
  serve)
    printf 'codegraph %s\n' "$*" >&2
    ;;
  *)
    printf 'unexpected codegraph command: %s\n' "$*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
install_default_codegraph_stub

# ---- macOS fallback: no flock in PATH ----
mkdir -p "$WORKDIR/noflock/bin"
ln -sf "$(command -v bash)" "$WORKDIR/noflock/bin/bash"
ln -sf "$(command -v rm)" "$WORKDIR/noflock/bin/rm"
ln -sf "$(command -v mkdir)" "$WORKDIR/noflock/bin/mkdir"
ln -sf "$(command -v dirname)" "$WORKDIR/noflock/bin/dirname" 2>/dev/null || true
ln -sf "$(command -v pwd)" "$WORKDIR/noflock/bin/pwd" 2>/dev/null || true
ln -sf "$(command -v date)" "$WORKDIR/noflock/bin/date"
ln -sf "$(command -v sleep)" "$WORKDIR/noflock/bin/sleep"
cat >"$WORKDIR/noflock/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .codegraph
    printf 'codegraph init fallback\n' >&2
    ;;
  serve)
    printf 'codegraph serve fallback %s\n' "$*" >&2
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/noflock/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
PATH="$WORKDIR/noflock/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
grep -q 'flock not found' "$WORKDIR/stderr" || fail "macOS fallback warning was not emitted"
[ -d "$WORKDIR/project/.codegraph" ] || fail ".codegraph was not created under macOS fallback"
grep -q 'codegraph serve fallback serve --mcp' "$WORKDIR/stderr" || fail "server was not started under macOS fallback"

# ---- Stdin isolation: init must not consume MCP bytes ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    if IFS= read -r line; then
      printf 'init consumed stdin: %s\n' "$line" >&2
      exit 1
    fi
    mkdir -p .codegraph
    ;;
  serve)
    IFS= read -r line
    printf 'serve received stdin: %s\n' "$line" >&2
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
printf 'mcp-byte\n' | bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
grep -q 'init consumed stdin' "$WORKDIR/stderr" && fail "init consumed MCP stdin"
grep -q 'serve received stdin: mcp-byte' "$WORKDIR/stderr" || fail "serve did not receive MCP stdin"

# ---- Concurrent launch: init runs only once ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
LOG_FILE="${CODEGRAPH_LOG_FILE:-}"
INIT_COUNT_FILE="${INIT_COUNT_FILE:-/tmp/codegraph-init-count}"
case "${1:-}" in
  init)
    mkdir -p .codegraph
    sleep 1
    flock "$INIT_COUNT_FILE" -c 'x=$(cat "$INIT_COUNT_FILE" 2>/dev/null || echo 0); echo $((x + 1)) > "$INIT_COUNT_FILE"'
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
reset_codegraph_dir
reset_bootstrap_state
export INIT_COUNT_FILE="$WORKDIR/init-count"
echo 0 > "$INIT_COUNT_FILE"

bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout1" 2>"$WORKDIR/stderr1" &
PID1=$!
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout2" 2>"$WORKDIR/stderr2" &
PID2=$!
wait "$PID1"
RC1=$?
wait "$PID2"
RC2=$?
[ "$RC1" -eq 0 ] || fail "first concurrent bootstrap exited with $RC1"
[ "$RC2" -eq 0 ] || fail "second concurrent bootstrap exited with $RC2"

INIT_COUNT="$(cat "$INIT_COUNT_FILE")"
[ "$INIT_COUNT" -eq 1 ] || fail "codegraph init ran $INIT_COUNT times, expected 1"

printf 'PASS\n'
