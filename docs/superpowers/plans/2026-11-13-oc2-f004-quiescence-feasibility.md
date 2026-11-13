# OC2 Daily Launcher — F-004 Guest Quiescence Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans **only after Human Owner explicitly authorizes execution**. Tasks have checkboxes. Do not automatically dispatch subagents or start independent review, implementation, GitHub writes, or later tasks.

**Goal:** Verify whether the Design R0.1.3 cgroup v2 Freezer candidate can safely contain the real Guest writer topology and capture a consistent read-only Git collection.

**Architecture:** Retain Mountless Docker Sandbox and the existing SessionKey/HostApplyGate design. Prove whole-session Writer Group containment, independently enforced collector read-only access, and consistency from freeze through copy; if any proof is missing, preserve Guest data as `PENDING` and keep auto-Collect/Host Apply disabled.

**Tech Stack:** Ubuntu Server 26.04; Docker Sandboxes v0.53.0; Linux cgroup v2; Python 3 standard library and `unittest`; Git; Linux capabilities and mount namespaces only when demonstrated available.

**Spec:** `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md` — Design R0.1.3 at commit `32957409840f99aa25c974c3a31547fc25e32ab2`, blob `bb4218078c5dcb4c609fe0c8d77fe778ee1ebbfa`; §6, §10.1, §11 and §12.

**Scope:** F-004 **feasibility only**, not implementation of OC2 Daily Launcher. The Plan is a document, not authorization to write code or operate a Sandbox. This correction is limited to Review Gate findings **F-004-P1/P2/P3**; do not introduce a different architecture.

**Owner Decision (separate authorities):** (1) Design R0.1.3 was **accepted as a document with blockers** (`ADOPT_DESIGN_R0.1.3_WITH_BLOCKERS`); (2) unrestricted/final implementation-ready Design adoption and residual-risk acceptance are **NOT AUTHORIZED**; (3) this Plan's drafting and prior GitHub commit were authorized, but **execution of this Feasibility Plan is NOT AUTHORIZED**; (4) production implementation/Host Apply **GO = HOLD**. None of these decisions imply the next one. Do not treat Plan review or documentation correction as PoC execution approval.

## Global Constraints

- Project goal: from a Git repository root, daily `oc2` use with Sandbox isolation and Host data preservation.
- Preserve Mountless, APM Full SSOT, selective Git Bundle, one-time Owner Apply authorization, and SessionKey = (`WorkspaceID`, `SandboxID`, `SessionGeneration`).
- Do not mount Host Workspace or `.git`; no Host Apply, Git push, credential or LLM inference, plugin installation, Docker configuration changes, or existing Phase 5/v1 changes.
- Dynamic tests require **separate Owner execution approval** and a disposable credential-free Sandbox. Evidence must remain outside Git repository, in a mode-0700 `/tmp/oc2-f004-feasibility.*` directory.
- `sbx stop → sbx cp` is rejected: stopped Sandbox was started by `sbx cp` on v0.51.0 and v0.53.0.
- `frozen 1` is necessary but insufficient: it does not prove absence of escaped, migrated, privileged, or out-of-group writers.
- Existing single-Writer PoC passed **for its fixture only**; do not rerun it or treat it as full OpenCode/Plugin/MCP coverage.
- A FAIL or NOT_VERIFIED never creates final `collection_digest`, `ApplyAuthorization`, or Host Apply. Preserve Guest original and partial evidence, and stop without switching architectures automatically.
- All three full-runtime Gates must derive from **one probe_run_id, one SessionKey, one SandboxID and one Writer Group identity**, with individually verified SHA-256 Evidence Manifests. Evidence gathered from another Session, fixture, different Sandbox or another run cannot be silently combined.
- **Verdict semantics:** observed successful prohibited write, observed Writer escape, or observed unauthorized source mutation is `FAIL`; not executed, unable to observe, unknown, missing/mismatched evidence, or incomplete runtime coverage is `NOT_VERIFIED`. An independently verified unsafe `FAIL` for this probe run takes priority over missing Gates; invalid or unrelated evidence never becomes `PASS`.

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

**Test-only interface fixed across tasks (F-004-P2):**

