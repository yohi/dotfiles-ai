#!/usr/bin/env bash
set -euo pipefail

# Regression test for _scripts/codegraph-bootstrap.sh.
# Verifies idempotent init, partial-init cleanup, macOS flock fallback,
# status/dry-run modes, argument validation, logging, stdin isolation, and
# cross-platform timeout handling.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
MINIMAL_PATH="/bin:/usr/bin"
ACTIVE_HELPER_PID=""
ACTIVE_WRAPPER_PID_FILE=""
ACTIVE_INIT_PID_FILE=""
ACTIVE_TIMER_PID_FILE=""

cleanup() {
    trap - EXIT INT TERM
    local pid_file pid
    if [[ -n "$ACTIVE_HELPER_PID" ]]; then
        kill "$ACTIVE_HELPER_PID" 2>/dev/null || true
        wait "$ACTIVE_HELPER_PID" 2>/dev/null || true
    fi
    for pid_file in "$ACTIVE_WRAPPER_PID_FILE" "$ACTIVE_INIT_PID_FILE" "$ACTIVE_TIMER_PID_FILE"; do
        if [[ -n "$pid_file" ]] && [[ -s "$pid_file" ]]; then
            pid="$(cat "$pid_file")"
            kill "$pid" 2>/dev/null || true
        fi
    done
    chmod -R u+rwx "$WORKDIR" 2>/dev/null
    rm -rf "$WORKDIR"
}
trap cleanup EXIT INT TERM

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
[[ -d "$WORKDIR/project/.codegraph" ]] || fail ".codegraph was not created"
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
[[ -d "$WORKDIR/project/.codegraph" ]] && fail "partial .codegraph directory was not removed"
[[ -f "$WORKDIR/project/.codegraph-bootstrap.log" ]] || fail "bootstrap log should survive cleanup"
grep -q 'init failed; removing partially-created .codegraph/' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "cleanup was not logged"

# ---- Logging must not create .codegraph before init ----
install_default_codegraph_stub
reset_codegraph_dir
reset_bootstrap_state
PATH="$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected --dry-run to succeed"
[[ -d "$WORKDIR/project/.codegraph" ]] && fail "logging/dry-run must not create .codegraph"
[[ -f "$WORKDIR/project/.codegraph-bootstrap.log" ]] || fail "bootstrap log should be created"

# ---- --status when codegraph is missing ----
reset_codegraph_dir
reset_bootstrap_state
PATH="$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --status \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" && fail "status must report missing when codegraph is not installed"
grep -q 'CodeGraph CLI: missing' "$WORKDIR/stdout" || fail "missing CLI was not reported"
grep -q '.codegraph/ dir: missing' "$WORKDIR/stdout" || fail "missing dir was not reported"
grep -q 'bootstrap lock: missing' "$WORKDIR/stdout" || fail "missing lock was not reported"

# ---- --status when codegraph is installed ----
reset_codegraph_dir
reset_bootstrap_state
mkdir -p "$WORKDIR/project/.codegraph"
PATH="$WORKDIR/bin:$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --status \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "status must report installed when codegraph is present"
grep -q 'CodeGraph CLI: installed' "$WORKDIR/stdout" || fail "installed CLI was not reported"
grep -q '.codegraph/ dir: present' "$WORKDIR/stdout" || fail "present dir was not reported"
# ---- --dry-run when .codegraph exists ----
reset_codegraph_dir
reset_bootstrap_state
mkdir -p "$WORKDIR/project/.codegraph"
PATH="$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected --dry-run to succeed with existing .codegraph"
grep -q 'dry-run: skip codegraph init' "$WORKDIR/stdout" || fail "dry-run did not skip init"
grep -q 'dry-run: exec codegraph serve --mcp' "$WORKDIR/stdout" || fail "dry-run did not report exec"

# ---- --dry-run when .codegraph is missing ----
reset_codegraph_dir
reset_bootstrap_state
PATH="$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" --dry-run serve --mcp \
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
    [[ -d "$WORKDIR/project/.codegraph" ]] && fail "argument error must not create .codegraph for: '$bad_args'"
done

