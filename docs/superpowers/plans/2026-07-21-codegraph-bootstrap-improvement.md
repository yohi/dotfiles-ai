# CodeGraph Bootstrap Wrapper 改善 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_scripts/codegraph-bootstrap.sh` を堅牢性・テスト品質・運用性の3観点から改善し、初回 `codegraph init` の自動化をより安全にする。

**Architecture:** 既存の `codegraph-bootstrap.sh` ラッパーに、診断ログ出力、`codegraph init` タイムアウト、`--status` / `--dry-run` モード、および強化されたエラー処理を追加する。テストは既存の回帰テストに並行起動・タイムアウト・コマンド不在ケースを追加する。CI / Makefile にはテスト実行を組み込む。

**Tech Stack:** Bash, CodeGraph CLI, APM-generated MCP config, GitHub Actions, GNU Make

## Global Constraints

- `apm.yml` は SSOT のまま維持する。
- 最終的な MCP プロセスは `codegraph serve --mcp` のまま維持する。
- すべての処理はローカル完結（外部サービス不使用）。
- stdin/stdout は MCP プロトコル専用に保護する。
- 既存の `flock` ロックと部分初期化クリーンアップは維持する。
- テストは TDD で追加し、既存テストも維持する。
- コミットは Conventional Commits（日本語）を使用する。

---

## File Structure

| ファイル | 責務 |
|---|---|
| `_scripts/codegraph-bootstrap.sh` | ブートストラップラッパー本体。ログ、タイムアウト、モード分岐、エラー処理を担当 |
| `_scripts/test-codegraph-bootstrap.sh` | 回帰テスト。既存ケース + 追加ケース |
| `.gitignore` | `.codegraph/logs/` を無視対象に追加 |
| `_mk/test.mk` | `test-all` ターゲットでブートストラップテストを自動実行 |
| `.github/workflows/ci.yml` | CI で `make test` 経由でテストを実行（現状維持、追加不要） |

---

### Task 1: ログユーティリティと環境変数の基盤を追加

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh:1-62`

**Interfaces:**
- Consumes: なし
- Produces: `_log()`, `_log_level()`, `CODEGRAPH_INIT_TIMEOUT`, `CODEGRAPH_LOG_LEVEL`, `CODEGRAPH_BOOTSTRAP_LOG` の動作

- [ ] **Step 1: 既存テストを実行して現状を確認する**

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `PASS`

- [ ] **Step 2: ログユーティリティと環境変数処理を追加する**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
CODEGRAPH_INIT_TIMEOUT="${CODEGRAPH_INIT_TIMEOUT:-300}"
CODEGRAPH_LOG_LEVEL="${CODEGRAPH_LOG_LEVEL:-info}"
CODEGRAPH_BOOTSTRAP_LOG="${CODEGRAPH_BOOTSTRAP_LOG:-$REPO_ROOT/.codegraph/logs/bootstrap.log}"

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
        mkdir -p "$(dirname "$CODEGRAPH_BOOTSTRAP_LOG")"
        printf '%s\n' "$line" >>"$CODEGRAPH_BOOTSTRAP_LOG"
    fi
}
```

- [ ] **Step 3: 変更後も既存テストが通ることを確認する**

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `PASS`

- [ ] **Step 4: コミットする**

```bash
git add _scripts/codegraph-bootstrap.sh
git commit -m "feat(codegraph): ブートストラップログ基盤を追加"
```

---