```python
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Literal

ProbeVerdict = Literal['PASS', 'FAIL', 'NOT_VERIFIED']
ProbeScope = Literal['fixture', 'full-runtime']

@dataclass(frozen=True)
class GateResult:
    gate: Literal['containment', 'collector', 'consistency']
    probe_run_id: str
    session_key: tuple[str, str, str]  # WorkspaceID, SandboxID, SessionGeneration
    sandbox_id: str
    writer_group_identity: str
    evidence_manifest_digest: str  # SHA-256 of the canonical manifest bytes
    scope: ProbeScope
    verdict: ProbeVerdict
    evidence_paths: tuple[str, ...]
    reason: str

def combine_gates(
    results: tuple[GateResult, ...],
    manifests_by_digest: Mapping[str, bytes],
) -> ProbeVerdict:
    # Verify every used manifest/digest and binding to the run/SessionKey/
    # SandboxID/cgroup identity/scope, then aggregate. No proof, no PASS.
    ...
```

**Evidence Manifest v1 (test-only, canonical UTF-8 JSON):** Each Gate has one immutable manifest containing `schema`, `gate`, `probe_run_id`, `session_key` (3 elements, including matching `sandbox_id`), `sandbox_id`, `writer_group_identity`, `scope`, `verdict`, `observations` (executed operation, expected/observed outcome, evidence file SHA-256), `evidence_file_digests`, `runtime_participants` (actual OpenCode/approved Plugin/MCP versions and observed processes for full-runtime), and `reason`. Canonical encoding: UTF-8, `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`; `evidence_manifest_digest = sha256(canonical_manifest_bytes)`. The digest is not embedded within its own manifest. `writer_group_identity` records the observed cgroup-v2 mount/namespace identity, canonical cgroup path and directory inode within the same live Sandbox; the raw identity is recorded identically in all three Gates, not inferred from an arbitrary PID. Evidence paths must stay under the private PoC evidence directory; verify content SHA-256 before trusting the manifest.

**Aggregation contract:** Before any PASS, verify manifest SHA-256, every referenced evidence hash, exact `GateResult`↔Manifest field agreement and **identical** `probe_run_id`, `session_key`, `sandbox_id`, `writer_group_identity` across the three Gates. Reject duplicate/missing Gates, mixed Session/Sandbox/run identity, fixture presented as full-runtime, manifest mismatch, unknown outcomes or omitted negative probes as `NOT_VERIFIED` (never PASS). A **verified observed unsafe event belonging to the probe run** wins as `FAIL`, even if other Gates remain unexecuted. Mere absence of evidence is `NOT_VERIFIED`, not an observed failure. No test-only PASS produces a production Collection Digest or ApplyAuthorization.

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

- [ ] **Step 1 — RED:** Write tests `test_three_full_runtime_passes_required`, `test_fixture_pass_is_not_full_runtime_pass`, `test_missing_or_duplicate_gate_not_verified`, `test_mixed_probe_run_rejected`, `test_mixed_session_or_sandbox_rejected`, `test_writer_group_identity_mismatch_rejected`, `test_manifest_digest_mismatch_rejected`, `test_missing_evidence_file_not_verified`, `test_observed_escape_is_fail_even_when_other_gate_missing`, `test_digest_not_issued_on_failure`. Assert exact run/Session/Sandbox/Writer Group/manifest binding, verified-unsafe `FAIL` precedence, and incomplete-proof `NOT_VERIFIED`.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect failure because gate implementation is missing.
- [ ] **Step 3 — Minimal implementation:** Add the exact `GateResult`/Evidence Manifest v1 interface above and validation of Gate↔Manifest SHA-256, referenced evidence SHA-256, identity equality, fixture/full-runtime scope, Gate coverage, negative-probe outcomes and verified-unsafe `FAIL` precedence. Do not add launcher integration or production digest issuance.
- [ ] **Step 4 — Verify GREEN:** Re-run the same unit tests; expect named tests PASS.
- [ ] **Step 5 — Stop:** Record test results. Do not commit without separate Owner GitHub-write approval.

**Deliverable:** Offline test gate that cannot mistake fixture evidence or missing proof for full-runtime PASS.

### Task 2: Session Writer containment and escape proof

