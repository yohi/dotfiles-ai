# OC2 Daily Launcher — F-004 Alternative A Stage 2 Full-runtime Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` **only after separate Human Owner execution authorization**. Execute approved tasks one by one; do not automatically dispatch subagents, request extra independent reviews, implement production code, commit, push, create PRs, or launch subsequent tasks. All steps below are **unchecked** because this request authorizes planning only.

**Goal:** Determine whether Alternative A (an unprivileged Writer container inside a Mountless Docker Sandbox) preserves writer isolation, authentic OpenCode v2/Plugin/MCP/TUI/proxy operation, and safe read-only Git collection under the **actual configured runtime**, without enabling production automatic Collect or Host Apply.

**Architecture:** The trusted Guest Supervisor runs outside the unprivileged Writer container and owns its start/stop/identity checks. OpenCode, allowed Plugins/MCP, descendants, and background jobs run inside the Writer container. An independent non-writing Collector reads the same Guest-local Git repository only after a verified stop and stages evidence for `sbx cp` while the outer Sandbox remains running. This is an **Alternative A feasibility candidate**, not yet an adopted replacement for Design R0.1.3's Freezer mechanism.

**Tech Stack:** Ubuntu Server 26.04; Docker Sandboxes Mountless (observed v0.53.0 in preceding PoCs); Guest Linux 7.0.14 / Docker 29.9.3 as *Stage 1 observations*; Docker containers, Git, Python 3, `unittest`; pinned OpenCode v2.2.5; existing OC2 APM/asset validation.

**Spec / References:**
- `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md`, Design R0.1.3, blob `bb4218078c5dcb4c609fe0c8d77fe778ee1ebbfa` (§5–§12).
- `docs/superpowers/plans/2026-11-13-oc2-f004-quiescence-feasibility.md`, last reviewed at `0c9d5962dfa0d2fa430d874a38fb0faf8ec947e8`, blob `b9168ef3b322c6527275a2863c3e2435493bf07f`.
- Existing implementation reference: `sandbox/scripts/oc2.py` (`VERSION='2.2.5'`, `PINNED=('/opt/oc2/bin/opencode',)`, `SandboxLaunch`, `launch`, `GUEST_EXEC_WRAPPER`, `Runner.sbx`); `oc2_guest.py`, `oc2_native.py`, `oc2_session.py`, `oc2_workspace.py`; existing offline tests under `sandbox/tests/`.
- Stage 1 report and decision **as reported by the Human Owner**, not independently read from local `/tmp`: `oc2-f004-altA-20261113235350`, adopted run `altas1-20261114000321`, evidence `/tmp/oc2-f004-altA-stage1.pR6nvF/`, report `/tmp/oc2-f004-altA-stage1-report.md`.

## Authority and Current Status

| Decision | Status |
| --- | --- |
| Original F-004 cgroup-Freezer containment approach | `FEASIBILITY_FAILED` (unchanged) |
| Stage 1 Alternative A | `FIXTURE_PASS_WITH_LIMITATIONS` **based on the reported evidence** |
| Run 1 | `ABORTED` (driver/probe error) |
| Run 2 | `ABORTED — instrumentation false-positive`, **accepted with limitations**; preserve original flagged evidence, do not relabel as PASS |
| Run 3 | A–D `PASS`, `scope=fixture` only; Stop Gate B manifest was **not** verified by the old evaluator |
| Stage 2 full-runtime | `NOT_VERIFIED` |
| This task | **PLAN_ONLY** — create this document; **no execution authorization** |
| Production implementation / automatic Collect / Host Apply | **HOLD** |
| `collection_digest` / `ApplyAuthorization` | **NEVER issue in this PoC** |

Design R0.1.3 §6/§10.1 presently specifies a cgroup Freezer mechanism whose original feasibility failed. **This Plan does not silently amend or adopt a new normative design.** A successful Alternative A Stage 2 is evidence for a future **separate Owner decision** on a limited Design change and production implementation planning. Do not represent existing Design/Plan as already requiring a Docker Writer container.

## Global Constraints

