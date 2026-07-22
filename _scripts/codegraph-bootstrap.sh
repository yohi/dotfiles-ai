#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
LOCK_FILE="$REPO_ROOT/.codegraph-bootstrap.lock"

CODEGRAPH_INIT_TIMEOUT="${CODEGRAPH_INIT_TIMEOUT:-300}"
CODEGRAPH_LOG_LEVEL="${CODEGRAPH_LOG_LEVEL:-info}"
# Place the bootstrap log outside .codegraph/ so that logging does not alter
# the initialization state and so diagnostics survive partial-init cleanup.
CODEGRAPH_BOOTSTRAP_LOG="${CODEGRAPH_BOOTSTRAP_LOG:-$REPO_ROOT/.codegraph-bootstrap.log}"

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
_log_level_rank() {
    case "${1:-}" in
        silent) echo 0 ;;
        error)  echo 1 ;;
        warn)   echo 2 ;;
        info)   echo 3 ;;
        debug)  echo 4 ;;
        *)      echo 3 ;;
    esac
}

_log() {
    local level="$1"
    shift
    local message="$*"
    local current
    current="$(_log_level_rank "$CODEGRAPH_LOG_LEVEL")"
    local target
    target="$(_log_level_rank "$level")"

    if [ "$target" -gt "$current" ]; then
        return 0
    fi

    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local line="[${timestamp}] [${level^^}] ${message}"

    # stderr output is reserved for human-readable diagnostics only when
    # the MCP server has not yet taken over stdout/stdin. After exec, this
    # function is no longer reachable.
    if [ "$level" = "error" ] || [ "$level" = "warn" ]; then
        printf '%s\n' "$line" >&2
    fi

    if [ "$CODEGRAPH_LOG_LEVEL" != "silent" ]; then
        printf '%s\n' "$line" >>"$CODEGRAPH_BOOTSTRAP_LOG"
    fi
}

# --------------------------------------------------------------------------
# Usage & mode detection
# --------------------------------------------------------------------------
_usage() {
    printf 'Usage: codegraph-bootstrap.sh [--status | --dry-run serve --mcp | serve --mcp]\n' >&2
}

_is_status_mode() {
    [ "$#" -eq 1 ] && [ "${1:-}" = "--status" ]
}

_is_dry_run_mode() {
    [ "$#" -eq 3 ] && [ "${1:-}" = "--dry-run" ] && [ "${2:-}" = "serve" ] && [ "${3:-}" = "--mcp" ]
}

_is_serve_mcp_mode() {
    [ "$#" -eq 2 ] && [ "${1:-}" = "serve" ] && [ "${2:-}" = "--mcp" ]
}

# --------------------------------------------------------------------------
# Status / dry-run (must work even when codegraph is not installed)
# --------------------------------------------------------------------------
_show_status() {
    local codegraph_ok="missing"
    local codegraph_dir="missing"
    local lock_file="missing"

    if command -v codegraph >/dev/null 2>&1; then
        codegraph_ok="installed"
    fi

    if [ -d "$REPO_ROOT/.codegraph" ]; then
        codegraph_dir="present"
    fi

    if [ -f "$LOCK_FILE" ]; then
        lock_file="present"
    fi

    printf 'CodeGraph CLI: %s\n' "$codegraph_ok"
    printf '.codegraph/ dir: %s\n' "$codegraph_dir"
    printf 'bootstrap lock: %s\n' "$lock_file"

    if [ "$codegraph_ok" = "installed" ] && [ "$codegraph_dir" = "present" ]; then
        exit 0
    else
        exit 1
    fi
}

_show_dry_run() {
    shift # consume --dry-run
    _log info "dry-run: would run codegraph init if .codegraph/ is missing, then exec codegraph serve --mcp"
    if [ ! -d "$REPO_ROOT/.codegraph" ]; then
        printf 'dry-run: codegraph init (because .codegraph/ is missing)\n'
    else
        printf 'dry-run: skip codegraph init (because .codegraph/ exists)\n'
    fi
    printf 'dry-run: exec codegraph serve --mcp\n'
    exit 0
}

