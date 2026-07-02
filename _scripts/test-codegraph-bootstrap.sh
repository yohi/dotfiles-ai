#!/usr/bin/env bash
set -euo pipefail

# Regression test for _scripts/codegraph-bootstrap.sh.
# Verifies idempotent init, partial-init cleanup, and macOS flock fallback.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

mkdir -p "$WORKDIR/bin" "$WORKDIR/project/_scripts"
ln -sf "$REPO_ROOT/_scripts/codegraph-bootstrap.sh" \
    "$WORKDIR/project/_scripts/codegraph-bootstrap.sh"

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

cd "$WORKDIR/project"
export PATH="$WORKDIR/bin:$PATH"
export CODEGRAPH_LOG_FILE="$WORKDIR/codegraph.log"

# ---- First run: bootstrap and serve ----
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
[ -d "$WORKDIR/project/.codegraph" ] || fail ".codegraph was not created"
grep -q 'codegraph init' "$WORKDIR/stderr" || fail "init was not attempted"
grep -q 'codegraph serve --mcp' "$WORKDIR/stderr" || fail "server was not started"
grep -q '^codegraph init$' "$WORKDIR/codegraph.log" || fail "init was not logged"
grep -q '^codegraph serve --mcp$' "$WORKDIR/codegraph.log" || fail "serve was not logged"

# ---- Second run: idempotency ----
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr"
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
rm -rf "$WORKDIR/project/.codegraph"
! bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected bootstrap to fail"
[ -d "$WORKDIR/project/.codegraph" ] && fail "partial .codegraph directory was not removed"

# ---- macOS fallback: no flock in PATH ----
mkdir -p "$WORKDIR/noflock/bin"
ln -sf "$(command -v bash)" "$WORKDIR/noflock/bin/bash"
ln -sf /bin/rm "$WORKDIR/noflock/bin/rm"
ln -sf /bin/mkdir "$WORKDIR/noflock/bin/mkdir"
ln -sf /usr/bin/dirname "$WORKDIR/noflock/bin/dirname"
ln -sf /bin/pwd "$WORKDIR/noflock/bin/pwd"
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
rm -rf "$WORKDIR/project/.codegraph"
rm -f "$WORKDIR/stdout" "$WORKDIR/stderr"
PATH="$WORKDIR/noflock/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"
grep -q 'flock not found' "$WORKDIR/stderr" || fail "macOS fallback warning was not emitted"
[ -d "$WORKDIR/project/.codegraph" ] || fail ".codegraph was not created under macOS fallback"
grep -q 'codegraph serve fallback serve --mcp' "$WORKDIR/stderr" || fail "server was not started under macOS fallback"

printf 'PASS\n'