- Preserve the overall project goal: a developer runs `oc2` at a Git repository root; Host stays Mountless; Owner-controlled apply remains a separate authority.
- Do not use an existing project repository, production credentials, existing Sandbox/worktree, or recorded Stage 1 files as test substrates. Do not mutate `oc2-f004-altA-20261113235350` or earlier F-004 PoC Sandboxes.
- Future dynamic work requires **a separately approved, new, disposable, credential-free Sandbox at the outset**. Any network-policy change, credential/proxy binding, actual provider call or chargeable inference requires a further **explicit scoped approval** before that operation; this Plan alone grants none.
- No Host Git writes or Workspace mount; no Host `.git` mount; no Host Apply, Credential modification, `sudo`/`docker` group changes to the existing Guest `agent` user, or arbitrary external network exposure.
- Unprivileged Writer: dedicated UID, `--cap-drop ALL`, `no-new-privileges`, no `docker.sock`, no Engine TCP access, no Supervisor PID/mount/control access, minimal RW mounts, `restart=no`, bounded PIDs, verified image digest; never use `--privileged` or host namespace sharing.
- Supervisor/Collector must not execute Git operations as root against a Writer-controlled RW directory. Collector uses a kernel-enforced read-only repository view, restricted capabilities/egress, independent staging output, and constrained path traversal.
- `docker stop` ending with SIGKILL/137 is **not proof of repository consistency**. Verify stopped PID/identity plus Git Index, refs, objects, staged/unstaged/untracked contents and recovery flags.
- Do not stop the **outer** Sandbox before `sbx cp` (prior evidence: this can restart it). Never allow a second writer or a mutable source during collection.
- Preserve APM SSOT, trusted Version/Artifact Identity, Guest runtime configuration boundaries, approved Plugin/MCP set and Host Credential Proxy semantics. Do not assume the older `oc2.py` already implements future Design v3 Session and Host Apply contracts.
- Evidence lives only in a new private `0700` directory outside repositories (e.g. `/tmp/oc2-f004-altA-stage2.<unique>/`), with file modes `0600` as appropriate. Record hashes, redact tokens/headers/auth DB/private data, and preserve all aborted/failed attempts; do not change prior PoC evidence.
- One bounded attempt **per distinct hypothesis**; retry only for an independently identified instrumentation defect that is **not** an observed security failure, and only under the authorized attempt budget. Observed prohibited operation → **FAIL and STOP**, not retest to wash out the failure.

## Scope Definitions, Identities and Verdicts

Use four evidence scopes, never coerce one into another:

- `fixture`: synthetic Writer, fake process or mock protocol; Stage 1 scope only.
- `runtime-offline`: genuine, pinned OpenCode executable and approved local Plugin/MCP artifacts, but no external network, credential, or paid inference. Does not prove proxy/model operation.
- `runtime-networked-no-inference`: same real executable/process topology plus a specifically authorized controlled egress/proxy path, but no chargeable inference; mock endpoints are identified as mocks.
- `full-runtime`: genuine enabled approved OpenCode/Plugin/MCP topology with required TUI, network/credential proxy and real request/response behavior under a **separate explicit Owner approval** of external inference and any charge. If a required configured component is absent or disabled, declare coverage limitations; do not implicitly enable another Plugin/MCP.

Every gate (including the previously omitted Stop gate) MUST have a canonical evidence manifest with:

```python
from dataclasses import dataclass
from typing import Literal

Verdict = Literal['PASS', 'FAIL', 'NOT_VERIFIED']
Scope = Literal['fixture', 'runtime-offline', 'runtime-networked-no-inference', 'full-runtime']
GateName = Literal['runtime', 'network', 'containment', 'stop', 'collector', 'consistency']

@dataclass(frozen=True)
class GateEvidence:
    gate: GateName
    probe_run_id: str
    session_key: tuple[str, str, str]  # WorkspaceID, SandboxID, SessionGeneration
    sandbox_id: str
    boot_id: str
    writer_container_id: str
    writer_cgroup_identity: str
    writer_image_digest: str
    runtime_identity: str
    plugin_mcp_manifest_digest: str
    scope: Scope
    evidence_manifest_digest: str  # SHA-256 of canonical manifest bytes
    verdict: Verdict
    evidence_paths: tuple[str, ...]
    reason: str
```