# ---- Invalid arguments exit with code 1 (per design doc) ----
reset_codegraph_dir
reset_bootstrap_state
rc=0
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || rc=$?
[[ "$rc" -eq 1 ]] || fail "invalid arguments should exit 1, got $rc"

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
# Verify actual timeout path: short timeout, slow init stub.
CODEGRAPH_INIT_TIMEOUT=1 bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" && fail "expected bootstrap to time out"
[[ -d "$WORKDIR/project/.codegraph/partial" ]] && fail "partial .codegraph directory was not removed after timeout"
grep -q 'timed out' "$WORKDIR/project/.codegraph-bootstrap.log" || fail "timeout was not logged"
grep -q 'init failed; removing partially-created .codegraph/' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "cleanup was not logged after timeout"

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
[[ "$RC1" -eq 0 ]] || fail "first concurrent bootstrap exited with $RC1"
[[ "$RC2" -eq 0 ]] || fail "second concurrent bootstrap exited with $RC2"

INIT_COUNT="$(cat "$INIT_COUNT_FILE")"
[[ "$INIT_COUNT" -eq 1 ]] || fail "codegraph init ran $INIT_COUNT times, expected 1"

# ---- codegraph missing in serve --mcp mode: error message + exit code 1 ----
reset_codegraph_dir
reset_bootstrap_state
rc=0
PATH="$MINIMAL_PATH" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || rc=$?
[[ "$rc" -eq 1 ]] || fail "missing codegraph in serve mode should exit 1, got $rc"
grep -q 'codegraph command not found' "$WORKDIR/stderr" || fail "missing codegraph error message was not reported"
[[ -d "$WORKDIR/project/.codegraph" ]] && fail "missing codegraph must not create .codegraph"

# ---- Lock file cannot be created: warn and continue instead of crashing ----
install_default_codegraph_stub
reset_codegraph_dir
reset_bootstrap_state
LOCK_FAIL_LOG="$WORKDIR/lock-fail.log"
rm -f "$LOCK_FAIL_LOG"
chmod 555 "$WORKDIR/project"
if CODEGRAPH_BOOTSTRAP_LOG="$LOCK_FAIL_LOG" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"; then
    LOCK_FAIL_RC=0
else
    LOCK_FAIL_RC=$?
fi
chmod 755 "$WORKDIR/project"
grep -q 'codegraph-bootstrap\.sh:.*lock' "$WORKDIR/stderr" \
    && fail "raw bash permission error from the wrapper leaked to stderr instead of a warn log: $(cat "$WORKDIR/stderr")"
grep -q 'could not create lock file' "$LOCK_FAIL_LOG" || fail "lock creation failure was not logged as a warning"
grep -q 'running codegraph init' "$LOCK_FAIL_LOG" \
    || fail "processing did not continue past lock acquisition failure (rc=$LOCK_FAIL_RC)"

# ---- flock acquisition times out: warn and fall back to no-lock ----
install_default_codegraph_stub
reset_codegraph_dir
reset_bootstrap_state
LOCK_PATH="$WORKDIR/project/.codegraph-bootstrap.lock"
: >"$LOCK_PATH"
# Hold an exclusive flock on the lock file in a background subshell for
# longer than the wrapper's configured lock-acquisition timeout.
(
    exec 201>"$LOCK_PATH"
    flock 201
    sleep 5
) &
HOLDER_PID=$!
# Give the holder a moment to actually acquire the lock before racing it.
sleep 0.5
if CODEGRAPH_LOCK_TIMEOUT=1 bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"; then
    FLOCK_TIMEOUT_RC=0
else
    FLOCK_TIMEOUT_RC=$?
fi
kill "$HOLDER_PID" 2>/dev/null || true
wait "$HOLDER_PID" 2>/dev/null || true
[[ "$FLOCK_TIMEOUT_RC" -eq 0 ]] || fail "wrapper should still succeed by falling back to no-lock, got rc=$FLOCK_TIMEOUT_RC"
grep -q 'flock acquisition timed out' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "flock timeout fallback was not logged"
[[ -d "$WORKDIR/project/.codegraph" ]] || fail ".codegraph was not created after flock timeout fallback"

