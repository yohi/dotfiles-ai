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

_ensure_bash_version_supports_wait_n() {
    local major="${BASH_VERSINFO[0]}"
    local minor="${BASH_VERSINFO[1]}"

    if (( major < 4 || (major == 4 && minor < 3) )); then
        _log error "Bash ${BASH_VERSION} detected; Bash 4.3 or newer is required for 'wait -n'. Install a newer Bash (on macOS: brew install bash), then re-run explicitly, for example: \"\$(brew --prefix)/bin/bash\" _scripts/codegraph-bootstrap.sh serve --mcp"
        exit 1
    fi
}

# --------------------------------------------------------------------------
# Locking
# --------------------------------------------------------------------------
_LOCK_TYPE=""
_CURRENT_INIT_PID=""
# Set to 1 for the brief window between forking the codegraph-init
# background job and recording its PID in _CURRENT_INIT_PID. Lets
# _on_termination_signal distinguish "no init running at all" (exit
# immediately) from "init just launched but not yet tracked" (defer via
# _PENDING_TERM_SIG instead of losing the signal or acting on an unknown
# PID).
_INIT_LAUNCHING=0
# Holds a deferred signal name (INT/TERM) received while _INIT_LAUNCHING
# was set; replayed synchronously by _run_init_with_timeout once
# _CURRENT_INIT_PID is known. Empty means no signal is pending.
_PENDING_TERM_SIG=""

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
#
# Detecting whether the group is still alive after the grace period used
# to be a blind `sleep 2` followed by `kill -0 -"$pgid"`. That re-check is
# racy: if some other process reaped `pgid` and the OS recycled the PGID
# number for an unrelated process group during the sleep, `kill -0` (and
# worse, the KILL escalation) could target that unrelated group instead.
# Both current callers (_on_termination_signal and the no-timeout watchdog
# in _run_init_with_timeout) invoke this from the shell that is the direct
# parent of `pgid`'s job, so we race a `wait -n` against a grace-period
# timer job instead: `wait -n` reports real process completion via the
# kernel's actual wait() mechanism, which cannot be fooled by PID/PGID
# reuse the way a `kill -0` poll can. (Requires bash 4.3+ for `wait -n`;
# normal mode checks this requirement before initialization.)
_job_still_tracked() {
    # Query Bash's own child-job bookkeeping instead of the kernel PID
    # namespace. A reaped child's PID can be recycled for an unrelated process,
    # but only an explicitly waited job disappears from this table.
    local tracked_jobs
    tracked_jobs="$(jobs -p 2>/dev/null)"
    [[ $'\n'"$tracked_jobs"$'\n' == *$'\n'"$1"$'\n'* ]]
}

_terminate_process_group() {
    local pgid="$1"
    if ! kill -TERM -"$pgid" 2>/dev/null; then
        # Target already gone; nothing to wait for or escalate to KILL.
        return 0
    fi

    sleep 2 &
    local grace_pid=$!
    local rc=0
    if wait -n "$pgid" "$grace_pid"; then
        rc=0
    else
        rc=$?
    fi

    if _job_still_tracked "$grace_pid"; then
        # The grace timer is still tracked, so `wait -n` must have reaped
        # `pgid` itself: SIGTERM was enough. Cancel the now-unneeded timer.
        kill "$grace_pid" 2>/dev/null || true
        wait "$grace_pid" 2>/dev/null || true
        return "$rc"
    fi

    # The grace timer is the one `wait -n` reaped (it fired before `pgid`
    # exited): escalate to KILL.
    kill -KILL -"$pgid" 2>/dev/null || true
    if wait "$pgid" 2>/dev/null; then
        rc=0
    else
        rc=$?
    fi
    return "$rc"
}