Manifest MUST separately list: approved model/provider identifiers (no tokens), runtime version/binary digest, active Plugin and MCP IDs/versions, proxy route classification, process/cgroup records, mount/namespace/capability records, Git OIDs, index SHA, per-file content hashes, test start/end UTC, observed syscalls/exit status, and **evidence-file digests**. Hash the final manifest's canonical payload (without recursive self-digest) and verify all referenced files. A raw PID/UID alone is not identity. Reconcile all gates to **one run, Sandbox, boot, SessionKey, Writer container/cgroup, runtime and Plugin/MCP inventory**. If components must be restarted, document the generation transition and treat it as a new probe run; do not merge runs into a PASS.

**Verdicts:** A real observed unauthorized write, cgroup/namespace/container escape, reachable Engine control API, unexpected external inference, or incorrect success finalization is `FAIL`. Missing evidence, unavailable infrastructure, missing actual configured participant, unverifiable manifest, unapproved live credential/inference, or unexecuted gate is `NOT_VERIFIED`. A verified `FAIL` takes priority in overall classification; `PASS` requires all required gates within the *same scope and identity*. Do not issue production `collection_digest` or `ApplyAuthorization` even when Stage 2 gates pass.

## File Map (future work, not executed now)

- **Read-only production references:** `sandbox/scripts/oc2.py`, `oc2_guest.py`, `oc2_native.py`, `oc2_workspace.py`, `oc2_session.py`, `sandbox/tests/test_oc2.py`, `sandbox/tests/test_oc2_e2e.py`.
- **New disposable evidence/test files only after authorization:** `/tmp/oc2-f004-altA-stage2.<unique>/gate_schema.py`, `test_gate_schema.py`, `runtime_launcher.py`, `network_probe.py`, `process_probe.py`, `collector_probe.py`, `consistency_probe.py`, `decision.md` (test-only). Paths are the work product for the PoC; **none are production modules or GitHub changes**.
- **Input assets:** trusted, separately verified OpenCode v2.2.5 binary/Runtime; previously approved APM Full SSOT and permitted Plugin/MCP artifacts, staged without secrets; do not download arbitrary substitutes or use the Stage 1 `docker import /usr /etc` test image as a trusted production artifact.

## Review Focus — Five Negative Cases to Pin in Tests

1. A plugin/MCP child accesses the Engine through a bridge gateway, UNIX socket, ambient proxy, or DNS rebinding → `FAIL`, no collector/Apply.
2. Two PTYs or background process survives TUI exit/container stop, writes to shared RW repository → `FAIL`, preserve original.
3. Collector parses Writer-controlled `.git/config`, hooks, fsmonitor, filter, symlink/hardlink to execute code or escape source root → reject, preserve evidence.
4. `SIGKILL(137)` interrupts Git index/ref/object writes; `git fsck` succeeds while index or untracked representation is damaged → `NOT_VERIFIED`/`PENDING`, never confirm collection.
5. Engine-created bind mount appears in `docker diff` after start (Stage 1 run 2) → distinguish an attested pre-workload Engine operation from a true Writer write; never allowlist arbitrary post-baseline changes.

---

