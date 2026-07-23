#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
LOCK_FILE="$REPO_ROOT/.codegraph-bootstrap.lock"

CODEGRAPH_INIT_TIMEOUT="${CODEGRAPH_INIT_TIMEOUT:-300}"
CODEGRAPH_LOCK_TIMEOUT="${CODEGRAPH_LOCK_TIMEOUT:-30}"
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

    if [[ "$level" != "error" ]]; then
        if [[ "$target" -gt "$current" ]]; then
            return 0
        fi
    fi

    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local line="[${timestamp}] [$(case "$level" in error) echo ERROR ;; warn) echo WARN ;; info) echo INFO ;; debug) echo DEBUG ;; silent) echo SILENT ;; *) echo "$level" ;; esac)] ${message}"

    # stderr output is reserved for human-readable diagnostics only when
    # the MCP server has not yet taken over stdout/stdin. After exec, this
    # function is no longer reachable.
    if [[ "$level" == "error" ]] || [[ "$level" == "warn" ]]; then
        printf '%s\n' "$line" >&2
    fi

    if [[ "$CODEGRAPH_LOG_LEVEL" != "silent" ]] || [[ "$level" == "error" ]]; then
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
    [[ "$#" -eq 1 ]] && [[ "${1:-}" == "--status" ]]
}

_is_dry_run_mode() {
    [[ "$#" -eq 3 ]] && [[ "${1:-}" == "--dry-run" ]] && [[ "${2:-}" == "serve" ]] && [[ "${3:-}" == "--mcp" ]]
}

_is_serve_mcp_mode() {
    [[ "$#" -eq 2 ]] && [[ "${1:-}" == "serve" ]] && [[ "${2:-}" == "--mcp" ]]
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

    if [[ -d "$REPO_ROOT/.codegraph" ]]; then
        codegraph_dir="present"
    fi

    if [[ -f "$LOCK_FILE" ]]; then
        lock_file="present"
    fi

    printf 'CodeGraph CLI: %s\n' "$codegraph_ok"
    printf '.codegraph/ dir: %s\n' "$codegraph_dir"
    printf 'bootstrap lock: %s\n' "$lock_file"

    if [[ "$codegraph_ok" == "installed" ]] && [[ "$codegraph_dir" == "present" ]]; then
        exit 0
    else
        exit 1
    fi
}