# Handle SIGINT/SIGTERM delivered to the wrapper itself: stop any
# in-flight codegraph init, release the lock, and exit with the
# conventional 128+signal exit code.
#
# If codegraph init has been forked but _CURRENT_INIT_PID has not been
# recorded yet (see _INIT_LAUNCHING in _run_init_with_timeout), defer
# instead of exiting or silently dropping the signal: it is remembered in
# _PENDING_TERM_SIG and replayed once the PID is known, so a signal
# arriving in that narrow window is never lost.
_on_termination_signal() {
    local sig="$1"
    _log warn "received SIG${sig}; terminating and cleaning up"
    if [[ -n "$_CURRENT_INIT_PID" ]]; then
        # The return value is only used by the watchdog escalation branch
        # in _run_init_with_timeout; here we always fall through to
        # _release_lock/exit regardless, so discard it explicitly rather
        # than letting a non-zero exit-by-signal status trip `set -e`.
        _terminate_process_group "$_CURRENT_INIT_PID" || true
    elif [[ "$_INIT_LAUNCHING" -eq 1 ]]; then
        _PENDING_TERM_SIG="$sig"
        return 0
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
    local init_rc=0

    # The INT/TERM traps installed by _main stay active continuously through
    # the fork below -- they are deliberately never disabled with
    # `trap '' INT TERM`. Ignoring a signal (SIG_IGN) discards deliveries
    # instead of queuing them, so a signal arriving in the fork window would
    # be lost outright; worse, SIG_IGN is inherited across fork+exec, so the
    # codegraph/timeout child launched below would itself start with
    # INT/TERM ignored and could shrug off a later graceful `kill -TERM`
    # from _terminate_process_group. Instead, _INIT_LAUNCHING marks this
    # narrow pre-registration window so _on_termination_signal can defer
    # (see _PENDING_TERM_SIG) rather than dropping the signal or acting on
    # a PID it doesn't know yet.
    _INIT_LAUNCHING=1
    set -m
    if [[ -n "$timeout_cmd" ]]; then
        "$timeout_cmd" "$CODEGRAPH_INIT_TIMEOUT" codegraph init < /dev/null &
    else
        codegraph init < /dev/null &
    fi
    init_pid=$!

    local sleep_pid=""
    if [[ -z "$timeout_cmd" ]]; then
        # Bash watchdog fallback for macOS and other systems without
        # timeout/gtimeout: start the grace timer as a job of THIS shell
        # (the real parent of init_pid) instead of in a detached sibling
        # subshell. A sibling subshell cannot `wait` on init_pid, so it can
        # only poll with `kill -0 -"$pgid"` after its own sleep -- which is
        # racy if this shell's own `wait` below has already reaped init_pid
        # and the OS has recycled its PGID for an unrelated process group
        # in the meantime. Racing a same-shell `wait -n` against this timer
        # instead detects real completion via the kernel's wait()
        # mechanism, immune to that PID/PGID reuse window.
        sleep "$CODEGRAPH_INIT_TIMEOUT" &
        sleep_pid=$!
    fi
    set +m
    _CURRENT_INIT_PID="$init_pid"
    _INIT_LAUNCHING=0
    if [[ -n "$_PENDING_TERM_SIG" ]]; then
        # A termination signal arrived while the job was still launching
        # and was deferred by _on_termination_signal. Handle it now,
        # synchronously, with the PID known, so it is not lost.
        local pending_sig="$_PENDING_TERM_SIG"
        _PENDING_TERM_SIG=""
        _on_termination_signal "$pending_sig"
    fi

    if [[ -n "$sleep_pid" ]]; then
        # No external timeout command: race init_pid against the grace
        # timer in this shell so we can tell them apart via `wait -n`
        # instead of a blind sleep-then-kill-0 re-check.
        local wait_n_rc=0
        if wait -n "$init_pid" "$sleep_pid"; then
            wait_n_rc=0
        else
            wait_n_rc=$?
        fi
        if _job_still_tracked "$sleep_pid"; then
            # Timer still tracked: wait -n reaped init_pid itself, so its exit
            # status is already in wait_n_rc. Cancel the now-unneeded timer.
            kill "$sleep_pid" 2>/dev/null || true
            wait "$sleep_pid" 2>/dev/null || true
            init_rc="$wait_n_rc"
        else
            # Timer already reaped by wait -n: CODEGRAPH_INIT_TIMEOUT
            # elapsed before init_pid finished. Hand off to
            # _terminate_process_group, which owns the TERM->KILL
            # escalation and reaps init_pid itself.
            if _terminate_process_group "$init_pid"; then
                init_rc=0
            else
                init_rc=$?
            fi
        fi
    else
        if wait "$init_pid"; then
            init_rc=0
        else
            init_rc=$?
        fi
    fi
    _CURRENT_INIT_PID=""

    if [[ "$init_rc" -eq 143 ]] || [[ "$init_rc" -eq 129 ]] || [[ "$init_rc" -eq 137 ]]; then
        # TERM/KILL signals normalize to the timeout(1) timeout exit code.
        # 137 = 128+SIGKILL, produced when _terminate_process_group had to
        # escalate past SIGTERM; without normalizing it here, a
        # KILL-escalated timeout would be mis-reported by _initialize_once
        # as a generic failure instead of a timeout.
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
    _ensure_bash_version_supports_wait_n
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