### Task 1 — Offline evidence contract and runtime prerequisites

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/gate_schema.py`, `test_gate_schema.py`; existing OC2 scripts **read-only**.

**Interfaces:** `GateEvidence`, `validate_gate_manifest(gate: GateEvidence, root: Path) -> Verdict`, `combine_run_gates(gates: tuple[GateEvidence, ...], scope: Scope) -> Verdict` (test-only). Produces one complete provenance record consumed by Tasks 2–5.

- [ ] **Step 1 (RED):** Write tests named `test_all_six_gates_required`, `test_stop_gate_manifest_required`, `test_mixed_run_or_boot_rejected`, `test_missing_real_mcp_not_promoted`, `test_observed_failure_precedence`, `test_modified_evidence_sha_rejected`, `test_run2_engine_mount_is_not_automatically_allowlisted`.
- [ ] **Step 2:** Run `python3 -m unittest -v test_gate_schema.py` **in the disposable evidence directory**; expected RED only for missing test-only helpers.
- [ ] **Step 3:** Implement the test-only schema and deterministic canonical manifest/digest verification. Record `source=reported` for Stage 1 prior evidence; do not claim it was independently revalidated.
- [ ] **Step 4:** Run the same command; expected GREEN for new tests. Do not change repository test modules.
- [ ] **Step 5:** Prepare the target-runtime inventory **without invoking credentials**: pinned binary digest, actual APM-selected Plugin/MCP enablement, runtime directory, executable dependencies, PTY requirements, proxy/CA injection points, expected network domains. If trusted assets/versions unavailable, mark dependent gates `NOT_VERIFIED` and stop before ad hoc downloads.

**Deliverable:** A full-runtime coverage matrix and evidence validator including **Gate B / stop**.

### Task 2 — Genuine Runtime, Plugin/MCP and TUI in an isolated Writer container

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/runtime_launcher.py`, `process_probe.py`; no repository edits.

**Interfaces:** Consumes Task 1 inventory, emits `GateEvidence(gate='runtime'...)` and `GateEvidence(gate='containment'...)` plus a frozen process inventory. Preserve original trusted artifact and `Runtime Identity` rather than rebuilding an unpinned OpenCode binary.

- [ ] **Step 1 (RED):** Define test assertions for exact OpenCode version+binary digest, Plugin/MCP inventory coverage, no allowed executable outside the Writer container, all spawned grandchildren and background jobs in the same container/cgroup, TUI terminal sizing/resize/SIGINT/SIGTERM, and forbidden Supervisor/Engine access. Record expected failure on any missing testable capability.
- [ ] **Step 2:** Establish **one new disposable Mountless Sandbox**, a separate container image with verified digest, and a dedicated Writer container with `--cap-drop ALL`, `no-new-privileges`, `--pids-limit`, `restart=no`, no Docker socket and no Host namespace sharing. Use only the approved, sanitized test repository. Check Writer cgroup identity **before runtime process execution**.
- [ ] **Step 3:** Start the **actual pinned OpenCode CLI** inside the Writer container using a controlled PTY. Verify stdin/stdout, terminal resize, process exit/signal behavior and that all configured enabled Plugin/MCP children are actually present and inside the boundary. Real providers/Plugin/MCP omitted because of missing credentials remain `NOT_VERIFIED`; a fake binary/script or mock Plugin cannot satisfy this gate.
- [ ] **Step 4:** Probe `sudo`, setuid, socket/path discovery, Engine TCP, cgroup writes, mount/namespace operations, and privileged Supervisor access through controlled non-destructive tests. The initial Stage 1 `--network none` outcome does **not** establish this result after networking is enabled.
- [ ] **Step 5:** Verify all test assertions, process/cgroup/namespace/capability records and immutable artifact hashes; emit appropriately scoped evidence. Observed bypass → **FAIL and STOP**.

**Deliverable:** Actual runtime/TUI/process topology evidence, or explicit `NOT_VERIFIED` where configured components were not exercised.

