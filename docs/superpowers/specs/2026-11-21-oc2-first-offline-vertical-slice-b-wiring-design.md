# OC2 — First Offline Vertical Slice B Wiring Design R0.1.3

- Date: 2026-11-21 (JST)
- Repository: `yohi/dotfiles-ai`
- Base: `master@34d0c023925d01f2bb4f91a5b61ee7c871c4a5df` (merged PR #191)
- Status: **DESIGN_LIMITED_CORRECTION / OWNER_ADOPTION_PENDING / IMPLEMENTATION_NOT_AUTHORIZED / LIVE_ACCEPTANCE_NOT_RUN**
- Reviewed HEAD: `feature/oc2-slice-b-offline-e2e-wiring-design-20261121@61d954d0221e7e36d1c903d7c300124de2f4b742` (existing committed Design R0.1.2 and Plan R0.1.1). Earlier `8ae1d916b830ee2cfa6355429321f7583e13739c` is historical, not the current reviewed baseline.
- Revision: **R0.1.3 — RG-OC2-B-003 conditional preservation completion and RG-OC2-B-006 Writer identity binding only; prior RG-OC2-B-001/002/004/005 retained**
- Scope: **Local limited corrections to this existing Design and its paired Implementation Plan only; no GitHub write or source/test execution.**
- Parent: [OC2 Daily Launcher Design R0.2](2026-11-13-oc2-daily-launcher-design.md)
- Existing bounded contract: [Alternative A — Vertical Slice B Integration Design R0.1.5](2026-11-16-oc2-alternative-a-vertical-slice-b-design.md)
- Existing plan (historical task scope; not automatically reauthorized): [Vertical Slice B Implementation Plan R0.1.2](../plans/2026-11-16-oc2-alternative-a-vertical-slice-b-implementation-plan.md)

## 1. Intent and completion boundary

The product goal remains: from a repository root, run `oc2` to use an isolated OpenCode development environment, safely retain work when stopping, and eventually resume daily development. This document **does not** claim that daily operation is complete.

The immediate objective is **two separately tested contracts**: production `oc2 --slice-b` always returns fixed HOLD, while the Python offline test harness directly invokes a dependency-injected E2E joining Git Baseline, Session/Guest Authority, simulated Writer/TUI and Host Lifecycle. The CLI never executes that Fake E2E. Implement only missing wiring, not a new Host/Guest architecture.

**Done for this slice** means: a failing integration test is observed first, the minimum wiring makes it pass, relevant existing offline regression tests pass, and the end-to-end flow can be demonstrated without a real Host, VM, Docker, Sandbox, credentials, provider, or network. Completion is **offline readiness only**, followed by a Human Owner checkpoint.

**Not done** means: no verified real isolation, no production TUI acceptance, no proof that Guest original data survives a real Host shutdown, no automatic Collect/Apply, no production daily-launcher completion, and no authority to start a later task.

## 2. Approach decision from brainstorming

| Approach | Trade-off | Decision |
| --- | --- | --- |
| A. CLI-to-Git-admission only | Lowest implementation cost but does not exercise the Writer/stop lifecycle | Not chosen for this slice |
| **B. Offline E2E wiring using existing Slice B components** | Tests integration and fail-closed transitions without treating mocks as live proof | **Selected for this design; Owner design adoption pending** |
| C. Directly enable daily Collect/Apply | Apparent convenience, but bypasses unaccepted isolation/preservation requirements | Rejected |

The previous brainstorming selected **B** as the recommended first slice. This document specifies that choice. It does not amend the parent design's production contract or grant approval for broader Slice B execution.

## 3. Existing implementation, observed gaps, and ownership

| Existing component on base `master` | Reuse | Missing for the first slice |
| --- | --- | --- |
| `bin/oc2` | Keep its repo-root resolution and `oc2.py` exec unchanged | None |
| `sandbox/scripts/oc2.py` | Keep normal Phase 1–5 launch, all current options, and legacy tests | No `--slice-b` dispatcher; normal path still uses fixed `oc2-v2` and rejects an existing name |
| `oc2_slice_b_git.py` | `admit_clean_repo`, `recheck_host_baseline`, existing bounded Bundle/Manifest helpers | Connect them to orchestration, do not recreate Git transport |
| `oc2_slice_b_session.py` | Immutable `SliceBReceipt`, `VerifiedSliceBReceipt`, `VerifiedGuestAuthority`, identity-bound start data | Connect only through existing verified construction/validation boundaries |
| `oc2_slice_b_image_*.py` | Source/Archive/Image Record/Config-ID validation for mode A | Inject a fake for orchestration tests; real Host build/load remains unaccepted |
| `oc2_writer.py`, `oc2_supervisor.py`, `oc2_slice_b_transport.py`, `sandbox/oc2_slice_b/entrypoint.py` | Fixed one-Writer/one-PID1 TUI/fixture and attach identity constraints, already unit-tested | Connect one offline scenario via injected effects, not privileged production operation |
| `oc2_host_lifecycle.py`, `oc2_host_provider.py` | Conservative stop/retry and isolation checks | Integration result must not upgrade the provider's unknown autostart/restart/shared-write observations |
| `oc2_workspace.py`, `oc2_workspace_ops.py`, `oc2_session.py` | Preserve existing snapshot and legacy apply behavior for the existing launcher | They are **not** a Git baseline/Collector/Host Apply implementation for Slice B |

PR #191 delivered offline Host lifecycle/preservation components, not a live accepted runtime. Its recorded Host isolation, Writer runtime and GuestFS/offline-preservation acceptance remain `NOT_RUN` or `NOT_VERIFIED` where stated; merging code did not change these evidence states.

## 4. Proposed narrow architecture

```text
bin/oc2 -> oc2.py
  |-- no --slice-b: existing Phase 1–5 behavior unchanged
  `-- effective raw argv contains --slice-b (also --slice-b=...):
       fixed Production HOLD **before argparse**
       even with --help/--version/unknown/--dry-run
       SLICE_B_LIVE_NOT_ACCEPTED; return 1; no runtime effects

Python unittest only (not reachable from CLI flags or environment):
  -> run_slice_b(repo_root, workspace, sandbox_name, *, dry_run, ops=FakeSliceBOps)
       |-- verified clean Git Baseline + Bundle/Manifest
       |-- imported Guest actual Git re-observed pre-authority/pre-Writer
       |-- private Host Receipt + verified Guest authority
       |-- same-Session Fake Writer/TUI/fixture
       |-- FakeHostControl lifecycle event order
       `-- test-only OFFLINE_FAKE_PASS / PENDING /
           PRESERVATION_UNVERIFIED / REJECTED;
           production Receipt remains in existing schema;
           no real Host Isolation PASS, Collector or Apply

NO real Host/VM/Docker/sbx, Credential, Inference, Collector, Apply.
```

### 4.1 Entry and selection contract — RG-OC2-B-004

1. In `oc2.py` `main(argv: list[str] | None = None) -> int`, derive the **effective raw arguments** from explicit `argv` or `sys.argv[1:]` **before constructing `argparse.ArgumentParser` or calling `parse_args()`**. If any token is exactly `--slice-b` or begins `--slice-b=`, **return `1`** after writing exactly `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED\n` to stderr. Do not emit help/version/normal runtime text to stdout; do not import/call `run_slice_b`, create `SliceBOps` or access infrastructure. This is an early fixed HOLD, **not** a dispatch to the internal harness.
2. Selector precedence is unconditional, including `oc2 --slice-b`, `--slice-b --dry-run`, `--slice-b --help`, `--slice-b --version`, `--slice-b --unknown`, incompatible credential/inference/provisioning flags and `--slice-b=...`. Exact standalone `--slice-b` after `--` is also conservatively HOLD. No Fake flag/environment value or extra option can bypass it. No combination may fall through to ordinary launch.
3. **Without a Slice B selector**, retain existing `argparse` behavior: `--help` and `--version` print normal information and raise `SystemExit(0)`; unknown args use the normal argparse error diagnostic and raise `SystemExit(2)`. The no-flag Phase 1–5 launcher behavior remains unchanged. No new parsing rules affect legacy invocations.
4. CLI negative tests assert exit/exception, exact diagnostic class and stdout/stderr, and **zero runtime/Host effects separately**. All selector cases use fixed `return 1`/fixed stderr rather than argparse exit `0`/`2`; legacy help/version/unknown follow the original argparse outcomes. All cases, including informational and invalid options, are side-effect-free with respect to Runtime/Host/VM/Docker/credentials.

### 4.2 Integration boundary, not reimplementation

Create `sandbox/scripts/oc2_slice_b.py` only for orchestration and bounded outcome mapping. **Reuse Plan Task 6's exact interface:** `def run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int`. The `SliceBOps` protocol wraps only explicit operations and has no default real or Fake implementation. Keep existing validation, trusted authority creation, Writer spec, TTY frame protocol, Session receipt schema, Host isolation, and preservation logic in their existing modules.

Only a **Python test harness** (Plan Task 6 target `sandbox/tests/test_oc2_slice_b_adapter.py`) invokes `run_slice_b(..., ops=fake)` directly, with explicitly supplied `SliceBOps` Fake ports and deterministic event recording. Production `oc2.py` never instantiates these Fake ports or invokes `run_slice_b`, including for `--dry-run`. No injection via user CLI flags, environment variables, generic shell port or privileged fallback. Real adapters remain disabled; no delegation to legacy `sbx exec` or `_session_action`. Test-local Git fixture activity is permitted; real Host lifecycle/VM/Docker/sbx calls are forbidden.

Trusted authority is **never** constructed from arbitrary Guest-reported identity. Use the existing `GuestAuthorityVerificationRequest` and `verify_guest_authority_from_host_record(request, runner)` with `FakeGuestImageRunner` from `sandbox/tests/oc2_slice_b_test_support.py` in the offline harness. Issue `VerifiedGuestAuthority` only after existing Host Receipt/Manifest, Archive/Config-ID, Runtime/Image Record, SessionKey and a **fresh independent real Guest Git observation** succeed. `verify_guest_authority_from_host_record()` validates the supplied `GuestBaseline` against the Receipt but **does not re-read actual Guest Git**; never treat its invocation as proof the repository is still unchanged. Immediately after `import_guest_baseline()` completes, re-run `admit_clean_repo(guest_repo)` and compare the returned `GitBaseline` with the imported frozen Guest baseline (including root, HEAD, tree, ref, Index and worktree). Immediately **before** `ops.run_writer`, call `recheck_host_baseline(host_baseline)` and `recheck_host_baseline(imported_guest_baseline)` again. In both phases reject independently observed drift **before Writer** with `REJECTED`/`OBSERVED_MISMATCH`, retaining Guest original and Session evidence when created. Keep full Writer Container ID/StartedAt correlation. No forged sealed authority, mutable Guest `.git` expected identity or bare Docker image tag may substitute for those checks.

**Writer observation binding — RG-OC2-B-006:** After the single injected `ops.run_writer` returns, the Orchestrator must validate `SliceBWriterObservation.identity` against the same sealed `VerifiedGuestAuthority` **before accepting the Fake TUI/fixture or requesting a stop outcome**. Require `WriterIdentity.container_id` to be exactly 64 lowercase hexadecimal characters (full CID, never a name/short ID); require `WriterIdentity.image_id` to be exactly `authority.image_config_id` (the pinned `sha256:` + 64 lowercase-hex Image Config ID, not the image tag or Archive SHA); require `WriterIdentity.started_at` to be a nonempty, non-zero-sentinel, valid UTC RFC3339 timestamp `YYYY-MM-DDTHH:MM:SS[.fraction]Z` with 1–9 fractional digits when present and a valid calendar date. Bind the **unchanged exact** `(container_id, image_id, started_at)` tuple across the launch observation, same-Writer TUI/fixture correlation, `ops.stop_request(authority, writer.identity)` and any subsequent identity readback; do not substitute a new Writer or normalize a changed StartedAt into equality. A syntactically invalid or independently observed mismatching value is test-only `REJECTED` with reason `OBSERVED_MISMATCH`, return `1`; never `OFFLINE_FAKE_PASS`, Collect/Apply, or live Host success. If the Fake Writer already ran, retain Guest original/Receipt and evidence, and do not launch a replacement Writer. Reuse existing Writer/Guest Authority/Host Lifecycle contracts unchanged.

Host original Git `HEAD`, branch, Index, Working Tree and any pre-existing Guest data must remain unchanged by the offline test. Do not transport raw Host `.git`, mount a Host RW worktree, run `git reset`/`checkout` on Host, or infer Git history from a file snapshot. Keep current unsupported Git topologies and secret policy fail-closed; do not loosen `admit_clean_repo` merely to make the fixture pass.

### 4.3 Single test-scenario transaction

1. Preflight: clean local branch, valid Host Git baseline and digest-bound Bundle/Manifest; reject unsupported/dirty/changed Host state before any Writer or infrastructure effect. Local temporary Bundle/import artifacts are permissible only under the offline harness.
2. Admission: run real `import_guest_baseline()` to a **new isolated temporary Guest Git repository**; after Import, call `admit_clean_repo(guest_repo)` and compare all actual returned Git identity fields against the immutable imported Guest baseline **before** issuing Authority. Create/validate the private Session Receipt; then issue `VerifiedGuestAuthority` via `verify_guest_authority_from_host_record()` + `FakeGuestImageRunner` with pinned Host evidence. Its Guest baseline argument is the freshly verified Git observation, not a stale structure or Guest self-report. Missing/mismatched Receipt/Archive/Config-ID/Manifest/Runtime/SessionKey or Git state fails closed.
3. Execute: **immediately before Fake Writer launch**, recheck both Host and Guest using `recheck_host_baseline(host_baseline)` and `recheck_host_baseline(imported_guest_baseline)`; changed HEAD, Index or Worktree at either boundary means `REJECTED`/`OBSERVED_MISMATCH`, no Writer start, Guest original/Receipt retained. Only after this check model one Fake Writer/TUI exit, deterministic fixture edit/test and one-path Git Commit. Validate the returned `SliceBWriterObservation.identity`: full lowercase-hex 64-character CID, `image_id == authority.image_config_id`, valid UTC RFC3339 `started_at`, and identical `(container_id, image_id, started_at)` across the TUI/fixture/stop evidence. Reject a different Fake Image ID or changed StartedAt as `REJECTED`/`OBSERVED_MISMATCH` (return `1`), preserve Guest/Receipt, never start a replacement Writer or invoke Apply. A Fake TUI/Commit is not live OpenCode or inference proof.
4. Terminate: invoke existing `coordinate_host_controlled_stop(HostControlledStopRequest(...))` through `FakeGuestStopper`, `FakeHostControl` and `FakePreserver`, not real infrastructure. The verified Fake Lifecycle can legitimately emit `host.observe → guest.stop → host.observe → host.shutdown → host.wait → preserve`, including `FakeHostControl.request_graceful_shutdown()`. Alternative retry/already-stopped ordering follows existing tests. **Assert Fake event ordering and zero real Host/VM/Docker/sbx effects separately**. Fake successes are not live Host Isolation PASS.
5. Retain: if `HostControlledStopResult.failures` includes `GUEST_STOP_UNVERIFIED`, or quiescence is `GUEST_QUIESCENCE_UNVERIFIED`, **overall status is `PENDING` even when later Fake Host isolation or preservation stages appear successful**. In addition, `PreservationDisposition.CONDITIONALLY_ACCEPTED` / `HostLifecycleStage.OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED` is **never** Fake success, even when `result.failures == ()`: classify it test-only `PRESERVATION_UNVERIFIED`, return `1`, retain original/Receipt, and require Owner decision for any real conditional acceptance. Fake green requires **affirmatively** verified Guest stop and quiescence, verified Fake Host isolation, and `PreservationDisposition.VERIFIED` with the matching `OFFLINE_PRESERVATION_VERIFIED` stage and no coordinator failures. Never determine overall success from an empty `failures` tuple or positive stage alone. Retain Guest original/Session evidence when `PENDING` or `PRESERVATION_UNVERIFIED`, record bounded reasons and forbid Collection Digest, ApplyAuthorization or Host Apply. Do not mutate the Host checkout.

The action is idempotent only where the existing identity-bound stop/retry contract actually proves it. No retry may create a second Writer or change Session Generation; ambiguous interruption is not silently resumed as success.

## 5. Safety invariants and outcome semantics

| Observation | Required integration behavior |
| --- | --- |
| Invalid args, dirty/unsupported Git, baseline/authority/hash mismatch **before launch** | `REJECTED` or fixed fail-closed CLI stop; **zero** infrastructure side effects |
| Missing Writer/Guest Session identity or failed correlation, malformed Full CID/StartedAt, or `WriterIdentity.image_id != authority.image_config_id` | Test-only `REJECTED`/`OBSERVED_MISMATCH`, return `1`; keep Guest original/Receipt; no replacement Writer, guessed identity, tag fallback or Host Apply |
| Writer TUI not completed successfully / fixture check fails | No success claim or fixture Commit acceptance; preserve available evidence |
| Guest stop, restart epoch or Host isolation cannot be verified | `PENDING / GUEST_QUIESCENCE_UNVERIFIED` or corresponding bounded unverified reason; do not collect/apply |
| Host autostart, restart audit or shared-write exclusion remains unknown | Maintain `NOT_VERIFIED`; never substitute a mocked `STOPPED` for real Host Isolation |
| Guest original/receipt durability or readback unknown, or `PreservationDisposition.CONDITIONALLY_ACCEPTED` even with no `LifecycleFailure` | Test-only `PRESERVATION_UNVERIFIED`, return `1`; retain evidence and forbid finalize/apply; conditional preservation is not `VERIFIED` |
| Independently observed identity/commit/blob mismatch | Failure, **not** `NOT_VERIFIED`; retain evidence for Owner |
| Real Host/VM/GuestFS/Writer/TTY tests not performed | `NOT_RUN` in the human-facing acceptance record regardless of offline test success |

**Distinct result domains — RG-OC2-B-003:** The persistent production `SliceBReceipt.state` is **unchanged** and accepts exactly `REJECTED`, `RUNNING`, `PENDING` or `PRESERVATION_UNVERIFIED` (as validated by existing `_STATES`). It has **no success terminal state**, and offline Fake success must **never** be stored as `RUNNING` or written as an invented Receipt `SUCCESS`/`PASS`. The Python-only harness instead records the explicit test-only `SliceBOfflineOutcome = Literal["OFFLINE_FAKE_PASS", "REJECTED", "PENDING", "PRESERVATION_UNVERIFIED"]` through `ops.record_result(outcome, reason, lifecycle_result)`; this operation is not Receipt persistence or live acceptance evidence.

| Test-only outcome | Classification / `reason` | `run_slice_b` return | Production Receipt and real acceptance |
| --- | --- | --- | --- |
| `OFFLINE_FAKE_PASS` | **All** required affirmative checks: actual Git/Authority + `(CID, pinned Image Config ID, StartedAt)` for same Writer/TUI/fixture; `result.failures == ()`; `result.guest_verdict is not None and result.guest_verdict.verified`; stage `GUEST_QUIESCENCE_VERIFIED` present and `GUEST_QUIESCENCE_UNVERIFIED` absent; `result.host_isolation is not None and result.host_isolation.verified` with stage `VM_ISOLATION_VERIFIED`; `result.preservation is not None and result.preservation.disposition is PreservationDisposition.VERIFIED` with stage `OFFLINE_PRESERVATION_VERIFIED` and **no** `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED`. `reason=None`. Neither `failures == ()` nor positive stages alone suffice. | `0` | Receipt remains `PENDING` (no live terminal success); real Host Isolation/Preservation still `NOT_RUN`/`NOT_VERIFIED` |
| `PENDING` | `GUEST_STOP_UNVERIFIED`/`GUEST_QUIESCENCE_UNVERIFIED`, restart/isolation uncertainty, or other absent proof; bounded reason, **regardless of later Fake success stages** | `1` | Original Guest/Session evidence retained; Receipt `PENDING`; no Apply |
| `PRESERVATION_UNVERIFIED` | Guest stop/quiescence and Fake isolation verified, but preservation is missing, `UNVERIFIED` **or `CONDITIONALLY_ACCEPTED`** (including `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED` with `result.failures == ()`); bounded preservation reason | `1` | Receipt remains `PENDING` or existing `PRESERVATION_UNVERIFIED`; never real preservation PASS |
| `REJECTED` | Independently **observed** Git/identity/digest/commit mismatch, including incorrect Fake Writer Image Config ID, malformed Full CID or invalid/changed StartedAt; `reason=OBSERVED_MISMATCH` (or bounded preflight rejection reason); no Writer on prelaunch mismatch and no **replacement** Writer after a bad observation | `1` | Receipt stays in existing schema; originals retained if created; never relabel real observed mismatch as unknown |

Observed mismatch is not `NOT_VERIFIED`. Evaluate independently observed mismatch first; otherwise Guest-stop uncertainty takes precedence over later Fake-positive stages; otherwise Host isolation uncertainty, then preservation `MISMATCH` as observed `REJECTED`/`OBSERVED_MISMATCH`, and missing/`UNVERIFIED`/**`CONDITIONALLY_ACCEPTED`** preservation as `PRESERVATION_UNVERIFIED`. Any remaining missing affirmative success evidence or unclassified lifecycle failures must **not** map to success (bounded `PENDING`, return `1`). `OFFLINE_FAKE_PASS` requires every affirmative Guest, Host and `PreservationDisposition.VERIFIED` check plus `result.failures == ()`. No Fake result upgrades the live evidence state.

Keep the three AC-13 claims separate: credential non-injection, external communication path absence, and absence of inference requests. Offline Fake tests can verify control-flow **non-invocation** and static constraints, but cannot set those three live assertions to `PASS`.

Do not install systemd units, disable Host isolation checks, change credentials, grant paid inference, auto-enable T8/T9 Preservation, or add broad exception handlers that convert unexpected failures to success. Failed cleanup must never silently delete a Guest original.

## 6. Test-first implementation contract (subsequent explicitly authorized task)

TDD follows **RED → GREEN → REFACTOR**. Test the fixed production CLI HOLD and the Python-only `run_slice_b(..., ops=fake)` as separate contracts. Local Git fixtures and Fake `host.observe`/`host.shutdown`/`host.wait` are allowed; no **real** Host/VM/Docker/sbx, GuestFS, SSH, sudo, credential or network actions.

| Test focus | RED expectation before wiring | GREEN/acceptance expectation |
| --- | --- | --- |
| **CLI production HOLD / precedence** | `--slice-b` unavailable / parse-time `SystemExit(0)` for help/version | Raw-argv pre-parse selector with `--help`, `--version`, unknown, `--dry-run`, `--slice-b=...` or credential flags returns **1**, exact fixed stderr and no stdout/effects; no-selector help/version/unknown keep argparse `SystemExit(0/2)` |
| Selection rejects conflict | Disallowed option may enter normal bootstrap | Every forbidden combination rejects before any external effect |
| **Python-only Fake E2E** | No one-piece integration flow | Test harness directly calls Plan Task 6 `run_slice_b(..., ops: SliceBOps)`; actual Guest `admit_clean_repo`/`recheck_host_baseline`, verified Authority, same-Writer Fake TUI/fixture, Host Lifecycle; no CLI entry |
| **Offline outcome vs Receipt (RG-OC2-B-003)** | Success wrongly maps to Receipt `RUNNING`, invented `SUCCESS`, or `CONDITIONALLY_ACCEPTED` with no lifecycle failures | Test-only `OFFLINE_FAKE_PASS`/`None`/return `0` only with positive Guest-stop, Host-isolation and **`PreservationDisposition.VERIFIED`** evidence and no failures; conditional preservation → `PRESERVATION_UNVERIFIED`/return `1`; Receipt never stores Fake success; live acceptance remains `NOT_RUN` |
| **Git negative / post-import drift (RG-OC2-B-005)** | Saved `GitBaseline` might mask later Guest mutation | Actual imported Guest is re-observed **before Authority** and rechecked with Host **immediately before Writer**; mutations after Import/Authority reject before Writer, retain Guest/Receipt and original Host |
| Digest/identity negative cases (RG-OC2-B-006) | Adapter permits missing/mismatched evidence or Fake Writer Image ID differing from the pinned Config ID | `verify_guest_authority_from_host_record()` with existing `FakeGuestImageRunner` validates Receipt/Archive/Config-ID/Runtime; Orchestrator rejects malformed full CID, Fake `identity.image_id != authority.image_config_id`, invalid/changed StartedAt or forged authority as `REJECTED`/`OBSERVED_MISMATCH`; no Fake PASS/Apply |
| **Guest-stop-unknown precedence** | Positive Fake stage could conceal unverified Guest stop | `GUEST_STOP_UNVERIFIED` / `GUEST_QUIESCENCE_UNVERIFIED` => `PENDING` despite later Fake success; Guest originals retained, live Host Isolation NOT_VERIFIED |
| Other stop/preservation negatives | Empty `result.failures` mistakenly treated as success despite conditional preservation | Isolation unknown => `PENDING`; Guest original/readback missing **or** `CONDITIONALLY_ACCEPTED` (existing `test_conditionally_accepted_preservation_has_distinct_stage`) => `PRESERVATION_UNVERIFIED`/return `1`; only `VERIFIED` disposition may lead to Fake success; no Collector/Apply |
| **Fake Lifecycle event-order assertion (RG-OC2-B-001)** | No integrated sequence | Check `host.observe`, `guest.stop`, `host.shutdown`, `host.wait`, optional `preserve` order using existing `FakeHostControl`; **Fake `host.shutdown` is allowed** |
| **Real infrastructure non-invocation assertion (separate)** | No external effect evidence | **Zero real** Host observe/start/stop, VM, Docker/sbx, SSH/sudo, GuestFS, credential, network, inference, Collect, Apply calls; do not count Fake `host.shutdown` as a real call |
| Regression | New selector may collide with Phase 1–5 | Existing relevant `test_oc2.py`, `test_oc2_e2e.py`, Slice B Git/Session/Writer/Supervisor/Host lifecycle offline suites still pass |

Prefer Plan Task 6's `sandbox/tests/test_oc2_slice_b_adapter.py` for the internal Fake E2E, plus minimal launcher tests for the separate production HOLD contract. Reuse existing fixtures and fake implementations; do not rewrite or duplicate their tests for formatting reasons. When a proposed scenario is already covered, reference the existing test rather than multiplying test cases.

Offline proof must include: exact base HEAD, changed file list, test commands, observed **RED** failure (expected missing behavior), **GREEN** pass, relevant regression results, and explicit `NOT_RUN` for live acceptance. A test that passed before the code change is not RED evidence. Do not invent counts or report a test as passing without command output.

## 7. Allowed file scope and non-goals

Expected future TDD implementation touch points, **not modified by this design-only task**:

- `sandbox/scripts/oc2.py`: minimal early dispatch and selection checks.
- `sandbox/scripts/oc2_slice_b.py`: one narrowly scoped orchestration adapter, if needed.
- `sandbox/tests/test_oc2_slice_b_adapter.py`: Plan Task 6 internal Fake E2E, negative and non-invocation coverage.
- `sandbox/tests/test_oc2.py` / `test_oc2_e2e.py`: only strictly necessary CLI regression tests.

Changes to `oc2_writer.py`, `oc2_supervisor.py`, `oc2_host_lifecycle.py`, `oc2_slice_b_git.py`, image/Session schema, and old tests are **not presumed necessary**. Only modify them later when a RED test demonstrates a concrete integration defect and the Owner-approved implementation scope permits it. Preserve PR #191 behavior.

Out of scope: daily `oc2` default-mode migration, Sandbox selection/reuse, dirty-index restoration, live VM operations, credential/proxy/provider selection changes, production TUI/TTY acceptance, automatic stop+Collect/Apply, Git history migration, Release, and host rollout.

## 8. Exit criteria, risk and Human Owner checkpoint

This bounded review remediation updates **only this Design and its paired implementation-plan Markdown in local output**. Existing prior GitHub commits are evidence, not authority for new GitHub writes. **No Commit/Push/PR or implementation is authorized by this correction**; Design adoption and Tasks 1–3 implementation remain separate Human Owner decisions.

The future first slice is complete only if:

1. One integrated offline scenario demonstrably flows through verified baseline → Session/Guest authority → fake same-Writer TUI/fixture → bounded conservative stop outcome.
2. All fail-closed and forbidden-side-effect regression assertions above pass, with genuine RED and GREEN evidence.
3. Legacy default path remains unchanged, and no real infrastructure or Host worktree is touched.
4. Real Host Isolation, T8/T9 Preservation, live TUI and actual durable recovery remain clearly `NOT_RUN`/`NOT_VERIFIED`.
5. Results, limitations and any deferred non-blocking findings are stated once; stop at **Human Owner Checkpoint**.

**Stop conditions:** an operation requires real Host/VM/Docker/Sandbox/GuestFS/credential access, source changes outside the approved slice, an unsafe identity/isolation workaround, data-loss risk, or an unapproved Commit/Push/PR. Fail closed on the affected operation; do not automatically start a new review, correction loop, task, plan, PR, Merge or environment change.

**Residual risk:** an offline green suite demonstrates wiring and control decisions, **not** real OpenCode TUI usability, kernel-wide quiescence, Host Isolation, preserved original recoverability or daily-operation readiness. Production opt-in and Host acceptance each require a separate explicit Owner decision. This document can be considered at the Owner checkpoint without further independent review by default.
