# OC2 — First Offline Vertical Slice B Wiring Design R0.1.1

- Date: 2026-11-21 (JST)
- Repository: `yohi/dotfiles-ai`
- Base: `master@34d0c023925d01f2bb4f91a5b61ee7c871c4a5df` (merged PR #191)
- Status: **DESIGN_LIMITED_CORRECTION / OWNER_ADOPTION_PENDING / IMPLEMENTATION_NOT_AUTHORIZED / LIVE_ACCEPTANCE_NOT_RUN**
- Revision: **R0.1.1 — RG-OC2-B-001 and RG-OC2-B-002 limited correction only**
- Scope: **One bounded offline TDD vertical slice; design document only in this branch.**
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
  `-- --slice-b (including --dry-run): fixed Production HOLD
       SLICE_B_LIVE_NOT_ACCEPTED; nonzero; no ops or infrastructure effects

Python unittest only (not reachable from CLI flags or environment):
  -> run_slice_b(repo_root, workspace, sandbox_name, *, dry_run, ops=FakeSliceBOps)
       |-- verified clean Git Baseline + Bundle/Manifest
       |-- private Host Receipt + verified Guest authority
       |-- same-Session Fake Writer/TUI/fixture
       |-- FakeHostControl lifecycle event order
       `-- bounded outcome; PENDING on Guest-stop uncertainty;
           no real Host Isolation PASS, Collector or Apply

NO real Host/VM/Docker/sbx, Credential, Inference, Collector, Apply.
```

### 4.1 Entry and selection contract

1. Add **only** an explicit `--slice-b` selector in `oc2.py`. Its **fixed HOLD gate**, not the internal orchestration function, runs before normal launcher runtime setup, APM export, OAuth/bootstrap, broker probe, credential Mixin, Sandbox creation, CLI download, or TUI launch. Preserve no-flag `oc2` semantics.
2. Reject combinations with credential/inference options (`--use-host-broker`, `--host-broker-*`, `--allow-paid-inference`, `--use-cloudflare-ai-gateway`) and provisioning/verification/Phase-4 options before side effects. Explicitly reject any unsupported state or unknown flag; no implicit fallback to normal mode.
3. `oc2 --slice-b --dry-run` also returns the **same fixed nonzero HOLD**, without calling `run_slice_b`, allocating `SliceBOps`, touching infrastructure or claiming readiness. No CLI option or environment variable may inject Fake ports or bypass this gate.
4. **Production HOLD:** all production `oc2 --slice-b` invocations stop **nonzero** with fixed non-secret `SLICE_B_LIVE_NOT_ACCEPTED` **before calling `run_slice_b` or any Host/VM/Docker/Sandbox effects**. Verify HOLD through an actual CLI subprocess test. Test doubles are passed only by the separate Python test harness, never through a CLI `--fake`, environment opt-in or alternate entrypoint.

### 4.2 Integration boundary, not reimplementation

Create `sandbox/scripts/oc2_slice_b.py` only for orchestration and bounded outcome mapping. **Reuse Plan Task 6's exact interface:** `def run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int`. The `SliceBOps` protocol wraps only explicit operations and has no default real or Fake implementation. Keep existing validation, trusted authority creation, Writer spec, TTY frame protocol, Session receipt schema, Host isolation, and preservation logic in their existing modules.

Only a **Python test harness** (Plan Task 6 target `sandbox/tests/test_oc2_slice_b_adapter.py`) invokes `run_slice_b(..., ops=fake)` directly, with explicitly supplied `SliceBOps` Fake ports and deterministic event recording. Production `oc2.py` never instantiates these Fake ports or invokes `run_slice_b`, including for `--dry-run`. No injection via user CLI flags, environment variables, generic shell port or privileged fallback. Real adapters remain disabled; no delegation to legacy `sbx exec` or `_session_action`. Test-local Git fixture activity is permitted; real Host lifecycle/VM/Docker/sbx calls are forbidden.

Trusted authority is **never** constructed from arbitrary Guest-reported identity. Use the existing `GuestAuthorityVerificationRequest` and `verify_guest_authority_from_host_record(request, runner)` with `FakeGuestImageRunner` from `sandbox/tests/oc2_slice_b_test_support.py` in the offline harness. Issue `VerifiedGuestAuthority` only after existing Host Receipt/Manifest, Archive/Config-ID, Runtime/Image Record, SessionKey and independently observed Guest Baseline checks succeed. Keep full Writer Container ID/StartedAt correlation. No forged sealed authority, mutable Guest `.git` expected identity or bare Docker image tag may substitute for those checks.

Host original Git `HEAD`, branch, Index, Working Tree and any pre-existing Guest data must remain unchanged by the offline test. Do not transport raw Host `.git`, mount a Host RW worktree, run `git reset`/`checkout` on Host, or infer Git history from a file snapshot. Keep current unsupported Git topologies and secret policy fail-closed; do not loosen `admit_clean_repo` merely to make the fixture pass.

### 4.3 Single test-scenario transaction

1. Preflight: clean local branch, valid Git baseline and digest-bound Bundle/Manifest; reject unsupported/dirty/changed Host state before any effect.
2. Admission: create and validate private Session Receipt, then issue `VerifiedGuestAuthority` only via existing `verify_guest_authority_from_host_record()` and `FakeGuestImageRunner` with pinned Host evidence; all immutable identities remain fixed. A missing/mismatched Receipt, Archive, Config ID, Manifest, Runtime/SessionKey or independently observed Guest Baseline fails closed; recheck Host baseline at the required boundary.
3. Execute: in the **offline Fake only**, model one accepted Writer identity and same Writer's TUI exit, deterministic fixture edit/test and one-path Git Commit contract. The fake emits identity-bound observations; it does **not** prove that a real OpenCode TUI ran or that AI inference happened.
4. Terminate: invoke existing `coordinate_host_controlled_stop(HostControlledStopRequest(...))` through `FakeGuestStopper`, `FakeHostControl` and `FakePreserver`, not real infrastructure. The verified Fake Lifecycle can legitimately emit `host.observe → guest.stop → host.observe → host.shutdown → host.wait → preserve`, including `FakeHostControl.request_graceful_shutdown()`. Alternative retry/already-stopped ordering follows existing tests. **Assert Fake event ordering and zero real Host/VM/Docker/sbx effects separately**. Fake successes are not live Host Isolation PASS.
5. Retain: if `HostControlledStopResult.failures` includes `GUEST_STOP_UNVERIFIED`, or quiescence is `GUEST_QUIESCENCE_UNVERIFIED`, **overall status is `PENDING` even when later Fake Host isolation or preservation stages appear successful**. Never determine overall success from a positive stage alone. Retain Guest original/Session evidence when `PENDING` or `PRESERVATION_UNVERIFIED`, record bounded reasons and forbid Collection Digest, ApplyAuthorization or Host Apply. Do not mutate the Host checkout.

The action is idempotent only where the existing identity-bound stop/retry contract actually proves it. No retry may create a second Writer or change Session Generation; ambiguous interruption is not silently resumed as success.

## 5. Safety invariants and outcome semantics

| Observation | Required integration behavior |
| --- | --- |
| Invalid args, dirty/unsupported Git, baseline/authority/hash mismatch **before launch** | `REJECTED` or fixed fail-closed CLI stop; **zero** infrastructure side effects |
| Missing Writer/Guest Session identity or failed correlation | Stop; no guessed identity, tag fallback, new Writer or Host Apply |
| Writer TUI not completed successfully / fixture check fails | No success claim or fixture Commit acceptance; preserve available evidence |
| Guest stop, restart epoch or Host isolation cannot be verified | `PENDING / GUEST_QUIESCENCE_UNVERIFIED` or corresponding bounded unverified reason; do not collect/apply |
| Host autostart, restart audit or shared-write exclusion remains unknown | Maintain `NOT_VERIFIED`; never substitute a mocked `STOPPED` for real Host Isolation |
| Guest original/receipt durability or readback unknown | `PRESERVATION_UNVERIFIED`; retain evidence and forbid finalize/apply |
| Independently observed identity/commit/blob mismatch | Failure, **not** `NOT_VERIFIED`; retain evidence for Owner |
| Real Host/VM/GuestFS/Writer/TTY tests not performed | `NOT_RUN` in the human-facing acceptance record regardless of offline test success |

Keep the three AC-13 claims separate: credential non-injection, external communication path absence, and absence of inference requests. Offline Fake tests can verify control-flow **non-invocation** and static constraints, but cannot set those three live assertions to `PASS`.

Do not install systemd units, disable Host isolation checks, change credentials, grant paid inference, auto-enable T8/T9 Preservation, or add broad exception handlers that convert unexpected failures to success. Failed cleanup must never silently delete a Guest original.

## 6. Test-first implementation contract (subsequent explicitly authorized task)

TDD follows **RED → GREEN → REFACTOR**. Test the fixed production CLI HOLD and the Python-only `run_slice_b(..., ops=fake)` as separate contracts. Local Git fixtures and Fake `host.observe`/`host.shutdown`/`host.wait` are allowed; no **real** Host/VM/Docker/sbx, GuestFS, SSH, sudo, credential or network actions.

| Test focus | RED expectation before wiring | GREEN/acceptance expectation |
| --- | --- | --- |
| **CLI production HOLD** | `--slice-b` unavailable / no fixed HOLD | Real CLI `oc2 --slice-b` (also `--dry-run`) exits nonzero with `SLICE_B_LIVE_NOT_ACCEPTED` before `run_slice_b`/`SliceBOps`/external effects; default `oc2` unchanged |
| Selection rejects conflict | Disallowed option may enter normal bootstrap | Every forbidden combination rejects before any external effect |
| **Python-only Fake E2E** | No one-piece integration flow | Test harness directly calls Plan Task 6 `run_slice_b(..., ops: SliceBOps)` with Fake; clean Baseline/verified Guest Authority/same-Writer TUI-fixture/Host Lifecycle result, never via CLI |
| Git negative cases | Missing integrated rejection evidence | Dirty, changed, unsupported or unsafe repo rejects before launch; baseline still unchanged |
| Digest/identity negative cases | Adapter permits missing/mismatched evidence | `verify_guest_authority_from_host_record()` with existing `FakeGuestImageRunner` must validate Receipt/Archive/Config-ID/Runtime; mismatched/forged authority, Guest Baseline, Writer/epoch fail closed |
| **Guest-stop-unknown precedence** | Positive Fake stage could conceal unverified Guest stop | `GUEST_STOP_UNVERIFIED` / `GUEST_QUIESCENCE_UNVERIFIED` => `PENDING` despite later Fake success; Guest originals retained, live Host Isolation NOT_VERIFIED |
| Other stop/preservation negatives | Overconfident terminal status | Isolation unknown => `PENDING`; Guest original/readback missing => `PRESERVATION_UNVERIFIED`; no Collector/Apply |
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

Design deliverable: **this one Markdown document only**. Creating and pushing its feature branch is authorized by the user's current request; **the design is not thereby adopted** and implementation is not authorized.

The future first slice is complete only if:

1. One integrated offline scenario demonstrably flows through verified baseline → Session/Guest authority → fake same-Writer TUI/fixture → bounded conservative stop outcome.
2. All fail-closed and forbidden-side-effect regression assertions above pass, with genuine RED and GREEN evidence.
3. Legacy default path remains unchanged, and no real infrastructure or Host worktree is touched.
4. Real Host Isolation, T8/T9 Preservation, live TUI and actual durable recovery remain clearly `NOT_RUN`/`NOT_VERIFIED`.
5. Results, limitations and any deferred non-blocking findings are stated once; stop at **Human Owner Checkpoint**.

**Stop conditions:** an operation requires real Host/VM/Docker/Sandbox/GuestFS/credential access, source changes outside the approved slice, an unsafe identity/isolation workaround, data-loss risk, or an unapproved Commit/Push/PR. Fail closed on the affected operation; do not automatically start a new review, correction loop, task, plan, PR, Merge or environment change.

**Residual risk:** an offline green suite demonstrates wiring and control decisions, **not** real OpenCode TUI usability, kernel-wide quiescence, Host Isolation, preserved original recoverability or daily-operation readiness. Production opt-in and Host acceptance each require a separate explicit Owner decision. This document can be considered at the Owner checkpoint without further independent review by default.