### Task 3 — Network, Credential Proxy and MCP reachability with separate grants

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/network_probe.py`; existing APM/Guest wrapper read-only.

**Interfaces:** Consumes same run/session/container identity from Task 2; produces `GateEvidence(gate='network'...)` with explicit `scope` and `authorization_record` identifier (no secret material).

- [ ] **Step 1 (RED):** Test expectations: only approved proxy route is usable; no raw Engine API/bridge access; no DNS or socket bypass; no credentials exposed to Writer environment, image, filesystem, logs or manifest; specified CA and proxy variables match the existing `GUEST_EXEC_WRAPPER` contract; permitted MCP endpoint reachable without exposing a Supervisor control socket.
- [ ] **Step 2:** First run **offline-only** validations and classify the network gate `NOT_VERIFIED` for full-runtime. Avoid reclassifying the previous `--network none` probe as an online security proof.
- [ ] **Step 3 — Authorization gate:** **STOP unless** Human Owner separately authorizes a specific network policy, proxy/CA binding, destination set and permitted credential use. No implicit permission from Stage 2 Plan approval or Sandbox availability; no paid inference by default.
- [ ] **Step 4 (only if separately approved):** Enable the narrowly approved egress, confirm traffic reaches only the intended proxy and that Engine TCP, Docker socket, host-network access, and unexpected DNS are rejected. Inspect both network paths and container-visible certificate trust without printing credential bytes. Any reachable Engine control endpoint or uncontrolled external request is **FAIL**.
- [ ] **Step 5 (independent inference gate):** A live provider request, token acquisition/refresh, or chargeable model call requires **another explicit authorization specifying Provider/Model/Account/Workspace, usage limit and credential binding**. Without it, keep real-inference behavior `NOT_VERIFIED`; mock responses prove plumbing, not provider correctness. Never automatically use an existing OAuth session or import Host credentials.

**Deliverable:** Separately evidenced `runtime-offline`, controlled network, and optional explicitly approved live-provider outcomes. **Do not call it full-runtime PASS** if any required branch is missing.

### Task 4 — Verified stop and strictly non-writing Collector

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/collector_probe.py`; source repository only a disposable test fixture.

**Interfaces:** Consumes exact Task 2–3 container, SessionKey and Plugin/MCP identity; produces **two** independently hashed gates: `stop` and `collector`.

- [ ] **Step 1 (RED):** Add tests for `restart=no`, `exited/Pid=0` with PID/cgroup/namespace verification, no external Writer and no RW path remaining; plus Collector `O_WRONLY`, rename, unlink, remount, index/object mutation rejection; symlink/hardlink/path-escape and unsafe Git config cases.
- [ ] **Step 2:** Block Plugin/MCP restart/respawn paths; exercise the actual runtime's shutdown and `docker stop` once. Distinguish clean TERM exit from SIGKILL/137; log signals, state and process descendants. Repeat no stopped-container test that restarts the outer Sandbox.
- [ ] **Step 3:** Verify Writer container exited, no restart, cgroup/identity no longer executing, no external Writer can modify the source, and all shared RW mount paths are inventoried. UID-based absence and 20-second hash stability are **supporting evidence only**, not sole proof.
- [ ] **Step 4:** From a separate, nonroot Collector with kernel-enforced read-only source and a distinct writable staging area, perform Git reads. Treat `.git/config` / hooks / filters / fsmonitor as untrusted; disable user/system config inheritance where possible and prevent execution via no-network + limited capabilities. **Any root Git read on Writer-controlled RW source is prohibited**.
- [ ] **Step 5:** Reject symlink and hardlink escapes using descriptor-relative, no-follow traversal and inode/dev/link-count checks; if an untrusted hardlink outside the fixture cannot be ruled out, mark the related proof `NOT_VERIFIED`. Run forbidden write/remount negative probes and compare source raw index/object/ref/file digests before and after.
- [ ] **Step 6:** Independently verify canonical **Stop gate evidence manifest** (Stage 1 B gap) and Collector manifest, both bound to the same run/Session/Container/boot identity. Any successful forbidden write or surviving Writer → **FAIL and STOP**.

**Deliverable:** Real topology stop assurance and kernel-enforced Collector evidence, including an explicit treatment of forced SIGKILL.