# ---- SIGTERM forwarding: in-flight codegraph init must not survive as an orphan ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .codegraph/partial
    sleep 47.131
    ;;
  serve)
    printf 'codegraph %s\n' "$*" >&2
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state

bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" &
WRAPPER_PID=$!
sleep 1
kill -TERM "$WRAPPER_PID"
if wait "$WRAPPER_PID"; then
    WRAPPER_RC=0
else
    WRAPPER_RC=$?
fi
[[ "$WRAPPER_RC" -eq 143 ]] || fail "wrapper should exit 143 after SIGTERM, got $WRAPPER_RC"
grep -q 'received SIGTERM' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "SIGTERM receipt was not logged"

sleep 1
if pgrep -f 'sleep 47\.131' >/dev/null 2>&1; then
    fail "codegraph init child (sleep 47.131) survived as an orphan after SIGTERM"
fi

# ---- Deferred SIGTERM replay logs receipt exactly once ----
# A DEBUG hook injected through BASH_ENV stops immediately before init_pid=$!,
# after the child has forked but before _CURRENT_INIT_PID can be published.
cat >"$WORKDIR/deferred-signal.bashenv" <<'EOF'
if [[ "$0" == */_scripts/codegraph-bootstrap.sh ]] \
    && [[ -n "${DEFER_SIGNAL_MARKER:-}" ]] \
    && [[ -n "${INIT_LAUNCH_MARKER:-}" ]]; then
    set -T
    _deliver_deferred_term_once() {
        local next_command="$1"
        if [[ "${_INIT_LAUNCHING:-0}" -eq 1 ]] \
            && [[ -z "${_CURRENT_INIT_PID:-}" ]] \
            && [[ ! -e "$DEFER_SIGNAL_MARKER" ]] \
            && [[ "$next_command" == 'init_pid=$!' ]]; then
            trap - DEBUG
            local marker_ready=0
            for _ in {1..500}; do
                if [[ -s "$INIT_LAUNCH_MARKER" ]]; then
                    marker_ready=1
                    break
                fi
                sleep 0.01
            done
            if [[ "$marker_ready" -ne 1 ]]; then
                printf 'timed out waiting for codegraph init launch marker: %s\n' \
                    "$INIT_LAUNCH_MARKER" >&2
                exit 1
            fi
            : >"$DEFER_SIGNAL_MARKER"
            kill -TERM "$$"
        fi
    }
    trap '_deliver_deferred_term_once "$BASH_COMMAND"' DEBUG
fi
EOF
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .codegraph/partial
    printf '%s\n' "$$" >"$INIT_LAUNCH_MARKER"
    exec /bin/sleep 47.132
    ;;
  serve)
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
DEFER_SIGNAL_MARKER="$WORKDIR/deferred-term.marker"
INIT_LAUNCH_MARKER="$WORKDIR/deferred-init.pid"
rm -f "$DEFER_SIGNAL_MARKER" "$INIT_LAUNCH_MARKER"
ACTIVE_INIT_PID_FILE="$INIT_LAUNCH_MARKER"
rc=0
BASH_ENV="$WORKDIR/deferred-signal.bashenv" \
    DEFER_SIGNAL_MARKER="$DEFER_SIGNAL_MARKER" \
    INIT_LAUNCH_MARKER="$INIT_LAUNCH_MARKER" \
    bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || rc=$?
[[ "$rc" -eq 143 ]] || fail "deferred SIGTERM replay should exit 143, got $rc"
[[ -f "$DEFER_SIGNAL_MARKER" ]] || fail "SIGTERM was not delivered in the init launch window"
[[ -s "$INIT_LAUNCH_MARKER" ]] || fail "codegraph init did not launch before deferred SIGTERM"
DEFERRED_INIT_PID="$(cat "$INIT_LAUNCH_MARKER")"
if kill -0 "$DEFERRED_INIT_PID" 2>/dev/null; then
    kill "$DEFERRED_INIT_PID" 2>/dev/null || true
    fail "codegraph init child survived deferred SIGTERM"