### Task 2: 事前検証とモード分岐を追加

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_log()` from Task 1
- Produces: `_ensure_codegraph_installed()`, `_show_status()`, `_show_dry_run()`

- [ ] **Step 1: `codegraph` コマンド不在テストを追加する（失敗する状態）**

`_scripts/test-codegraph-bootstrap.sh` の末尾の `printf 'PASS\n'` の前に追加：

```bash
# ---- codegraph command not found ----
rm -rf "$WORKDIR/project/.codegraph"
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr"
PATH="/bin:/usr/bin" bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" && fail "expected bootstrap to fail when codegraph missing"
grep -q 'codegraph.*not found\|codegraph.*install' "$WORKDIR/stderr" || fail "missing codegraph error message was not emitted"
```

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `FAIL` (missing codegraph error message was not emitted)

- [ ] **Step 2: 事前検証と `--status` / `--dry-run` モードを実装する**

既存の `codegraph-bootstrap.sh` に、ロック取得の前に以下を追加：

```bash
_ensure_codegraph_installed() {
    if ! command -v codegraph >/dev/null 2>&1; then
        _log error "codegraph command not found. Install with: npm i -g @colbymchenry/codegraph"
        exit 1
    fi
}

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

    if [ -f "$REPO_ROOT/.codegraph-bootstrap.lock" ]; then
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
    _log info "dry-run: would run codegraph init if .codegraph/ is missing, then exec codegraph $*"
    if [ ! -d "$REPO_ROOT/.codegraph" ]; then
        printf 'dry-run: codegraph init (because .codegraph/ is missing)\n'
    else
        printf 'dry-run: skip codegraph init (because .codegraph/ exists)\n'
    fi
    printf 'dry-run: exec codegraph %s\n' "$*"
    exit 0
}

_ensure_codegraph_installed

case "${1:-}" in
    --status)
        _show_status
        ;;
    --dry-run)
        _show_dry_run "$@"
        ;;
    serve)
        : # fall through to normal bootstrap
        ;;
    *)
        _log error "unknown mode: ${1:-<empty>}. Expected 'serve --mcp', '--status', or '--dry-run'"
        exit 1
        ;;
esac
```

- [ ] **Step 3: テストを実行して新ケースが通ることを確認する**

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `PASS`

- [ ] **Step 4: コミットする**

```bash
git add _scripts/codegraph-bootstrap.sh _scripts/test-codegraph-bootstrap.sh
git commit -m "feat(codegraph): 事前検証と status/dry-run モードを追加"
```

---

### Task 3: `codegraph init` のタイムアウトと強化されたクリーンアップ

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh`
- Modify: `_scripts/test-codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_log()` from Task 1
- Produces: `_initialize_once()` の新しい実装

- [ ] **Step 1: タイムアウトテストを追加する（失敗する状態）**

`_scripts/test-codegraph-bootstrap.sh` の `printf 'PASS\n'` の前に追加：

```bash
# ---- codegraph init timeout cleanup ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
LOG_FILE="${CODEGRAPH_LOG_FILE:-}"
case "${1:-}" in
  init)
    mkdir -p .codegraph/partial
    printf 'codegraph init slow\n' >&2
    printf 'codegraph init slow\n' >>"$LOG_FILE"
    sleep 10
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
rm -rf "$WORKDIR/project/.codegraph"
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr"
export CODEGRAPH_INIT_TIMEOUT=1
! bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout" 2>"$WORKDIR/stderr" || fail "expected bootstrap to timeout"
[ -d "$WORKDIR/project/.codegraph" ] && fail "partial .codegraph directory was not removed after timeout"
unset CODEGRAPH_INIT_TIMEOUT
```

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `FAIL` (expected bootstrap to timeout)

- [ ] **Step 2: `_initialize_once()` にタイムアウトと強化ログを追加する**

既存の `_initialize_once()` を以下のように置き換える：

```bash
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
        if timeout "$CODEGRAPH_INIT_TIMEOUT" codegraph init < /dev/null; then
            _log info "codegraph init completed"
        else
            local rc=$?
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
```

- [ ] **Step 3: テストを実行して通ることを確認する**

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `PASS`

- [ ] **Step 4: コミットする**

```bash
git add _scripts/codegraph-bootstrap.sh _scripts/test-codegraph-bootstrap.sh
git commit -m "feat(codegraph): codegraph init のタイムアウト処理を追加"
```

---

### Task 4: 並行起動テストとロック強化

**Files:**
- Modify: `_scripts/test-codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_acquire_lock()`, `_release_lock()` from existing script
- Produces: 並行起動時の init 回数検証

- [ ] **Step 1: 並行起動テストを追加する**

`_scripts/test-codegraph-bootstrap.sh` の `printf 'PASS\n'` の前に追加：

