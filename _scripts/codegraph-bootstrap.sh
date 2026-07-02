#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Atomic guard: prevents a TOCTOU race when multiple MCP clients
# (OpenCode, Claude Code, ...) launch this wrapper concurrently on a
# fresh checkout and would otherwise both observe .codegraph as missing.
LOCK_FILE="$REPO_ROOT/.codegraph-bootstrap.lock"
_LOCK_TYPE=""

_acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        exec 200>"$LOCK_FILE"
        flock 200
        _LOCK_TYPE=flock
    else
        printf '[!] codegraph-bootstrap: flock not found; running without lock (macOS fallback)\n' >&2
        _LOCK_TYPE=none
    fi
}

_release_lock() {
    case "$_LOCK_TYPE" in
        flock)
            flock -u 200
            exec 200>&-
            ;;
        *) ;;
    esac
}

# Initialize CodeGraph once, cleaning up a partially-created .codegraph/
# directory if init fails.  stdin is redirected to /dev/null so that init
# cannot consume MCP protocol bytes from the wrapper's stdio transport.
_initialize_once() {
    local existed_before=0
    if [ -d ".codegraph" ]; then
        existed_before=1
    fi

    _cleanup_partial_init() {
        if [ "$existed_before" -eq 0 ] && [ -d ".codegraph" ]; then
            rm -rf ".codegraph"
        fi
    }
    trap '_cleanup_partial_init' ERR

    if [ ! -d ".codegraph" ]; then
        codegraph init < /dev/null
    fi

    trap - ERR
}

_acquire_lock
_initialize_once
_release_lock

exec codegraph "$@"