fi
ACTIVE_INIT_PID_FILE=""
TERM_LOG_COUNT="$(grep -c 'received SIGTERM; terminating and cleaning up' \
    "$WORKDIR/project/.codegraph-bootstrap.log" || true)"
[[ "$TERM_LOG_COUNT" -eq 1 ]] \
    || fail "deferred SIGTERM receipt should be logged once, got $TERM_LOG_COUNT events"

# ---- No-timeout signal handling terminates and reaps the fallback timer ----
mkdir -p "$WORKDIR/notimeout-signal/bin"
ln -sf "$(command -v bash)" "$WORKDIR/notimeout-signal/bin/bash"
ln -sf "$(command -v rm)" "$WORKDIR/notimeout-signal/bin/rm"
ln -sf "$(command -v mkdir)" "$WORKDIR/notimeout-signal/bin/mkdir"
ln -sf "$(command -v dirname)" "$WORKDIR/notimeout-signal/bin/dirname" 2>/dev/null || true
ln -sf "$(command -v pwd)" "$WORKDIR/notimeout-signal/bin/pwd" 2>/dev/null || true
ln -sf "$(command -v date)" "$WORKDIR/notimeout-signal/bin/date"
cat >"$WORKDIR/notimeout-signal/bin/sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "${FALLBACK_TIMER_DELAY:-}" ]]; then
    printf '%s\n' "$$" >"$FALLBACK_TIMER_PID_FILE"
