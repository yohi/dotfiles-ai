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
