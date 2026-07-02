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