**Files:** Create `sandbox/tests/fixtures/f004_writer_tree.py`; extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/containment/`.

**Interfaces:** Consumes Task 1 gate evaluator. Produces containment evidence for `GateResult(gate='containment', ...)`.

- [ ] **Step 1 — RED:** Add tests `test_writer_attached_before_first_instruction`, `test_child_and_detached_grandchild_captured`, `test_writer_cgroup_migration_refused`, `test_privileged_socket_or_capability_escape_refused`, `test_unexamined_plugin_topology_not_verified`.
- [ ] **Step 2 — Verify RED:** Run `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect failures in newly added tests only.
- [ ] **Step 3 — Minimal fixture:** Implement synthetic parent/child/grandchild/background Writer, with instrumentation proving membership **before the first file write**. Assess an atomic spawn-into-cgroup primitive such as `clone3(CLONE_INTO_CGROUP)` under actual Sandbox permissions/seccomp; an after-spawn `echo PID > cgroup.procs` alone is insufficient. Do not install packages or broaden the mechanism if unavailable.
- [ ] **Step 4 — Authorized fixture pass:** Allocate a unique `probe_run_id`, SessionKey, SandboxID, Writer Group identity and private evidence directory. Launch the synthetic fixture under the Writer Group; collect `/proc/<pid>/cgroup`, creation/exit evidence, `cgroup.events`, UID/capabilities, socket exposure and migration-attempt results. Attempt out-of-group writes and privileged escape using **only disposable fixture files**. Observe `frozen 1` once all fixture writers are captured. Emit a `scope='fixture'` Evidence Manifest; do not label it full-runtime.
- [ ] **Step 5 — Separately observed full-runtime pass:** On the **same controlled probe run identity** and disposable Sandbox, start the *actual* approved OpenCode/Plugin/MCP process configuration with no credentials, no inference, no production repository and no unapproved configuration changes; verify the complete runtime topology including idle/detached/background children **before first write** and attempted cgroup migration/escape. Emit a separate `scope='full-runtime'` Evidence Manifest. If actual participants cannot be launched or their topology cannot be exhaustively observed, record full-runtime `NOT_VERIFIED` (not a fabricated PASS); observed unauthorized escape/write is `FAIL`. Do not promote the preceding fixture result.
- [ ] **Step 6 — Verify GREEN and classify:** Run `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; retain per-process evidence and output one containment GateResult. Stop if bypass observed or complete topology cannot be verified; do not start alternate mechanisms.

**Deliverable:** Evidence about pre-exec capture, descendants, migration/escape, and external writers; not just a Freeze test.

### Task 3: Enforced read-only Collector — fixture / full-runtime explicitly separated (F-004-P1)

**Files:** Create `sandbox/tests/fixtures/f004_collector.py`; extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/collector/`.

**Interfaces:** Consumes Task 2 containment evidence tied to the same `probe_run_id`, `session_key`, `sandbox_id`, `writer_group_identity`; produces a Collector `GateResult` and SHA-256-verified Evidence Manifest with explicit `scope='fixture'` or `scope='full-runtime'`.