### Task 5 — Collection consistency, forced-kill safety and finalization prohibition

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/consistency_probe.py`; independent evidence and staging directories only.

**Interfaces:** Consumes the validated `runtime`, `network`, `containment`, `stop`, `collector` gates from **one** matching run; produces `GateEvidence(gate='consistency'...)` but **never** a production Collection Digest or ApplyAuthorization.

- [ ] **Step 1 (RED):** Tests for raw Index corruption despite `git fsck` success, Git write interrupted by SIGKILL, unstaged/untracked mismatch, cross-run evidence mixing, copy truncation, runtime identity change, unexpected post-stop Writer or changed mount identity, and premature simulated finalization.
- [ ] **Step 2:** With the verified stopped Writer and read-only Collector, record HEAD/Branch/Parent OIDs, selected Commit Bundle reachability, raw Index SHA, staged/unstaged/untracked file sets, file modes, symlink and hardlink declarations, Git objects and raw file hashes. Stage outside repository and transfer using `sbx cp` while **outer Sandbox remains running**.
- [ ] **Step 3:** Recheck the same complete manifest and cgroup/container/boot/Session identity before staging, before/after copy, and before **simulated** finalization. Include `git fsck` but do not treat it as a substitute for Index parsing, ref/mode integrity and complete Working Tree capture.
- [ ] **Step 4:** On a *separate permitted disposable test generation*, create a Git update-in-progress and induce a single controlled SIGKILL to check that incomplete Index/object/ref state becomes `PENDING` and remains recoverable as original evidence. **Do not run fault injection on a valuable repository, and do not retry after observed unauthorized source mutation.**
- [ ] **Step 5:** Verify GREEN on deterministic tests and preserve evidence for all attempts. The only successful output is a *test-only* consistency verdict tied to the same run and scope; no real Collection Digest, Host Apply, or ApplyAuthorization is issued.

**Deliverable:** Evidence that the actual permitted Runtime can be collected consistently, or `NOT_VERIFIED`/`FAIL` with preserved originals.

### Task 6 — One Human Owner checkpoint and stop

**Files:** `/tmp/oc2-f004-altA-stage2.<unique>/decision.md` (future approved execution only).

**Interfaces:** Consumes six individually validated GateEvidence records, full inventory and any aborted-run evidence; outputs one overall verdict and a clearly limited next decision.

- [ ] **Step 1:** Verify all Gate manifests, file hashes, immutable run/session/container/boot/image/Runtime/Plugin identities and recorded authorization boundaries. Separately record every fixture/offline/networked/mock result; do not aggregate incompatible scopes.
- [ ] **Step 2:** Produce a 6-gate table (`runtime`, `network`, `containment`, `stop`, `collector`, `consistency`) with `PASS`/`FAIL`/`NOT_VERIFIED`, actual scope, exact evidence digest and concrete cause. Record Stage 1 run 2 reclassification **with limitations** as historical evidence, not full-runtime evidence.
- [ ] **Step 3:** One observed unsafe bypass or prohibited write → **FAIL** and HOLD; otherwise any missing full-runtime component or evidence → `NOT_VERIFIED` and HOLD; only six identity-consistent genuine `full-runtime` gates PASS → **candidate for Owner deliberation**, not Production GO.
- [ ] **Step 4:** Return to Human Owner for whether to adopt Alternative A, authorize a limited Design change, plan production implementation, or HOLD. **Stop**. No PR/commit/push, next-stage execution, additional reviews, Sandbox deletion, or automatic architectural fallback.

**Deliverable:** One evidence-linked Owner decision record with explicit HOLD status and no automatic subsequent task.

## Success, Failure and Stop Conditions

**This document is complete when** the scope and evidence gates above permit an implementer to run a *separately authorized* Stage 2 without making unstated security/architecture decisions. The fact it exists does **not** authorize the test.

**Actual Stage 2 PASS (future, not claimed):** All genuine enabled approved Runtime/Plugin/MCP processes, permitted TUI and model/proxy paths, stop/quiescence, independent Collector and consistency must be observed under one stable proof scope and correlated identity, with all negative probes rejected. A `runtime-offline` PASS is useful but not a `full-runtime` PASS.

**Observed FAIL:** Successful escape or Engine control, collector write, data integrity violation, unwanted external inference, unauthorized finalization or other observed unsafe behavior. Preserve Sandbox and evidence; HOLD.

**NOT_VERIFIED:** Missing/disabled required runtime participant, network/inference not authorized, unexecuted test, failed evidence verification or inability to observe. Preserve artifacts; HOLD. Do not use unverified `runtime-offline` results to claim production safety.

**Owner authorization boundaries:** Current approval = Stage 1 `ACCEPT_WITH_LIMITATIONS`, and **Stage 2 Plan creation only**. Future Stage 2 execution, network/credential/chargeable inference, Production implementation, repository changes, Host Apply, GitHub writes, new review and disposal each require separate approval. This plan neither updates Design R0.1.3 nor overrides the original F-004 mechanism FAIL.
