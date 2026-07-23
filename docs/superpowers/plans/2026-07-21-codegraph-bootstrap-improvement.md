# CodeGraph Bootstrap Wrapper 改善 実装計画（完了）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_scripts/codegraph-bootstrap.sh` を堅牢性・テスト品質・運用性の3観点から改善し、初回 `codegraph init` の自動化をより安全にする。

**Architecture:** 既存の `codegraph-bootstrap.sh` ラッパーに、診断ログ出力、`codegraph init` タイムアウト、`--status` / `--dry-run` モード、および強化されたエラー処理を追加する。テストは既存の回帰テストに並行起動・タイムアウト・コマンド不在ケースを追加する。

**Tech Stack:** Bash, CodeGraph CLI, APM-generated MCP config

## Global Constraints

- `apm.yml` は SSOT のまま維持する。
- 最終的な MCP プロセスは `codegraph serve --mcp` のまま維持する。
- すべての処理はローカル完結（外部サービス不使用）。
- stdin/stdout は MCP プロトコル専用に保護する。
- 既存の `flock` ロックと部分初期化クリーンアップは維持する。
- テストは TDD で追加し、既存テストも維持する。

---

## File Structure

| ファイル | 責務 |
|---|---|
| `_scripts/codegraph-bootstrap.sh` | ブートストラップラッパー本体。ログ、タイムアウト、モード分岐、エラー処理を担当 |
| `_scripts/test-codegraph-bootstrap.sh` | 回帰テスト。既存ケース + 追加ケース |
| `.gitignore` | `.codegraph-bootstrap.log` / `.codegraph-bootstrap.lock` を無視対象に追加 |

---

## 変更点サマリ

| 項目 | 変更前 | 変更後 |
|---|---|---|
| ログパス | `.codegraph/logs/` 内（計画時） | `$REPO_ROOT/.codegraph-bootstrap.log`（`.codegraph/` 外に配置して init の状態判定に影響しない） |
| ログ出力 | `printf` 直書き | `_log()` 関数（レベル制御付き。`error`/`warn` は stderr へ、`info`/`debug` はログファイルへ） |
| 事前検証 | なし | `_ensure_codegraph_installed()` + 厳密な引数検証（`serve --mcp` のみ許可） |
| モード分岐 | なし | `--status`（codegraph 未インストールでも動作） / `--dry-run serve --mcp` / `serve --mcp` |
| タイムアウト | なし | `timeout` / `gtimeout` / Bash watchdog フォールバック。`CODEGRAPH_INIT_TIMEOUT` で制御 |
| テスト | 基本ケースのみ | status/dry-run/timeout fallback/invalid args/stdin isolation/concurrent init を追加 |

---

## Task 1: ログユーティリティと環境変数の基盤を追加

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh:1-62`

**Interfaces:**
- Produces: `_log()`, `_log_level_rank()`, `CODEGRAPH_INIT_TIMEOUT`, `CODEGRAPH_LOG_LEVEL`, `CODEGRAPH_BOOTSTRAP_LOG`

- [x] **Step 1: ログユーティリティと環境変数処理を追加する**

```bash
CODEGRAPH_BOOTSTRAP_LOG="${CODEGRAPH_BOOTSTRAP_LOG:-$REPO_ROOT/.codegraph-bootstrap.log}"
```

**重要な設計決定:** ログファイルは `.codegraph/` 内ではなくプロジェクトルート直下の `.codegraph-bootstrap.log` に配置する。これにより、ログ出力そのものが `codegraph init` の状態判定に影響することを防ぐ。

- [x] **Step 2: 変更後も既存テストが通ることを確認する**

Result: `PASS`

---

## Task 2: 事前検証とモード分岐を追加

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_log()` from Task 1
- Produces: `_ensure_codegraph_installed()`, `_show_status()`, `_show_dry_run()`

**変更点:** `_ensure_codegraph_installed()` は通常モード（`serve --mcp`）時のみ実行されるように制御。`--status` と `--dry-run` は、codegraph が未インストールでも動作する必要があるため、インストールチェックより先に終了する。

```bash
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
    ...
}
```

- [x] **テストを実行して新ケースが通ることを確認する**

Result: `PASS`

---

## Task 3: `codegraph init` のタイムアウトと強化されたクリーンアップ

**Files:**
- Modify: `_scripts/codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_log()` from Task 1
- Produces: `_run_init_with_timeout()` の新しい実装

