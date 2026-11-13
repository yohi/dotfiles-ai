# OC2 Daily Launcher — F-004 Guest Quiescence Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans **only after Human Owner explicitly authorizes execution**. Tasks have checkboxes. Do not automatically dispatch subagents or start independent review, implementation, GitHub writes, or later tasks.

**Goal:** Verify whether the Design R0.1.3 cgroup v2 Freezer candidate can safely contain the real Guest writer topology and capture a consistent read-only Git collection.

**Architecture:** Retain Mountless Docker Sandbox and the existing SessionKey/HostApplyGate design. Prove whole-session Writer Group containment, independently enforced collector read-only access, and consistency from freeze through copy; if any proof is missing, preserve Guest data as `PENDING` and keep auto-Collect/Host Apply disabled.

**Tech Stack:** Ubuntu Server 26.04; Docker Sandboxes v0.53.0; Linux cgroup v2; Python 3 standard library and `unittest`; Git; Linux capabilities and mount namespaces only when demonstrated available.

**Spec:** `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md` — Design R0.1.3 at commit `32957409840f99aa25c974c3a31547fc25e32ab2`, blob `bb4218078c5dcb4c609fe0c8d77fe778ee1ebbfa`; §6, §10.1, §11 and §12.

**Scope:** F-004 **feasibility only**, not implementation of OC2 Daily Launcher. The Plan is a document, not authorization to write code or operate a Sandbox.

## Global Constraints

- Project goal: from a Git repository root, daily `oc2` use with Sandbox isolation and Host data preservation.
- Preserve Mountless, APM Full SSOT, selective Git Bundle, one-time Owner Apply authorization, and SessionKey = (`WorkspaceID`, `SandboxID`, `SessionGeneration`).
- Do not mount Host Workspace or `.git`; no Host Apply, Git push, credential or LLM inference, plugin installation, Docker configuration changes, or existing Phase 5/v1 changes.
- Dynamic tests require **separate Owner execution approval** and a disposable credential-free Sandbox. Evidence must remain outside Git repository, in a mode-0700 `/tmp/oc2-f004-feasibility.*` directory.
- `sbx stop → sbx cp` is rejected: stopped Sandbox was started by `sbx cp` on v0.51.0 and v0.53.0.
- `frozen 1` is necessary but insufficient: it does not prove absence of escaped, migrated, privileged, or out-of-group writers.
- Existing single-Writer PoC passed **for its fixture only**; do not rerun it or treat it as full OpenCode/Plugin/MCP coverage.
- A FAIL or NOT_VERIFIED never creates final `collection_digest`, `ApplyAuthorization`, or Host Apply. Preserve Guest original and partial evidence, and stop without switching architectures automatically.

## File Map

**Existing implementation — read-only reference for this plan:**
- `sandbox/scripts/oc2.py`: host `Runner.sbx()`, Sandbox orchestration and launch; not yet Daily Launcher / F-004-complete.
- `sandbox/scripts/oc2_workspace.py` and `oc2_workspace_ops.py`: current snapshot and comparison utilities.
- `sandbox/scripts/oc2_session.py`: current session receipt, **not** Design v3 SessionGeneration state.
- `sandbox/tests/test_oc2.py`, `sandbox/tests/test_oc2_e2e.py`: repository's `unittest` conventions and FakeSbx precedent.

**New test-only files, for a future authorized execution:**
- `sandbox/tests/oc2_f004_feasibility.py`: gate result schema and pure decision functions (never imported by the production launcher).
- `sandbox/tests/test_oc2_f004_feasibility.py`: deterministic unit tests for the gates and failure handling.
- `sandbox/tests/fixtures/f004_writer_tree.py`: synthetic parent/child/grandchild/background Writer and escape probes.
- `sandbox/tests/fixtures/f004_collector.py`: non-writing collector probe; prohibited-write tests.
- Evidence: `/tmp/oc2-f004-feasibility.<unique>/` (not committed and without credentials/private project data).

**Test-only interface fixed across tasks:**

```python
from dataclasses import dataclass
from typing import Literal

ProbeVerdict = Literal['PASS', 'FAIL', 'NOT_VERIFIED']

@dataclass(frozen=True)
class GateResult:
    gate: Literal['containment', 'collector', 'consistency']
    verdict: ProbeVerdict
    evidence_paths: tuple[str, ...]
    scope: Literal['fixture', 'full-runtime']
    reason: str

def combine_gates(results: tuple[GateResult, ...]) -> ProbeVerdict:
    # FAIL if an observed unsafe condition exists; PASS only for exactly
    # three full-runtime PASS gates; otherwise NOT_VERIFIED.
    ...
```