```bash
# ---- Concurrent launch: init runs only once ----
cat >"$WORKDIR/bin/codegraph" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
LOG_FILE="${CODEGRAPH_LOG_FILE:-}"
INIT_COUNT_FILE="${INIT_COUNT_FILE:-/tmp/codegraph-init-count}"
case "${1:-}" in
  init)
    mkdir -p .codegraph
    # Simulate slow init to expose races
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
rm -rf "$WORKDIR/project/.codegraph"
rm -f "$WORKDIR/codegraph.log" "$WORKDIR/stderr"
export INIT_COUNT_FILE="$WORKDIR/init-count"
echo 0 > "$INIT_COUNT_FILE"

bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout1" 2>"$WORKDIR/stderr1" &
PID1=$!
bash "$WORKDIR/project/_scripts/codegraph-bootstrap.sh" serve --mcp \
    >"$WORKDIR/stdout2" 2>"$WORKDIR/stderr2" &
PID2=$!
wait "$PID1" "$PID2"

INIT_COUNT="$(cat "$INIT_COUNT_FILE")"
[ "$INIT_COUNT" -eq 1 ] || fail "codegraph init ran $INIT_COUNT times, expected 1"
```

- [ ] **Step 2: テストを実行して通ることを確認する**

Run:
```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Expected: `PASS`

- [ ] **Step 3: コミットする**

```bash
git add _scripts/test-codegraph-bootstrap.sh
git commit -m "test(codegraph): 並行起動時の init 回数を検証するテストを追加"
```

---

### Task 5: Makefile と .gitignore への統合

**Files:**
- Modify: `.gitignore`
- Modify: `_mk/test.mk`

**Interfaces:**
- Consumes: `_scripts/test-codegraph-bootstrap.sh`
- Produces: `make test-all` 実行時の自動テスト統合

- [ ] **Step 1: `.gitignore` に `.codegraph/logs/` を追加する**

`.gitignore` に以下を追加（既存 `.codegraph-bootstrap.lock` エントリの近くが望ましい）：

```gitignore
.codegraph/logs/
```

- [ ] **Step 2: `_mk/test.mk` でブートストラップテストを実行する**

`_mk/test.mk` の `test-all` ターゲット内、bash ループの前に追加：

```makefile
	@echo "Running CodeGraph bootstrap regression test..."
	@bash _scripts/test-codegraph-bootstrap.sh
```

`test-all` ターゲットの変更後のイメージ：

```makefile
.PHONY: test-all
test-all: test-integrity check-skill-adapters ## Run all tests in the project
	@echo "Running all tests..."
	@echo "Running CodeGraph bootstrap regression test..."
	@bash _scripts/test-codegraph-bootstrap.sh
	@bash -c 'shopt -s nullglob; ...'
```

- [ ] **Step 3: `make test-all` を実行して通ることを確認する**

Run:
```bash
make test-all
```
Expected: すべてのテストが `PASS`

- [ ] **Step 4: コミットする**

```bash
git add .gitignore _mk/test.mk
git commit -m "chore(codegraph): ブートストラップテストを make test-all に統合"
```

---

### Task 6: 最終統合検証

**Files:**
- なし（検証のみ）

- [ ] **Step 1: 全体テストを実行する**

Run:
```bash
make test
```
Expected: `✅ All tests passed!`

- [ ] **Step 2: `--status` / `--dry-run` を手動で確認する**

Run:
```bash
_scripts/codegraph-bootstrap.sh --status
_scripts/codegraph-bootstrap.sh --dry-run serve --mcp
```
Expected: `--status` は `.codegraph/ present` を表示。`--dry-run` は `skip codegraph init` を表示。

- [ ] **Step 3: 最終コミットまたは PR 作成**

変更をまとめて確認：
```bash
git status
git diff --stat
```

必要に応じて：
```bash
git push origin feature/codegraph-bootstrap-improvement
```

---

## Self-Review Checklist

- [x] Spec coverage: 設計書の各要件（ログ分離、タイムアウト、status/dry-run、並行テスト、CI統合）に対応する Task あり
- [x] Placeholder scan: TBD/TODO/あとで実装 なし
- [x] Type consistency: Bash スクリプトの関数・変数命名に矛盾なし
- [x] Scope: 単一の実装計画として適切