**変更点:** `timeout` コマンドがない環境（macOS など）では、`gtimeout` を検索し、それもなければ Bash watchdog フォールバックを使用する。

```bash
_run_init_with_timeout() {
    local timeout_cmd=""

    if command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout"
    fi

    if [[ -n "$timeout_cmd" ]]; then
        "$timeout_cmd" "$CODEGRAPH_INIT_TIMEOUT" codegraph init < /dev/null
        return $?
    fi

    # Bash watchdog fallback for macOS and other systems without timeout/gtimeout.
    # Launch codegraph init in a background process group so the watchdog can
    # terminate the entire group (init + any child processes it forks).
    local init_pid
    local watchdog_pid
    local init_rc=0

    # Enable job control momentarily so the background job receives its own
    # process group ID (PGID), making init_pid usable as the PGID.
    set -m
    codegraph init < /dev/null &
    init_pid=$!
    set +m

    (
        sleep "$CODEGRAPH_INIT_TIMEOUT"
        # Signal the whole process group, not just the parent process.
        kill -TERM -"$init_pid" 2>/dev/null || true
        # Brief grace period after TERM, then forcibly reap at the PGID level.
        sleep 2
        kill -KILL -"$init_pid" 2>/dev/null || true
    ) &
    watchdog_pid=$!

    if wait "$init_pid"; then
        init_rc=0
    else
        init_rc=$?
    fi

    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    if [[ "$init_rc" -eq 143 ]] || [[ "$init_rc" -eq 129 ]]; then
        # TERM/KILL signals normalize to the timeout(1) timeout exit code.
        init_rc=124
    fi

    return "$init_rc"
}
```

- [x] **テストを実行して通ることを確認する**

Result: `PASS`

---

## Task 4: 並行起動テストとロック強化

**Files:**
- Modify: `_scripts/test-codegraph-bootstrap.sh`

**Interfaces:**
- Consumes: `_acquire_lock()`, `_release_lock()` from existing script
- Produces: 並行起動時の init 回数検証

- [x] **Step 1: 並行起動テストを追加する**

2つのプロセスを同時に起動し、`flock` により `codegraph init` が1回だけ実行されることを検証する。

- [x] **テストを実行して通ることを確認する**

Result: `PASS`

---

## Task 5: `.gitignore` への統合

**Files:**
- Modify: `.gitignore`

- [x] **`.gitignore` に `.codegraph-bootstrap.log` を追加する**

`.codegraph-bootstrap.lock` の近くに追加：

```gitignore
# CodeGraph runtime files
.codegraph/
.codegraph-bootstrap.log
.codegraph-bootstrap.lock
```

---

## Task 6: 最終統合検証

**Files:**
- なし（検証のみ）

- [x] **Step 1: 全体テストを実行する**

```bash
bash _scripts/test-codegraph-bootstrap.sh
```
Result: `PASS`

- [x] **Step 2: `--status` / `--dry-run` を手動で確認する**

```bash
_scripts/codegraph-bootstrap.sh --status
_scripts/codegraph-bootstrap.sh --dry-run serve --mcp
```

Result: `--status` は正しくインストール状態を表示。`--dry-run` は正しく実行プランを表示。

---

## Self-Review Checklist

- [x] Spec coverage: 設計書の各要件（ログ分離、タイムアウト、status/dry-run、並行テスト）に対応する実装済み
- [x] Placeholder scan: TBD/TODO/あとで実装 なし
- [x] Type consistency: Bash スクリプトの関数・変数命名に矛盾なし
- [x] Scope: 単一の実装計画として適切

## Review Feedback（対応済み）

| Issue | 内容 | 対応 |
|---|---|---|
| Issue 1 | `_log()` が `.codegraph/` を作成しないこと | ✅ ログパスを `.codegraph/` 外に変更 |
| Issue 2 | `--status`/`--dry-run` がインストールチェックより先に終了 | ✅ `_main()` でモード判定を最初に実行 |
| Issue 3 | `serve --mcp` が正確なモードか検証 | ✅ `_is_serve_mcp_mode()` で厳密に検証 |
| Issue 4 | macOS で `timeout` がない | ✅ `timeout`/`gtimeout`/Bash watchdog の3段階フォールバック |
| Issue 5 | `test-all` で二重実行 | ✅ `_mk/test.mk` は変更せず、テストファイル単体でカバー |
| Issue 6 | 新規契約のテスト | ✅ `--status`/`--dry-run`/ログ/stdin 隔離の自動テストを追加 |