Every PASS must reference concrete kernel/cgroup/process/permission/hash observations, not just asserted booleans.

## Review Focus — Dangerous inputs requiring negative tests

1. Plugin spawns a detached grandchild/background writer outside Writer Group: containment cannot PASS.
2. Writer escapes through `cgroup.procs`, privileged capabilities, or an exposed Docker socket: containment FAIL if bypass occurs.
3. Collector can write Git Index, Git Objects, Working Tree, or parent dir (or remount writable): collector cannot PASS.
4. Cgroup thaws, a writer appears, or SessionKey/SandboxID changes during copying: collection cannot finalize.
5. Git copy/Bundle/Manifest is truncated, changes during capture, or loses Untracked: preserve original and partial data, mark `PENDING`.

---

### Task 1: Deterministic fail-closed gate evaluator

**Files:** Create `sandbox/tests/oc2_f004_feasibility.py`; test `sandbox/tests/test_oc2_f004_feasibility.py`.

**Interfaces:** Produces `GateResult` and `combine_gates(...)` for Tasks 2–4. Consumes evidence references tied to a Sandbox ID and SessionKey.

- [ ] **Step 1 — RED:** Write tests `test_three_full_runtime_passes_required`, `test_fixture_pass_is_not_full_runtime_pass`, `test_missing_or_duplicate_gate_not_verified`, `test_observed_escape_is_fail`, `test_digest_not_issued_on_failure`. Assertions: only three distinct full-runtime PASS gates yield PASS; unsafe observation yields FAIL; incomplete proof yields NOT_VERIFIED.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect failure because gate implementation is missing.
- [ ] **Step 3 — Minimal implementation:** Add the exact test-only interface above and deterministic validation of gate coverage, evidence references, verdict and scope. Do not add launcher integration.
- [ ] **Step 4 — Verify GREEN:** Re-run the same unit tests; expect named tests PASS.
- [ ] **Step 5 — Stop:** Record test results. Do not commit without separate Owner GitHub-write approval.

**Deliverable:** Offline test gate that cannot mistake fixture evidence or missing proof for full-runtime PASS.

### Task 2: Session Writer containment and escape proof

**Files:** Create `sandbox/tests/fixtures/f004_writer_tree.py`; extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/containment/`.

**Interfaces:** Consumes Task 1 gate evaluator. Produces containment evidence for `GateResult(gate='containment', ...)`.

- [ ] **Step 1 — RED:** Add tests `test_writer_attached_before_first_instruction`, `test_child_and_detached_grandchild_captured`, `test_writer_cgroup_migration_refused`, `test_privileged_socket_or_capability_escape_refused`, `test_unexamined_plugin_topology_not_verified`.
- [ ] **Step 2 — Verify RED:** Run `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect failures in newly added tests only.
- [ ] **Step 3 — Minimal fixture:** Implement synthetic parent/child/grandchild/background Writer, with instrumentation proving membership **before the first file write**. Assess an atomic spawn-into-cgroup primitive such as `clone3(CLONE_INTO_CGROUP)` under actual Sandbox permissions/seccomp; an after-spawn `echo PID > cgroup.procs` alone is insufficient. Do not install packages or broaden the mechanism if unavailable.
- [ ] **Step 4 — Authorized Sandbox test:** Launch fixture under the Session Writer Group; collect `/proc/<pid>/cgroup`, creation/exit evidence, `cgroup.events`, UID/capabilities, socket exposure and migration attempt results. Attempt out-of-group writes and privileged escape using only disposable fixture files. Observe `frozen 1` once all fixture writers are captured.
- [ ] **Step 5 — Full-runtime applicability:** Verify **actual** OpenCode, approved Plugin/MCP and spawned/background writers under a no-inference, no-credential configuration if achievable without changing production configuration. Otherwise record full-runtime `NOT_VERIFIED`, even if the synthetic fixture passes. Successful privileged escape is `FAIL`.
- [ ] **Step 6 — Verify GREEN and classify:** Run `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; retain per-process evidence and output one containment GateResult. Stop if bypass observed or complete topology cannot be verified; do not start alternate mechanisms.

**Deliverable:** Evidence about pre-exec capture, descendants, migration/escape, and external writers; not just a Freeze test.

### Task 3: Enforced read-only Collector

**Files:** Create `sandbox/tests/fixtures/f004_collector.py`; extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/collector/`.

**Interfaces:** Consumes frozen fixture repository and containment evidence. Produces `GateResult(gate='collector', ...)`.