- [ ] **Step 1 — RED:** Add tests `test_fixture_collector_reads_git_layers`, `test_fixture_index_object_worktree_writes_denied`, `test_fixture_rename_unlink_denied`, `test_fixture_writable_remount_denied`, `test_full_runtime_collector_boundary_required`, `test_no_full_runtime_collector_evidence_not_verified`, `test_manifest_identity_binding`.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect newly added tests to FAIL.
- [ ] **Step 3 — Establish enforcement (fixture):** Build an independent Collector process **outside Writer Group**, with a kernel-enforced read-only view of a **disposable Git repository** and writable staging elsewhere. Verify actual permissions, UID/capabilities and mount namespace; read-only environment flags or `GIT_OPTIONAL_LOCKS=0` do not prove enforcement. If mount/capability restriction is unsupported, record `NOT_VERIFIED`; do not silently substitute a weaker architecture.
- [ ] **Step 4 — Run fixture negative probes:** Against the disposable source only, attempt `open(O_WRONLY)`, Index update, Git Object creation, Working Tree modification, rename/unlink, remount writable and a child Writer from the Collector context. Record the observed errno/exit for each; **any actually successful forbidden source write or privilege bypass = `FAIL`**. Verify HEAD, raw Index hash, Git Objects, Working Tree and Untracked before/after; generate selected Bundle/Manifest only in staging. Emit immutable `scope='fixture'` evidence and manifest.
- [ ] **Step 5 — Run separate full-runtime Collector probe:** In **the same `probe_run_id`/SessionKey/SandboxID/Writer Group identity as Task 2 full-runtime**, start a new real approved OpenCode/Plugin/MCP runtime using **a disposable repository**. For this launch, verify **every Writer, including idle, detached and background descendants, is captured by Writer Group before its first write**; do not reuse Task 2's launch-specific capture evidence. Then verify that the **actual Collector invocation and its descendants** operate outside Writer Group with source kernel-enforced read-only and staging separate. Repeat the full prohibited-write matrix *from this actual Collector boundary*, capture observed denials and source hashes, and confirm the real runtime cannot remount, spawn a source Writer or bypass the Collector boundary. Never probe a live user repository. Emit a distinct `scope='full-runtime'` manifest, not an alias of fixture evidence.
- [ ] **Step 6 — Verify GREEN and classify:** Run `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; validate both manifests and binding fields. Fixture-only PASS is insufficient. If real Collector/runtime is unavailable, any negative probe is unexecuted, source write prevention is not enforceable, or evidence is missing, **full-runtime = `NOT_VERIFIED`** (unless an unsafe act was actually observed, in which case `FAIL`). Do not enable Collect.

**Deliverable:** Independent fixture and full-runtime evidence of non-writing Collector enforcement, or honest NOT_VERIFIED/FAIL without an architecture change.

### Task 4: Freeze → copy → consistency and PENDING preservation (F-004-P1/P2)

**Files:** Extend `sandbox/tests/test_oc2_f004_feasibility.py`; evidence `/tmp/oc2-f004-feasibility.*/consistency/`.

**Interfaces:** Consumes Tasks 2–3 evidence bound to **exactly the same `probe_run_id`, `session_key`, `sandbox_id`, and `writer_group_identity`**; emits a `GateResult(gate='consistency', ...)` with an independently hashed manifest. No production `collection_digest` or `ApplyAuthorization` is ever created.

- [ ] **Step 1 — RED:** Add tests `test_thaw_before_copy_complete_rejected`, `test_new_writer_during_copy_rejected`, `test_session_identity_change_rejected`, `test_mixed_probe_evidence_rejected`, `test_fixture_consistency_not_full_runtime_pass`, `test_untracked_mismatch_rejected`, `test_partial_copy_preserves_pending`, `test_verified_unsafe_failure_precedence`.
- [ ] **Step 2 — Verify RED:** `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`; expect failures only in new tests.
- [ ] **Step 3 — Implement test-only comparison:** Resolve one shared run/Session/Sandbox/Writer Group identity from Tasks 2/3, validate their manifests and evidence hashes, then check `frozen 1` and absence of external Writers **before staging, before `sbx cp`, after copy and immediately before simulated finalization**. Also require an enforced boundary that prevents thaw and external Writer writes for the entire copy interval, or independently verifiable evidence that detects any such violation through copy completion; checkpoints alone are insufficient. Compare HEAD/Branch, raw Index SHA-256, Staged/Unstaged/Untracked manifests, Bundle/Commit reachability, SHA-256 and `git fsck`. Missing/mixed evidence or inability to prove the copy-interval boundary is `NOT_VERIFIED`. A controlled injected thaw/new Writer is a negative-test input, not itself `FAIL`: require fail-closed `PENDING` and retained evidence. `FAIL` is limited to an unauthorized write, escape from containment, or inconsistent finalization.
- [ ] **Step 4 — Fixture-only negative tests:** With a disposable fixture repository, induce a controlled thaw/new Writer and interrupted/partial copy. Treat the injected event as a negative-test input and verify **no simulated finalization**, unchanged Guest originals, retained partial Host evidence and fail-closed `PENDING`/`GUEST_QUIESCENCE_UNVERIFIED`. The injection alone is not `FAIL`; an unauthorized write, escape from containment, or inconsistent finalization is `FAIL`. Save `scope='fixture'` evidence. Do not promote this PASS to full-runtime.
- [ ] **Step 5 — Separate full-runtime Freeze→Copy→Consistency:** Using **the same SessionKey/SandboxID/probe_run_id and Writer Group identity** as the full-runtime Task 2 containment and Task 3 real Collector probe, start a new approved OpenCode/Plugin/MCP runtime against a disposable repo. For this launch, verify every Writer, including idle, detached and background descendants, is captured by Writer Group before its first write; do not reuse Task 2/3 launch-specific capture evidence. Then block new Writers, freeze Group (`frozen 1`), invoke the actual read-only Collector to stage a Bundle/Index/Working Tree/Untracked manifest, and perform live-Sandbox `sbx cp` while the copy-interval protection/detection boundary remains active. Verify identity, freeze, boundary and hash checkpoints and Git consistency through copy completion and the **simulated** finalization gate. Do not issue real Collection Digest or ApplyAuthorization.
- [ ] **Step 6 — Failure preservation and GREEN:** Repeat one bounded controlled negative event (thaw/new Writer or copy failure) *only if permitted in the authorized full-runtime PoC*. Treat the injected event itself as a negative-test input; verify fail-closed `PENDING` and evidence retention. `FAIL` is limited to an unauthorized write, escape from containment, or inconsistent finalization. Execute `python3 -m unittest sandbox.tests.test_oc2_f004_feasibility -v`. Emit separate `scope='full-runtime'` evidence or `NOT_VERIFIED` if actual Runtime/Collector/Identity/copy-interval protection or violation-detection proof is unavailable. No automatic alternative route or more PoC runs.

**Deliverable:** Fixture and (when authorized/possible) real-runtime Freeze→Copy→Consistency evidence, with no unsafe promotion and PENDING/HOLD on incomplete proof.

### Task 5: One Human Owner decision checkpoint (no review loop)

**Files:** Future evidence only: `/tmp/oc2-f004-feasibility.*/decision.md`.

**Interfaces:** Consumes exactly the three **full-runtime** GateResults plus independently linked fixture evidence, returns one `PASS` / `FAIL` / `NOT_VERIFIED` verdict without generating any production authorization.

- [ ] **Step 1 — Check evidence:** Validate the three SHA-256 manifests and their recorded evidence file digests; require matching `probe_run_id`, `session_key`, `sandbox_id`, `writer_group_identity`, actual-runtime participants and negative-probe coverage. Coverage must show that controlled thaw/new-Writer injections fail closed to `PENDING` with evidence retained; the injected event itself is not `FAIL`. Aggregate by `probe_run_id`: a verified unauthorized write, containment escape, or inconsistent finalization is `FAIL`; missing/unexecuted negative probes or unverified evidence is `NOT_VERIFIED`, never `PASS`. Record separate fixture verdicts. Mixed identity or missing proof remains `NOT_VERIFIED`.
- [ ] **Step 2 — Report:** One compact table for containment, collector, consistency containing scope, identity, manifest digest, verdict and observed failures; distinguish fixture from real runtime.
- [ ] **Step 3 — Decide:** Three identity-consistent, evidence-complete full-runtime PASS Gates, including negative-probe coverage showing injected thaw/new-Writer events fail closed to `PENDING` with retained evidence → eligible for Owner consideration of a later implementation plan (**not** Implementation GO). Aggregate only evidence bound to the same `probe_run_id`; a verified unauthorized write, containment escape, or inconsistent finalization → FAIL/HOLD even with other Gates missing. Injected events alone are not FAIL. Missing/mixed evidence or omitted/unexecuted negative probes → NOT_VERIFIED/HOLD. Never generate production Collection Digest or ApplyAuthorization.
- [ ] **Step 4 — Stop:** Ask Human Owner for one decision. Do **not** automatically start implementation, new independent review, architecture alternatives, PR, or GitHub write.

## Completion / Stop Conditions

- **Review Gate document correction complete now:** F-004-P1 separates fixture and full-runtime in Tasks 3/4; F-004-P2 binds three GateResults to SHA-256 evidence manifests, one run/Session/Sandbox/Writer Group; F-004-P3 separates conditional Design document acceptance from final adoption, Plan execution and Implementation GO. No Source changes or Sandbox tests executed.
- **Feasibility PASS later:** All actual full-runtime Writer/Collector/Consistency gates are proven with kernel-backed evidence. This only permits a separate Owner judgment about implementation planning.
- **FAIL:** Observed escape, collector write, inconsistent state, lost data or unauthorized finalization; preserve Guest state and stop.
- **NOT_VERIFIED:** Cannot exercise actual runtime or prove an enforcement boundary. Preserve state, keep auto-Collect/Host Apply and Implementation GO on HOLD.
- **No loop:** One bounded test attempt for each unverified hypothesis. Do not repeat prior single-writer PoC or start review/correction sessions by default.

**Authorization record (F-004-P3):** Human Owner accepted Design R0.1.3 **as a document WITH BLOCKERS**; no final implementation-ready Design adoption or residual-risk acceptance is inferred. The earlier `writing-plans` request and explicit Plan `commit,push` authorized drafting and publishing the previous Plan, **not execution**. This Review Gate authorizes **document-only limited correction**; it does **not** authorize PoC/Sandbox actions, Production implementation, Host Apply, Credential changes, further GitHub Commit/Push/PR/Merge, or a new review. The next step is one Human Owner decision checkpoint.