fi
exec /bin/sleep "$@"
EOF
cat >"$WORKDIR/notimeout-signal/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .codegraph/partial
    printf '%s\n' "$$" >"$INIT_PID_FILE"
    exec /bin/sleep "$INIT_SLEEP_DELAY"
    ;;
  serve)
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/notimeout-signal/bin/sleep" "$WORKDIR/notimeout-signal/bin/codegraph"
cat >"$WORKDIR/wrapper-pid.bashenv" <<'EOF'
if [[ "$0" == */_scripts/codegraph-bootstrap.sh ]] && [[ -n "${WRAPPER_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" >"$WRAPPER_PID_FILE"
fi
EOF

FALLBACK_TIMER_FAILURES=""
run_fallback_signal_test() {
    local sig="$1"
    local expected_rc="$2"
    local wrapper_pid_file="$WORKDIR/wrapper-${sig}.pid"
    local init_pid_file="$WORKDIR/init-${sig}.pid"
    local timer_pid_file="$WORKDIR/timer-${sig}.pid"
    local signal_sent_file="$WORKDIR/signal-${sig}.sent"
    local init_sleep_delay timer_pid init_pid rc=0
    init_sleep_delay="47.13${expected_rc}"
    rm -f "$wrapper_pid_file" "$init_pid_file" "$timer_pid_file" "$signal_sent_file"
    reset_codegraph_dir
    reset_bootstrap_state

    ACTIVE_WRAPPER_PID_FILE="$wrapper_pid_file"
    ACTIVE_INIT_PID_FILE="$init_pid_file"
    ACTIVE_TIMER_PID_FILE="$timer_pid_file"
    (
        for _ in {1..200}; do
            if [[ -s "$wrapper_pid_file" ]] && [[ -s "$init_pid_file" ]] \
                && [[ -s "$timer_pid_file" ]]; then
                break
            fi
            sleep 0.05
        done
        [[ -s "$wrapper_pid_file" ]] && [[ -s "$init_pid_file" ]] \
            && [[ -s "$timer_pid_file" ]] || exit 1
        sleep 0.2
        kill "-$sig" "$(cat "$wrapper_pid_file")"
        : >"$signal_sent_file"
    ) &
    ACTIVE_HELPER_PID=$!

    if BASH_ENV="$WORKDIR/wrapper-pid.bashenv" \
        WRAPPER_PID_FILE="$wrapper_pid_file" \
        INIT_PID_FILE="$init_pid_file" \
        INIT_SLEEP_DELAY="$init_sleep_delay" \
        FALLBACK_TIMER_DELAY=37 \
        FALLBACK_TIMER_PID_FILE="$timer_pid_file" \
        CODEGRAPH_INIT_TIMEOUT=37 \
        PATH="$WORKDIR/notimeout-signal/bin" \
        bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
        >"$WORKDIR/stdout" 2>"$WORKDIR/stderr"; then
        rc=0
    else
        rc=$?
    fi
    wait "$ACTIVE_HELPER_PID" || fail "$sig signal helper did not observe all lifecycle PIDs"
    ACTIVE_HELPER_PID=""

    [[ -f "$signal_sent_file" ]] || fail "$sig was not sent to the wrapper"
    [[ "$rc" -eq "$expected_rc" ]] \
        || fail "wrapper should exit $expected_rc after SIG$sig, got $rc"
    timer_pid="$(cat "$timer_pid_file")"
    init_pid="$(cat "$init_pid_file")"
    if kill -0 "$init_pid" 2>/dev/null; then
        kill "$init_pid" 2>/dev/null || true
        fail "codegraph init child survived after SIG$sig"
    fi
    if kill -0 "$timer_pid" 2>/dev/null; then
        kill "$timer_pid" 2>/dev/null || true
        for _ in {1..100}; do
            kill -0 "$timer_pid" 2>/dev/null || break
            sleep 0.01
        done
        kill -KILL "$timer_pid" 2>/dev/null || true
        FALLBACK_TIMER_FAILURES="${FALLBACK_TIMER_FAILURES} SIG${sig}"
    fi

    ACTIVE_WRAPPER_PID_FILE=""
    ACTIVE_INIT_PID_FILE=""
    ACTIVE_TIMER_PID_FILE=""
}

run_fallback_signal_test TERM 143
run_fallback_signal_test INT 130
[[ -z "$FALLBACK_TIMER_FAILURES" ]] \
    || fail "fallback timer survived wrapper termination for:${FALLBACK_TIMER_FAILURES}"

# ---- KILL escalation normalizes to exit 124 (no timeout/gtimeout in PATH) ----
# Exercises the bash watchdog fallback's TERM->KILL escalation inside
# _terminate_process_group: codegraph init ignores SIGTERM, so after the
# 2-second grace period the wrapper must escalate to SIGKILL, and the
# resulting wait() status (137 = 128+SIGKILL) must be normalized to 124,
# the same "timed out" exit code produced by the external timeout(1) path.
mkdir -p "$WORKDIR/notimeout/bin"
ln -sf "$(command -v bash)" "$WORKDIR/notimeout/bin/bash"
ln -sf "$(command -v rm)" "$WORKDIR/notimeout/bin/rm"
ln -sf "$(command -v mkdir)" "$WORKDIR/notimeout/bin/mkdir"
ln -sf "$(command -v dirname)" "$WORKDIR/notimeout/bin/dirname" 2>/dev/null || true
ln -sf "$(command -v pwd)" "$WORKDIR/notimeout/bin/pwd" 2>/dev/null || true
ln -sf "$(command -v date)" "$WORKDIR/notimeout/bin/date"
ln -sf "$(command -v sleep)" "$WORKDIR/notimeout/bin/sleep"
cat >"$WORKDIR/notimeout/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    trap '' TERM
    mkdir -p .codegraph/partial
    sleep 41.271
    ;;
  serve)
    printf 'codegraph %s\n' "$*" >&2
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$WORKDIR/notimeout/bin/codegraph"
reset_codegraph_dir
reset_bootstrap_state
rc=0
CODEGRAPH_INIT_TIMEOUT=1 PATH="$WORKDIR/notimeout/bin" \
    bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || rc=$?
[[ "$rc" -eq 124 ]] || fail "KILL-escalated timeout should normalize to exit 124, got $rc"
[[ -d "$WORKDIR/project/.codegraph/partial" ]] && fail "partial .codegraph directory was not removed after KILL escalation"
grep -q 'timed out' "$WORKDIR/project/.codegraph-bootstrap.log" \
    || fail "KILL-escalated timeout was not logged as a timeout"
sleep 1
if pgrep -f 'sleep 41\.271' >/dev/null 2>&1; then
    fail "codegraph init child (sleep 41.271) survived as an orphan after KILL escalation"
fi

printf 'PASS\n'