- [ ] **Step 1 — RED:** Add tests `test_collector_reads_git_layers`, `test_index_object_worktree_writes_denied`, `test_rename_unlink_denied`, `test_writable_remount_denied`, `test_collector_cannot_spawn_writer_to_source`.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect newly added tests FAIL.
- [ ] **Step 3 — Establish real enforcement:** Attempt an independent collector identity outside Writer Group, with a **kernel-enforced read-only source view**, no write/remount capability and a separate writable staging area (e.g. separate mount namespace and read-only bind view **if supported**). Environment variable `GIT_OPTIONAL_LOCKS=0` or an application promise alone is insufficient.
- [ ] **Step 4 — Test negative operations:** Explicitly attempt `open(O_WRONLY)`, index update, object creation, rename/unlink, privileged remount and a child writer against source; all must be denied. Run Git HEAD/Index/Working Tree/Untracked reads and selective Bundle/Manifest creation **to staging**, comparing raw Index/source hashes before/after. Never exercise these probes on an actual user repository.
- [ ] **Step 5 — Verify GREEN and classify:** Run offline unit tests and record observed permission/capability/mount failures. If read-only enforcement cannot be established, result is `NOT_VERIFIED`, no unapproved workaround.

**Deliverable:** Reproducible proof of collector non-write enforcement or explicit NOT_VERIFIED/FAIL.

### Task 4: Freeze → copy → consistency and PENDING preservation

**Files:** Extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/consistency/`.

**Interfaces:** Consumes Tasks 2–3 evidence; produces `GateResult(gate='consistency', ...)`. Never creates a production `collection_digest` or `ApplyAuthorization`.

- [ ] **Step 1 — RED:** Add tests `test_thaw_before_copy_complete_rejected`, `test_new_writer_during_copy_rejected`, `test_session_identity_change_rejected`, `test_untracked_mismatch_rejected`, `test_partial_copy_preserves_pending`.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect new tests FAIL.
- [ ] **Step 3 — Implement test-only comparison:** Check Sandbox ID, SessionKey, Writer Group identity, `frozen 1` and no external Writer **before staging, before `sbx cp`, after copy and immediately before simulated finalization**. Check Git HEAD/Branch, raw Index SHA-256, staged/unstaged/untracked manifest, Bundle object reachability, source/destination digests and `git fsck`.
- [ ] **Step 4 — Dynamic negative tests:** Induce one controlled thaw/new Writer and one partial copy/failure on disposable fixture data. Confirm no simulated finalization; Guest original, evidence and partial Host collection remain, and status is `PENDING`/`GUEST_QUIESCENCE_UNVERIFIED`.
- [ ] **Step 5 — Verify GREEN:** Run unit tests, capture hashes and classify gate. A static fixture PASS is not full-runtime consistency PASS.

**Deliverable:** Consistency and preservation evidence without granting Host Apply.

### Task 5: One Human Owner decision checkpoint (no review loop)

**Files:** Future evidence only: `/tmp/oc2-f004-feasibility.*/decision.md`.

**Interfaces:** Consumes exactly the three GateResults and returns one `PASS` / `FAIL` / `NOT_VERIFIED` verdict with observed evidence IDs.

- [ ] **Step 1 — Check evidence:** Verify sandbox/tool versions, identity, time window, negative tests, hashes and no credentials/inference; missing items remain NOT_VERIFIED.
- [ ] **Step 2 — Report:** One compact table for containment, collector, consistency; distinguish fixture from actual runtime.
- [ ] **Step 3 — Decide:** Full-runtime three-gate PASS → eligible for Owner consideration of a later implementation plan (NOT Implementation GO). Any unsafe behavior → FAIL, HOLD. Missing proof → NOT_VERIFIED, HOLD.
- [ ] **Step 4 — Stop:** Ask Human Owner for one decision. Do **not** automatically start implementation, new independent review, architecture alternatives, PR, or GitHub write.

## Completion / Stop Conditions

- **Writing-plans complete now:** A plan with exact files, interfaces, test commands, negative tests, failure-preservation rules and one decision gate has been produced. No Source changes or Sandbox tests executed by this task.
- **Feasibility PASS later:** All actual full-runtime Writer/Collector/Consistency gates are proven with kernel-backed evidence. This only permits a separate Owner judgment about implementation planning.
- **FAIL:** Observed escape, collector write, inconsistent state, lost data or unauthorized finalization; preserve Guest state and stop.
- **NOT_VERIFIED:** Cannot exercise actual runtime or prove an enforcement boundary. Preserve state, keep auto-Collect/Host Apply and Implementation GO on HOLD.
- **No loop:** One bounded test attempt for each unverified hypothesis. Do not repeat prior single-writer PoC or start review/correction sessions by default.

**Authorization record:** The Owner approved Design R0.1.3 **WITH BLOCKERS**. The explicit request here is `superpowers:writing-plans`, **not** approval to execute this plan, commit/push it, or change the runtime.