_show_dry_run() {
    shift # consume --dry-run
    _log info "dry-run: would run codegraph init if .codegraph/ is missing, then exec codegraph serve --mcp"
    if [[ ! -d "$REPO_ROOT/.codegraph" ]]; then
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
_CURRENT_INIT_PID=""

_acquire_lock() {
    if ! command -v flock >/dev/null 2>&1; then
        _log warn "flock not found; running without lock (macOS fallback)"
        _LOCK_TYPE=none
        return 0
    fi

    if ! { exec 200>"$LOCK_FILE"; } 2>/dev/null; then
        _log warn "could not create lock file ${LOCK_FILE}; running without lock"
        _LOCK_TYPE=none
        return 0
    fi

    if flock -w "$CODEGRAPH_LOCK_TIMEOUT" 200; then
        _LOCK_TYPE=flock
    else
        _log warn "flock acquisition timed out after ${CODEGRAPH_LOCK_TIMEOUT}s; proceeding without lock"
        exec 200>&-
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

# Send SIGTERM (then SIGKILL after a grace period) to an entire process
# group. Used both by the init timeout watchdog and by the termination-
# signal handler so that an in-flight codegraph init never survives as
# an orphan.
_terminate_process_group() {
    local pgid="$1"
    if ! kill -TERM -"$pgid" 2>/dev/null; then
        # Target already gone; nothing to wait for or escalate to KILL.
        return 0
    fi
    sleep 2
    # Re-check the group is still present before escalating to KILL, since
    # the PGID could have been recycled by an unrelated process during the
    # sleep window.
    if kill -0 -"$pgid" 2>/dev/null; then
        kill -KILL -"$pgid" 2>/dev/null || true
    fi
}

# Handle SIGINT/SIGTERM delivered to the wrapper itself: stop any
# in-flight codegraph init, release the lock, and exit with the
# conventional 128+signal exit code.
_on_termination_signal() {
    local sig="$1"
    _log warn "received SIG${sig}; terminating and cleaning up"
    if [[ -n "$_CURRENT_INIT_PID" ]]; then
        _terminate_process_group "$_CURRENT_INIT_PID"
    fi
    _release_lock
    case "$sig" in
        INT)  exit 130 ;;
        *)    exit 143 ;;
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

    # Always launch codegraph init as a background job in its own process
    # group (via `set -m`) and `wait` on it, whether or not timeout/gtimeout
    # is available. This keeps a single code path for both cases and,
    # critically, lets a pending INT/TERM trap interrupt `wait` immediately
    # instead of being deferred until a synchronous foreground command exits.
    local init_pid
    local watchdog_pid=""
    local init_rc=0

    set -m
    # Block INT/TERM for the brief window between launching the background
    # job and recording its PID, so a termination signal can never arrive
    # while codegraph init is running but untracked by _CURRENT_INIT_PID.
    trap '' INT TERM
    if [[ -n "$timeout_cmd" ]]; then
        "$timeout_cmd" "$CODEGRAPH_INIT_TIMEOUT" codegraph init < /dev/null &
    else
        codegraph init < /dev/null &
    fi
    init_pid=$!
    set +m
    _CURRENT_INIT_PID="$init_pid"
    trap '_on_termination_signal INT' INT
    trap '_on_termination_signal TERM' TERM

    if [[ -z "$timeout_cmd" ]]; then
        # Bash watchdog fallback for macOS and other systems without
        # timeout/gtimeout: terminate the whole process group ourselves.
        (
            sleep "$CODEGRAPH_INIT_TIMEOUT"
            _terminate_process_group "$init_pid"
        ) &
        watchdog_pid=$!
    fi

    # Wait for init to finish (naturally, via the watchdog, or via a
    # termination signal delivered to the wrapper itself).
    if wait "$init_pid"; then
        init_rc=0
    else
        init_rc=$?
    fi
    _CURRENT_INIT_PID=""

    if [[ -n "$watchdog_pid" ]]; then
        kill "$watchdog_pid" 2>/dev/null || true
        wait "$watchdog_pid" 2>/dev/null || true
    fi

    if [[ "$init_rc" -eq 143 ]] || [[ "$init_rc" -eq 129 ]]; then
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
    if [[ -d ".codegraph" ]]; then
        existed_before=1
        _log info ".codegraph/ already exists; skipping codegraph init"
    fi

    _cleanup_partial_init() {
        if [[ "$existed_before" -eq 0 ]] && [[ -d ".codegraph" ]]; then
            _log warn "init failed; removing partially-created .codegraph/"
            rm -rf ".codegraph"
        fi
    }
    trap '_cleanup_partial_init' ERR

    if [[ ! -d ".codegraph" ]]; then
        _log info "running codegraph init (timeout: ${CODEGRAPH_INIT_TIMEOUT}s)"
        if _run_init_with_timeout; then
            _log info "codegraph init completed"
        else
            local rc=$?
            _cleanup_partial_init
            if [[ "$rc" -eq 124 ]]; then
                _log error "codegraph init timed out after ${CODEGRAPH_INIT_TIMEOUT}s"
            else
                _log error "codegraph init failed with exit code $rc"
            fi
            trap - ERR
            return "$rc"
        fi
    fi

    trap - ERR
}

# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
_main() {
    trap '_on_termination_signal INT' INT
    trap '_on_termination_signal TERM' TERM

    if _is_status_mode "$@"; then
        _show_status
    fi

    if _is_dry_run_mode "$@"; then
        _show_dry_run "$@"
    fi

    if ! _is_serve_mcp_mode "$@"; then
        _log error "invalid arguments: $*. Expected '--status', '--dry-run serve --mcp', or 'serve --mcp'"
        _usage
        exit 1
    fi

    _ensure_codegraph_installed
    _acquire_lock
    _initialize_once || {
        local rc=$?
        _release_lock
        return "$rc"
    }
    _release_lock

    _log info "starting codegraph serve --mcp"
    exec codegraph serve --mcp
}

_main "$@"