# --------------------------------------------------------------------------
# Normal-mode prerequisites
# --------------------------------------------------------------------------
_ensure_codegraph_installed() {
    if ! command -v codegraph >/dev/null 2>&1; then
        _log error "codegraph command not found. Install with: npm i -g @colbymchenry/codegraph"
        exit 1
    fi
}

# --------------------------------------------------------------------------
# Locking
# --------------------------------------------------------------------------
_LOCK_TYPE=""

_acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        exec 200>"$LOCK_FILE"
        flock 200
        _LOCK_TYPE=flock
    else
        _log warn "flock not found; running without lock (macOS fallback)"
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

# --------------------------------------------------------------------------
# Init with cross-platform timeout
# --------------------------------------------------------------------------
_run_init_with_timeout() {
    local timeout_cmd=""

    if command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout"
    fi

    if [ -n "$timeout_cmd" ]; then
        "$timeout_cmd" "$CODEGRAPH_INIT_TIMEOUT" codegraph init < /dev/null
        return $?
    fi

    # Bash watchdog fallback for macOS and other systems without timeout/gtimeout.
    # Launch codegraph init in the background, then wait for it with a sleep-based
    # watchdog. If the watchdog fires, kill init and normalize the exit code to 124.
    local init_pid
    local watchdog_pid
    local init_rc=0

    codegraph init < /dev/null &
    init_pid=$!

    (
        sleep "$CODEGRAPH_INIT_TIMEOUT"
        kill -TERM "$init_pid" 2>/dev/null || true
    ) &
    watchdog_pid=$!

    if wait "$init_pid"; then
        init_rc=0
    else
        init_rc=$?
    fi

    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    if [ "$init_rc" -eq 143 ] || [ "$init_rc" -eq 129 ]; then
        # TERM/KILL signals normalize to the timeout(1) timeout exit code.
        init_rc=124
    fi

    return "$init_rc"
}

# Initialize CodeGraph once, cleaning up a partially-created .codegraph/
# directory if init fails.  stdin is redirected to /dev/null so that init
# cannot consume MCP protocol bytes from the wrapper's stdio transport.
_initialize_once() {
    local existed_before=0
    if [ -d ".codegraph" ]; then
        existed_before=1
        _log info ".codegraph/ already exists; skipping codegraph init"
    fi

    _cleanup_partial_init() {
        if [ "$existed_before" -eq 0 ] && [ -d ".codegraph" ]; then
            _log warn "init failed; removing partially-created .codegraph/"
            rm -rf ".codegraph"
        fi
    }
    trap '_cleanup_partial_init' ERR

    if [ ! -d ".codegraph" ]; then
        _log info "running codegraph init (timeout: ${CODEGRAPH_INIT_TIMEOUT}s)"
        if _run_init_with_timeout; then
            _log info "codegraph init completed"
        else
            local rc=$?
            _cleanup_partial_init
            if [ "$rc" -eq 124 ]; then
                _log error "codegraph init timed out after ${CODEGRAPH_INIT_TIMEOUT}s"
            else
                _log error "codegraph init failed with exit code $rc"
            fi
            return "$rc"
        fi
    fi

    trap - ERR
}

# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
_main() {
    if _is_status_mode "$@"; then
        _show_status
    fi

    if _is_dry_run_mode "$@"; then
        _show_dry_run "$@"
    fi

    if ! _is_serve_mcp_mode "$@"; then
        _log error "invalid arguments: $*. Expected '--status', '--dry-run serve --mcp', or 'serve --mcp'"
        _usage
        exit 2
    fi

    _ensure_codegraph_installed
    _acquire_lock
    _initialize_once
    _release_lock

    _log info "starting codegraph serve --mcp"
    exec codegraph serve --mcp
}

_main "$@"
