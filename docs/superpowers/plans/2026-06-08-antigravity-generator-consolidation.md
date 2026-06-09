# Antigravity Generator Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the duplicate Antigravity MCP config generator so a single, design-compliant script (`_scripts/sync_antigravity.py`, reading `apm.lock.yaml`) is the only generator wired into the build, removing the legacy `render-antigravity-config.py` and a dangling `uninstall-superpowers` Make reference.

**Architecture:** The repo currently has TWO generators writing the same `antigravity/mcp_config.json`: `sync_antigravity.py` (lockfile-based, design-compliant, wired into `make sync-agents` at `Makefile:37`) and the legacy `render-antigravity-config.py` (apm.yml-based, wired into `make sync-antigravity` at `_mk/antigravity.mk:55`, and documented in README). This plan repoints `make sync-antigravity` to the canonical `sync_antigravity.py`, deletes the legacy script, and removes a dead `uninstall-superpowers` call left over from an earlier cleanup. A red/green shell guard test locks the convergence in place and is auto-collected by `make test-all`.

**Tech Stack:** GNU Make (`_mk/*.mk`), Python (`uv run`), Bash, pytest, shellcheck

**Source findings:** `docs/superpowers/specs/2026-06-06-apm-optimization-design.md` (L33 names `sync_antigravity.py` as the single post-compile generator), verification report 2026-06-08 (dual-generator drift, ASCII-rule violation in legacy script, dangling `uninstall-superpowers`).

