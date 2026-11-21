# OC2 — First Offline Vertical Slice B Wiring Design R0.1.0

- Date: 2026-11-21 (JST)
- Repository: `yohi/dotfiles-ai`
- Base: `master@34d0c023925d01f2bb4f91a5b61ee7c871c4a5df` (merged PR #191)
- Status: **DESIGN_PROPOSED / IMPLEMENTATION_NOT_AUTHORIZED / LIVE_ACCEPTANCE_NOT_RUN**
- Scope: **One bounded offline TDD vertical slice; design document only in this branch.**
- Parent: [OC2 Daily Launcher Design R0.2](2026-11-13-oc2-daily-launcher-design.md)
- Existing bounded contract: [Alternative A — Vertical Slice B Integration Design R0.1.5](2026-11-16-oc2-alternative-a-vertical-slice-b-design.md)
- Existing plan (historical task scope; not automatically reauthorized): [Vertical Slice B Implementation Plan R0.1.2](../plans/2026-11-16-oc2-alternative-a-vertical-slice-b-implementation-plan.md)

## 1. Intent and completion boundary

The product goal remains: from a repository root, run `oc2` to use an isolated OpenCode development environment, safely retain work when stopping, and eventually resume daily development. This document **does not** claim that daily operation is complete.

The immediate objective is **one executable, offline, dependency-injected end-to-end integration test path** connecting the existing CLI, verified clean Git baseline, immutable Session/Guest authority, one simulated Writer/TUI execution, and a conservative stop result. Implement only the missing connections, not a new Host/Guest architecture.

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
bin/oc2
  -> oc2.py: parse + reject incompatible --slice-b flags EARLY
       |-- no --slice-b: existing Phase 1–5 flow unchanged
       `-- --slice-b: offline-safe dispatcher / production HOLD
               |
               v
       oc2_slice_b.py (new, bounded orchestration only)
               |
               +-- Host clean Git admission + baseline recheck
               +-- verified Git Bundle/Manifest + Session identity
               +-- immutable Host Receipt and verified Guest authority
               +-- trusted Guest image/Writer adapter (offline Fake in tests)
               +-- same-identity TUI -> offline fixture/test/commit (Fake)
               +-- stop/quiescence/isolation observation (Fake)
               `-- typed outcome + retained originals / PENDING where unverified

NO credential/bootstrap, real Docker, sbx, VM, Relay, Collector, Apply.
```

### 4.1 Entry and selection contract

1. Add **only** an explicit `--slice-b` selector in `oc2.py`. Dispatch before normal launcher runtime setup, APM export, OAuth/bootstrap, broker probe, credential Mixin, Sandbox creation, CLI download, or TUI launch. Preserve no-flag `oc2` semantics.
2. Reject combinations with credential/inference options (`--use-host-broker`, `--host-broker-*`, `--allow-paid-inference`, `--use-cloudflare-ai-gateway`) and provisioning/verification/Phase-4 options before side effects. Explicitly reject any unsupported state or unknown flag; no implicit fallback to normal mode.
3. `--slice-b --dry-run`, if included in this slice, must be non-mutating, must not touch Docker/VM/credential/paid inference, and must not claim operational readiness. Tests must verify its safety. Do not expose an undocumented CLI option or environment variable that bypasses the production gate.
4. **Production HOLD:** this offline slice is not permission to invoke the real Host/VM/Writer effects from `oc2 --slice-b`. Until separately authorized and live-accepted, a non-test request for that route must stop with a fixed, non-secret `SLICE_B_LIVE_NOT_ACCEPTED` outcome **before any Host/VM/Docker/Sandbox effects**. Test doubles are injected only in the Python offline test harness, never through a user-accessible `--fake` or environment opt-in.

### 4.2 Integration boundary, not reimplementation

Create `sandbox/scripts/oc2_slice_b.py` only for orchestration and bounded outcome mapping. Keep existing validation, trusted authority creation, Writer spec, TTY frame protocol, Session receipt schema, Host isolation, and preservation logic in their existing modules.

Use narrow, dependency-injected **ports** for effects requiring real infrastructure (e.g. verified bundle/Guest transfer, image access, Writer launch/attach/stop, Host observation). A test adapter implements those ports with deterministic call/event recording; the production adapter remains disabled and does not silently delegate to legacy `sbx exec` or `_session_action`.

Trusted authority is **never** constructed from arbitrary Guest-reported identity. Reuse validated `WriterSessionKey`, Host baseline, Bundle/Manifest hashes, Runtime/Image Record, full Container ID, StartedAt, and the existing Session/Guest authority validators. No mutable Guest path or bare Docker image tag can become authority.

Host original Git `HEAD`, branch, Index, Working Tree and any pre-existing Guest data must remain unchanged by the offline test. Do not transport raw Host `.git`, mount a Host RW worktree, run `git reset`/`checkout` on Host, or infer Git history from a file snapshot. Keep current unsupported Git topologies and secret policy fail-closed; do not loosen `admit_clean_repo` merely to make the fixture pass.

### 4.3 Single test-scenario transaction

1. Preflight: clean local branch, valid Git baseline and digest-bound Bundle/Manifest; reject unsupported/dirty/changed Host state before any effect.
2. Admission: create and validate private Session Receipt and Guest authority using the existing code paths. Immutable identities remain fixed for the whole scenario; verify Host baseline again at the relevant boundary.
3. Execute: in the **offline Fake only**, model one accepted Writer identity and same Writer's TUI exit, deterministic fixture edit/test and one-path Git Commit contract. The fake emits identity-bound observations; it does **not** prove that a real OpenCode TUI ran or that AI inference happened.
4. Terminate: model one stop request, observed identity, restart epoch, quiescence and Host isolation response through the current lifecycle contracts. No simulated `PASS` may be promoted to real Host acceptance.
5. Retain: when state is `PENDING` or preservation is unverified, retain original Guest repository and Session evidence, record a bounded reason, and do not issue Collection Digest, ApplyAuthorization or Host Apply. The offline scenario must not mutate the Host checkout.

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

TDD follows **RED → GREEN → REFACTOR**. Tests run entirely offline; no real Docker, sbx, VM, GuestFS, SSH, sudo, credential or network actions.

| Test focus | RED expectation before wiring | GREEN/acceptance expectation |
| --- | --- | --- |
| CLI selection | `--slice-b` unavailable / dispatch absent | Explicit selection reaches adapter before normal side effects; default `oc2` unchanged |
| Selection rejects conflict | Disallowed option may enter normal bootstrap | Every forbidden combination rejects before any external effect |
| Successful Fake E2E | No one-piece integration flow | One clean Git baseline, verified identity, fake TUI/fixture/stop result, same Session/Writer identity throughout |
| Git negative cases | Missing integrated rejection evidence | Dirty, changed, unsupported or unsafe repo rejects before launch; baseline still unchanged |
| Digest/identity negative cases | Adapter permits missing/mismatched evidence | Mismatch, forged authority, altered receipt, different Writer/epoch fail closed |
| Stop and preservation negative cases | Potentially overconfident terminal status | Unverified stop/isolation => PENDING, evidence retained, no Collector/Apply |
| Zero-side-effect enforcement | No high-level interaction assertion | Fake ports record **no** credential, host start/stop, VM, live Docker, network, inference, Collect, Apply |
| Regression | New selector may collide with Phase 1–5 | Existing relevant `test_oc2.py`, `test_oc2_e2e.py`, Slice B Git/Session/Writer/Supervisor/Host lifecycle offline suites still pass |

Prefer a new focused `sandbox/tests/test_oc2_slice_b_wiring.py` plus minimal changes to existing launcher tests. Reuse existing fixtures and fake implementations; do not rewrite or duplicate their tests for formatting reasons. When a proposed scenario is already covered, reference the existing test rather than multiplying test cases.

Offline proof must include: exact base HEAD, changed file list, test commands, observed **RED** failure (expected missing behavior), **GREEN** pass, relevant regression results, and explicit `NOT_RUN` for live acceptance. A test that passed before the code change is not RED evidence. Do not invent counts or report a test as passing without command output.

## 7. Allowed file scope and non-goals

Expected future TDD implementation touch points, **not modified by this design-only task**:

- `sandbox/scripts/oc2.py`: minimal early dispatch and selection checks.
- `sandbox/scripts/oc2_slice_b.py`: one narrowly scoped orchestration adapter, if needed.
- `sandbox/tests/test_oc2_slice_b_wiring.py`: focused fake E2E, negative and non-invocation coverage.
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