**Out of scope / no change required:**
- `README.md`: The user-facing command `make sync-antigravity` and the sentence "Antigravity 設定は `make sync-antigravity` で `antigravity/mcp_config.json` を生成し ... へリンクします" stay TRUE after this change (target name unchanged; still generates the same file). No README edit is needed for consolidation. (A pre-existing path inconsistency in the README symlink table -- `~/.gemini/antigravity/` vs the code's `~/.gemini/antigravity-cli/` -- is unrelated to this work and is gated behind separate user approval.)
- `Makefile:37` already invokes `sync_antigravity.py`; it stays as-is.
- `docs/superpowers/plans/2026-06-08-skill-directory-adapters.md:457` mentions `render-antigravity-config.py` as historical record; archived plans are not edited.

**Git policy:** Per project rules, git commits are performed by the human operator on explicit instruction only. Commit steps below are included for completeness; the executing agent MUST stage/verify but MUST NOT run `git commit` unless the user explicitly authorizes it.

---

### Task 1: Add a failing convergence guard test

**Files:**
- Create: `_scripts/test-antigravity-generator.sh`

This test is auto-collected by `make test-all` because `_mk/test.mk` loops over `_scripts/test-*.sh` (only `test-mcp-connectivity.sh` is skipped). No Make edit is needed to register it.

- [ ] **Step 1: Write the failing test**

Create `_scripts/test-antigravity-generator.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

# 1. The legacy apm.yml-based generator must be removed.
if [ -e "$REPO_ROOT/_scripts/render-antigravity-config.py" ]; then
    fail "legacy generator still present: _scripts/render-antigravity-config.py"
fi

# 2. sync-antigravity must invoke the canonical lockfile-based generator.
if ! grep -q "sync_antigravity.py" "$REPO_ROOT/_mk/antigravity.mk"; then
    fail "_mk/antigravity.mk does not invoke sync_antigravity.py"
fi

# 3. No reference to the legacy generator may remain in the Make wiring.
if grep -q "render-antigravity-config.py" "$REPO_ROOT/_mk/antigravity.mk"; then
    fail "_mk/antigravity.mk still references render-antigravity-config.py"
fi

# 4. The removed uninstall-superpowers target must not be invoked anywhere in _mk.
if grep -rq "uninstall-superpowers" "$REPO_ROOT/_mk"; then
    fail "_mk still references removed target uninstall-superpowers"
fi

printf 'PASS: antigravity generator consolidation verified.\n'
```

- [ ] **Step 2: Make the test executable**

Run: `chmod +x _scripts/test-antigravity-generator.sh`
Expected: command exits 0.

- [ ] **Step 3: Run the test and verify it FAILS before implementation**

Run: `bash _scripts/test-antigravity-generator.sh`
Expected: FAIL with the first unmet assertion, e.g.:

```text
FAIL: legacy generator still present: _scripts/render-antigravity-config.py
```

- [ ] **Step 4: Lint the new script**

Run: `shellcheck _scripts/test-antigravity-generator.sh`
Expected: shellcheck exits 0 (no output).

- [ ] **Step 5: Stage (commit only on explicit user authorization)**

```bash
git add _scripts/test-antigravity-generator.sh
# git commit -m "test: ガード追加 Antigravity生成器の一本化を検証"
```

---

### Task 2: Repoint `make sync-antigravity` to the canonical generator

**Files:**
- Modify: `_mk/antigravity.mk:50-56`

- [ ] **Step 1: Replace the `sync-antigravity` recipe**

Current block (`_mk/antigravity.mk:50-56`):

```makefile
# Antigravityの設定を生成して同期
sync-antigravity: ## apm.ymlからAntigravity用のMCP設定を生成して同期
	@echo "🔄 Generating Antigravity MCP config from apm.yml..."
	@mkdir -p "$(REPO_ROOT)/antigravity"
	@set -a; [ -f "$(REPO_ROOT)/.env" ] && . "$(REPO_ROOT)/.env"; set +a; \
	uv run python3 "$(REPO_ROOT)/_scripts/render-antigravity-config.py"
	@$(MAKE) setup-antigravity
```

Replace with (data source changes apm.yml -> apm.lock.yaml; script changes render -> sync; explicit paths so it works from any CWD; preserve the `.env` load wrapper):

```makefile
# Antigravityの設定を生成して同期
sync-antigravity: ## apm.lock.yamlからAntigravity用のMCP設定を生成して同期
	@echo "🔄 Generating Antigravity MCP config from apm.lock.yaml..."
	@mkdir -p "$(REPO_ROOT)/antigravity"
	@set -a; [ -f "$(REPO_ROOT)/.env" ] && . "$(REPO_ROOT)/.env"; set +a; \
	uv run python3 "$(REPO_ROOT)/_scripts/sync_antigravity.py" \
		--lockfile "$(REPO_ROOT)/apm.lock.yaml" \
		--output "$(REPO_ROOT)/antigravity/mcp_config.json"
	@$(MAKE) setup-antigravity
```

Rationale: `sync_antigravity.py` accepts `--lockfile` (default `apm.lock.yaml`) and `--output` (default `antigravity/mcp_config.json`) per its `argparse` block (`_scripts/sync_antigravity.py:203-214`). `apm.lock.yaml` is committed and contains the resolved `mcp_configs` block (verified: `apm.lock.yaml:60` onward), so the standalone target works without requiring a fresh `apm compile`.

- [ ] **Step 2: Confirm the recipe parses and resolves the correct script**

Run: `make -n sync-antigravity`
Expected: the printed recipe shows `_scripts/sync_antigravity.py` with `--lockfile`/`--output` and NO mention of `render-antigravity-config.py`.

- [ ] **Step 3: Stage (commit only on explicit user authorization)**

```bash
git add _mk/antigravity.mk
# git commit -m "refactor: sync-antigravity を正規生成器 sync_antigravity.py に一本化"
```

---

### Task 3: Delete the legacy generator

**Files:**
- Delete: `_scripts/render-antigravity-config.py`

This also resolves the ASCII-only-output rule violation (the legacy script printed a non-ASCII check-mark at `render-antigravity-config.py:102`).

- [ ] **Step 1: Confirm no remaining active references before deletion**

Run: `grep -rn "render-antigravity-config\|render_antigravity" . --exclude-dir=oss --exclude-dir=.git`
Expected: matches ONLY in (a) `_scripts/test-antigravity-generator.sh` (guard assertions), and (b) `docs/superpowers/plans/2026-06-08-skill-directory-adapters.md` (historical record). No match in any `_mk/*.mk`, `Makefile`, or executable script other than the guard test.

- [ ] **Step 2: Delete the file**

Run: `git rm _scripts/render-antigravity-config.py`
(If the file is untracked, use `rm _scripts/render-antigravity-config.py`.)
Expected: file removed.

- [ ] **Step 3: Stage (commit only on explicit user authorization)**

```bash
git add -u _scripts/render-antigravity-config.py
# git commit -m "chore: 旧式 Antigravity 生成器 render-antigravity-config.py を削除"
```

---

### Task 4: Remove the dangling `uninstall-superpowers` call

**Files:**
- Modify: `_mk/main.mk:82`

The `uninstall-superpowers` target definition was already removed (verified: no `^uninstall-superpowers:` definition exists in `_mk/`), but `clean-internal` still calls it. The leading `-` swallows the error, so this is harmless drift; removing it completes the earlier cleanup intent (design spec 2.3).

- [ ] **Step 1: Delete the dangling call line**

In `_mk/main.mk`, inside the `clean-internal` target, remove this single line (currently `_mk/main.mk:82`):

```makefile
	-$(MAKE) uninstall-superpowers
```

Leave the surrounding `clean-internal` lines (`uninstall-mcp` above it at L81, `uninstall-cursor` below it at L83) untouched.

- [ ] **Step 2: Verify the reference is gone and `clean-internal` still parses**

Run: `grep -rn "uninstall-superpowers" _mk Makefile`
Expected: no output (exit 1 from grep is fine).

Run: `make -n clean-internal`
Expected: recipe prints without referencing `uninstall-superpowers` and without a "No rule to make target" error.

- [ ] **Step 3: Stage (commit only on explicit user authorization)**

```bash
git add _mk/main.mk
# git commit -m "fix: 定義削除済み uninstall-superpowers への dangling 呼び出しを除去"
```

---

### Task 5: Full verification

**Files:**
- Verify only: no planned edits

- [ ] **Step 1: Run the convergence guard test (now GREEN)**

Run: `bash _scripts/test-antigravity-generator.sh`
Expected:

```text
PASS: antigravity generator consolidation verified.
```

- [ ] **Step 2: Run the generator unit tests**

Run: `PYTHONPATH=. uv run pytest tests/test_sync_antigravity.py -v`
Expected: all tests PASS (the generator logic is unchanged; this confirms no regression).

- [ ] **Step 3: Dry-run the repointed target end to end**

Run: `make -n sync-antigravity`
Expected: shows `sync_antigravity.py` invocation followed by `make setup-antigravity`; no `render-antigravity-config.py`.

- [ ] **Step 4: Actually generate the config and confirm content shape**

Run:

```bash
uv run python3 _scripts/sync_antigravity.py --lockfile apm.lock.yaml --output /tmp/antigravity-check.json
python3 -c "import json; d=json.load(open('/tmp/antigravity-check.json')); s=d['mcpServers']; assert set(s)>= {'skillport','docker-mcp','nexus','chronos-graph'}, sorted(s); assert s['skillport']['env']['SKILLPORT_SKILLS_DIR'].endswith('/.agents/skills'), s['skillport']['env']['SKILLPORT_SKILLS_DIR']; print('OK', sorted(s))"
```

Expected: prints `OK ['chronos-graph', 'docker-mcp', 'nexus', 'skillport']` -- proving the lockfile data flow yields all four servers and the SkillPort env points at `.agents/skills`.

- [ ] **Step 5: Confirm the skill-adapter invariant still holds**

Run: `bash _scripts/test-skill-adapters.sh` (if native adapter dirs are set up in this environment) OR at minimum:
`grep -R "SKILLPORT_SKILLS_DIR.*agent-skills" .mcp.json opencode.json .codex/config.toml antigravity/mcp_config.json .agents/mcp_config.json 2>/dev/null; test $? -ne 0`
Expected: no generated config points SkillPort at `agent-skills`.

- [ ] **Step 6: Lint touched surfaces**

Run:

```bash
shellcheck _scripts/test-antigravity-generator.sh
make lint
```

Expected: `shellcheck` exits 0; `make lint` (ruff + mypy over the repo, excluding `oss`) exits 0. Deleting `render-antigravity-config.py` only reduces the Python lint surface.

- [ ] **Step 7: Stage any verification fixes (commit only on explicit user authorization)**

```bash
git add -A
# git commit -m "test: Antigravity 生成器一本化の検証を完了"
```

---

## Self-review

- **Spec coverage:** Design spec 2.2/L33 (single `sync_antigravity.py` post-compile generator from `apm.lock.yaml`) is enforced by Task 2 (repoint) + Task 3 (delete legacy) + Task 1/5 (guard test). Verification-report findings #1 (dual generator) -> Tasks 2-3; #2 (ASCII violation) -> Task 3 (deletion); #4 (dangling `uninstall-superpowers`) -> Task 4. Finding #3 (`make sync-agents` generates but does not link) is intentionally NOT changed -- `make setup` already links via `setup-agents` -> `setup-antigravity`, and altering `sync-agents` to deploy is a behavior change outside this consolidation's scope.
- **Placeholder scan:** No "TBD"/"handle edge cases" steps; every code/command step shows exact content and expected output.
- **Type/naming consistency:** `sync_antigravity.py`, `--lockfile`, `--output`, `antigravity/mcp_config.json`, `RUNTIME_SKILLS_DIR` used consistently. The guard test grep patterns match the exact strings edited in Tasks 2-4.
- **Ordering:** Task 1 establishes red; Tasks 2-4 make it green; Task 5 proves green + no regression. Safe to execute top-to-bottom.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-08-antigravity-generator-consolidation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
