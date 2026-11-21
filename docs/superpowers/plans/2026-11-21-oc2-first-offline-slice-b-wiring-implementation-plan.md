# OC2 — First Offline Vertical Slice B Wiring Implementation Plan R0.1.0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended by the skill) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **For this project, Human Owner's explicit scope and review-loop restrictions override any default automated reviews, follow-on work, or commits.**

**Status:** `PLAN_DRAFT / DESIGN_ADOPTION_PENDING / IMPLEMENTATION_AUTHORIZATION_HOLD / LIVE_ACCEPTANCE_NOT_RUN`  
**Date:** 2026-11-21 (JST)  
**Repository:** `yohi/dotfiles-ai`  
**Planning baseline:** `master@34d0c023925d01f2bb4f91a5b61ee7c871c4a5df`; Design branch `feature/oc2-slice-b-offline-e2e-wiring-design-20261121@7ce7bc73809590b7a138580d48e59491dc16d5ae`  
**Goal:** Connect an actual isolated imported Git fixture, checked Guest Authority, Fake Writer/TUI, and existing Fake Host Lifecycle into one test-first offline path, while keeping `oc2 --slice-b` in fixed, nonzero Production HOLD.

**Architecture:** Add a minimal early CLI HOLD in `oc2.py`, separate from the Python-only `run_slice_b(..., ops: SliceBOps)` entry. Inside the test harness use existing safe Git Bundle/import, Session Receipt, Archive/Config-ID validation, and verified Guest Authority APIs; pass Fake Writer and Fake Host Lifecycle adapters via an explicit `SliceBOps`. A passing Fake scenario is offline wiring evidence only, never live Host Isolation proof.

**Tech Stack:** Python 3, `unittest`, local Git CLI on temporary fixture repositories, current OC2 Git/Session/Image/Writer/Host Lifecycle Python modules. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-21-oc2-first-offline-vertical-slice-b-wiring-design.md` R0.1.1. Context: `docs/superpowers/specs/2026-11-16-oc2-alternative-a-vertical-slice-b-design.md` R0.1.5 and historical `docs/superpowers/plans/2026-11-16-oc2-alternative-a-vertical-slice-b-implementation-plan.md` Task 6. The historical plan's production dispatch instructions are **not** automatically adopted: the newer Design R0.1.1 fixed HOLD governs this slice.

## Global Constraints

- **Approval gate:** Planning is authorized by the `writing-plans` invocation; Design adoption and source-code implementation are **separate pending Human Owner decisions**. No execution, source edit, test run, Commit/Push/PR or Merge is authorized by the creation of this plan.
- **Production HOLD:** `oc2 --slice-b` and `oc2 --slice-b --dry-run` return nonzero `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED` before `SliceBOps`, `run_slice_b`, OAuth, broker, APM/runtime preparation, Docker/sbx, or any real Host/VM action. Unsupported or credential/inference flag combinations never fall back to another mode.
- **Harness entry:** Only Python `unittest` calls `run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int` directly with explicit Fake ports. No user CLI flag or environment variable can inject Fake ports or bypass HOLD.
- **Git identity:** Host admission uses `admit_clean_repo()` and `recheck_host_baseline()`; a bounded `build_verified_bundle()` plus `verify_bundle_manifest()` precedes **real `import_guest_baseline()` into a new, separate temporary Guest Git repository**. Never use fabricated `GitBaseline` or synthetic `make_verified_authority()` alone to satisfy the integrated E2E.
- **Authority:** Create/read an actual `SliceBReceipt` using `create_session_receipt()`, then use `GuestAuthorityVerificationRequest` + `verify_guest_authority_from_host_record()` with the existing `FakeGuestImageRunner`; `VerifiedGuestAuthority` is never constructed directly or extracted from writable Guest `.git` as expected authority.
- **Identity/policy:** Preserve `WriterSessionKey`, pinned Runtime SHA-256, Bundle/Manifest, Archive and Config ID, Guest Git HEAD/tree/ref/worktree, full Writer Container ID, StartedAt, one Writer/Session, and existing failure semantics. Do not relax image/Session/Host contracts.
- **Stop:** Reuse `coordinate_host_controlled_stop()` with `FakeGuestStopper`, `FakeHostControl`, `FakePreserver`. Fake `host.observe`, `host.shutdown`, `host.wait`, `preserve` are allowed in the recorded sequence; they are **not** real Host actions. Guest stop unverified means aggregate `PENDING` even if later Fake stages are successful.
- **No real infrastructure:** Zero real VM/Host Docker/sbx/Writer/GuestFS/SSH/sudo calls, credentials, egress, paid inference, Collector/Host Apply. Local temporary Git fixture creation/import/fixture commits are allowed as offline test data, not operations on the user's real checkout.
- **Default behavior:** `bin/oc2` and existing no-flag Phase 1–5 path unchanged. No general launcher migration, credential adjustments, daemon/systemd installation, Sandbox reuse or rollback changes.
- **Data retention:** On uncertainty, keep Guest original and private Session evidence; never claim real preservation or live Host Isolation `PASS` from Fake observations. Live acceptance stays `NOT_RUN`/`NOT_VERIFIED`.
- **Exit:** A bounded RED→GREEN→REFACTOR cycle plus relevant offline regressions and a short evidence report, then **Human Owner Checkpoint**. No automatic independent review, correction loop, later task, PR, release, or real Host trial. Any future Commit/Push requires separate explicit approval.

## File structure and ownership

| Path | Future responsibility |
| --- | --- |
| Modify `sandbox/scripts/oc2.py` | One early, unconditional fixed HOLD gate for explicit `--slice-b`; all default paths untouched |
| Create `sandbox/scripts/oc2_slice_b.py` | Plan Task 6-compatible internal orchestrator; narrow `SliceBOps` protocol and offline-only result mapping |
| Modify `sandbox/tests/test_oc2.py` | Production CLI HOLD, `--dry-run`/incompatible-flags/env non-bypass, default launcher regression |
| Create `sandbox/tests/test_oc2_slice_b_adapter.py` | Actual isolated Git import + verified authority + same-Writer Fake TUI/fixture + Fake Host Lifecycle and negatives |
| Reuse without changes | `oc2_slice_b_git.py`, `oc2_slice_b_session.py`, `oc2_slice_b_image*.py`, `oc2_writer.py`, `oc2_supervisor.py`, `oc2_host_lifecycle.py`, `oc2_host_control.py`, `sandbox/oc2_slice_b/offline_fixture.py`, `sandbox/tests/oc2_slice_b_test_support.py`, `sandbox/tests/oc2_host_lifecycle_test_support.py` |

**Scope control:** Do not add a new production `--fake`, gate-override environment variable, general-purpose shell executor, separate Collect/Apply module, or new image/authority schema. A demonstrated RED failure may justify a narrow fix to an existing dependency only after explicit Owner scope approval; do not expand this plan automatically.

## Review Focus

The five consequential failure classes that each have a test below:

1. `--slice-b --dry-run`, credential/inference flags or Fake-looking environment variables accidentally opening production execution → Task 1 asserts fixed nonzero HOLD and zero effects.
2. Dirty/changed Host baseline or overlapping/existing Guest repository → Task 2 asserts rejection **before Writer** and Host HEAD/Index/worktree unchanged.
3. Forged Guest evidence, changed Archive/Config-ID/Runtime/Manifest or synthetic authority replacing real import → Task 2 asserts rejection and an actual `import_guest_baseline()` readback.
4. Fake `host.shutdown` mistaken for a real Host call, or wrong event ordering → Task 3 separately asserts correct Fake sequence and zero real infrastructure calls.
5. Guest stop/restart epoch or preservation proof unknown even when later stages look successful → Task 3 asserts `PENDING` or `PRESERVATION_UNVERIFIED`, retained original, and no live PASS/Collect/Apply.

---

### Task 1 — Fixed Production CLI HOLD (no execution dispatch)

**Files:**
- Modify: `sandbox/scripts/oc2.py` (`main()` argument parser and immediately after `parse_args`)
- Test: `sandbox/tests/test_oc2.py`

**Interfaces:**
- Consumes: existing `main(argv: list[str] | None = None) -> int` and existing `Stop`/`OC2_STOP` error conventions.
- Produces: `oc2 --slice-b` and `oc2 --slice-b --dry-run` always exit **1** with `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED` on stderr, before any runtime/credential/VM effects; no import or invocation of `run_slice_b()` from CLI. Default `oc2` is unchanged.

- [ ] **Step 1 (RED):** In `test_oc2.py` add `test_slice_b_production_hold_before_runtime`, `test_slice_b_dry_run_cannot_bypass_hold`, `test_slice_b_rejects_credential_and_inference_modes`, and `test_slice_b_env_cannot_inject_fake`. Execute `oc2.main([...])` under patched external-effect entrypoints that raise on use. Assert return `1`, exact fixed stderr token, and zero `sbx`/Docker/credential/inference/adapter calls. For subprocess coverage run `python3 sandbox/scripts/oc2.py --slice-b` and `... --slice-b --dry-run` with isolated nonsecret environment and assert the same result. Keep existing tests of no-flag `--dry-run` unchanged.
- [ ] **Step 2 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2 -v`; expect the newly written fixed-HOLD assertions to fail before code change. An old argparse exit `2` is **not** a GREEN fixed HOLD.
- [ ] **Step 3 (minimal GREEN):** Add `p.add_argument('--slice-b', action='store_true')`, then a direct early check immediately after `args = p.parse_args(argv)` that prints the fixed nonsecret HOLD to stderr and returns `1`. Do not instantiate `SliceBOps`, import/call the internal orchestrator, or enter broker/OAuth/APM/`--dry-run` branches on this path. Unknown flags may still fail via existing argparse; never fall through to normal launch when `--slice-b` is accepted.
- [ ] **Step 4 (verify GREEN):** Re-run `python3 -m unittest sandbox.tests.test_oc2 -v` and the two subprocess CLI commands. Verify zero error/failure counts, nonzero HOLD in the CLI, no regression to existing Phase 1–5 tests.
- [ ] **Step 5:** Record RED/GREEN command output and scoped diff; **do not Commit/Push without separate Owner permission**.

### Task 2 — Real isolated Git import, verified Authority, and one Python-only Fake Writer/TUI

**Files:**
- Create: `sandbox/scripts/oc2_slice_b.py`
- Create: `sandbox/tests/test_oc2_slice_b_adapter.py`
- Reuse unchanged: existing Git, Session, Image, Offline Fixture and test-support helpers listed above.

**Interfaces:** Keep the original Plan Task 6 public Python function **exactly**:

```python
def run_slice_b(
    repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps
) -> int: ...
```

Define only the internal data needed for this one offline scenario in `oc2_slice_b.py`:

```python
@dataclass(frozen=True)
class SliceBOfflineInputs:
    key: WriterSessionKey
    runtime_sha256: str
    image_pin: ImagePin
    archive_path: Path
    image_control_root: Path
    docker_host: str
    state_root: Path
    bundle_path: Path
    guest_repo_path: Path
    image_runner: GuestImageRunner

@dataclass(frozen=True)
class SliceBWriterObservation:
    identity: WriterIdentity
    tui_exit_code: int
    fixture_commit_oid: str | None

class SliceBOps(Protocol):
    def inputs(self, baseline: GitBaseline, sandbox_name: str) -> SliceBOfflineInputs: ...
    def run_writer(self, authority: VerifiedGuestAuthority,
                   start: SliceBStartMessage,
                   guest_repo: Path) -> SliceBWriterObservation: ...
    def stop_request(self, authority: VerifiedGuestAuthority,
                     writer: WriterIdentity) -> HostControlledStopRequest: ...
    def record_result(self, state: str, reason: str | None,
                      result: HostControlledStopResult | None) -> None: ...
```

`SliceBOps` is supplied **only by the test**; no CLI or production implementation. The existing `GuestImageRunner` interface is implemented by `FakeGuestImageRunner` in the harness, whose `load_image()` operates on a test archive only. An observed Writer commit from a Fake is **not** production acceptance evidence. `record_result` is a test-visible bounded status record, not a Collection or Apply capability. `dry_run=True` in this internal function exits `1` before `ops.inputs()` or any fixture mutation; it never changes the CLI HOLD policy.

- [ ] **Step 1 (RED):** Add `test_imported_guest_git_and_verified_authority_reach_same_writer`. Use a temporary **actual clean local Git repository** (as in `test_oc2_slice_b_session.py`) to create a real commit, `admit_clean_repo()` and a separate `bundle_path`. Feed `SliceBOfflineInputs` through the test Fake. Require `run_slice_b()` to call `build_verified_bundle()`/`verify_bundle_manifest()`, `import_guest_baseline()` into an **absent, separate** Guest path, `create_session_receipt()`, `verify_guest_authority_from_host_record(GuestAuthorityVerificationRequest(...), FakeGuestImageRunner(pin))`, and `build_start_message()`. Assert observed Guest HEAD/tree/ref/worktree equal admitted Host baseline; the **Guest root differs from Host**, and Authority/Receipt/Manifest/Runtime/Config ID/SessionKey match. The Fake's `run_writer` checks the trusted start message and simulates TUI exit `0`, invokes existing deterministic `run_offline_fixture()` against the separate imported Guest repo, and records the exact single commit OID. Independently assert its parent is Host HEAD, exact fixture blob/path, and unchanged Host HEAD/Index/worktree. This test must not substitute `make_verified_authority()` for the real import/receipt flow.
- [ ] **Step 2 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter -v`; expect failure from missing `oc2_slice_b.py` or missing `run_slice_b`, not from an unrelated dependency or an actual external operation.
- [ ] **Step 3 (minimal GREEN):** In `oc2_slice_b.py`, define the above protocol/data types and `run_slice_b` only. First reject `dry_run=True`, invalid workspace/Host baseline and changed baseline; then run existing bounded Bundle+Manifest and Guest import; create a private `SliceBReceipt` initially `state='PENDING'`, `reason='NOT_RUN'`, `writer_id=None`, `started_at=None`, with the pinned `ImagePin` and `runtime_sha256`; create/verify the receipt via the real APIs; call existing `verify_guest_authority_from_host_record()` with the injected `image_runner`; issue `build_start_message()` only after verifying authority. Call exactly one Fake Writer operation; reject nonzero TUI status, missing fixture evidence, or identity drift. Do not manufacture a `VerifiedGuestAuthority`, run a real writer, shell out to Docker or call Collect/Apply. Defer lifecycle mapping to Task 3 with a fail-closed placeholder result (nonzero / `PENDING`, not falsely complete).
- [ ] **Step 4 (verify GREEN for the admission/Writer boundary):** Re-run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2_slice_b_git sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_image sandbox.tests.test_oc2_slice_b_entrypoint -v`; expect each tested admission/Writer behavior to pass, with lifecycle-completion assertions reserved for Task 3. Do not declare the full E2E complete yet.
- [ ] **Step 5 (security negatives):** Add tests `test_dirty_or_changed_host_rejected_before_writer`, `test_guest_path_already_exists_or_overlaps_host_rejected`, `test_manifest_archive_runtime_or_config_id_drift_rejected`, `test_unverified_guest_baseline_or_forged_authority_rejected`, `test_writer_identity_or_tui_failure_preserves_guest`. Assert fail-closed, original Guest/Receipt retained if created, and no `run_writer` after prelaunch rejection. Follow RED→GREEN for these assertions. Reuse existing validators; do not weaken them.
- [ ] **Step 6:** Record test outputs, private-fixture file/Host checkout invariant and scoped diff; **do not Commit/Push without separate Owner permission**.

### Task 3 — Existing Fake Host Lifecycle, conservative outcome, no real side effects

**Files:**
- Modify: `sandbox/scripts/oc2_slice_b.py` (complete Task 2 placeholder only)
- Modify: `sandbox/tests/test_oc2_slice_b_adapter.py`
- Reuse unchanged: `sandbox/scripts/oc2_host_lifecycle.py`, `sandbox/tests/oc2_host_lifecycle_test_support.py`, `sandbox/tests/test_oc2_host_lifecycle.py`.

**Interfaces:**
- Consumes: Task 2 `run_slice_b(..., ops: SliceBOps)`, verified `VerifiedGuestAuthority`, `SliceBWriterObservation.identity`; existing `HostControlledStopRequest`, `HostControlledStopResult`, `coordinate_host_controlled_stop(request)` and `LifecycleFailure.GUEST_STOP_UNVERIFIED` / `HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED`.
- Produces: `ops.record_result(state, reason, lifecycle_result)` exactly once for completed/uncertain Fake scenarios. Return `0` **only for a fully satisfied offline Fake test scenario** (not production readiness); return `1` for `REJECTED`, `PENDING`, `PRESERVATION_UNVERIFIED` or any observed failure. Use state strings already admitted by the existing Session receipt schema; for observed mismatch record a bounded failure reason and do not reinterpret it as missing evidence.

- [ ] **Step 1 (RED — normal Fake ordering):** Add `test_fake_host_stop_order_and_zero_real_infrastructure_calls`. With the **Task 2 imported Guest Authority** (not `HostFixture`'s synthetic authority), construct `FakeGuestStopper`, `FakeHostControl`, `FakePreserver` and `HostControlledStopRequest` sharing exactly its SessionKey and Writer identity. Adapt the existing `HostFixture` observation/evidence fields to that real imported authority's baseline, receipt SHA and Manifest SHA without bypassing identity validation. Assert the existing validated event sequence `['host.observe', 'guest.stop', 'host.observe', 'host.shutdown', 'host.wait', 'preserve']`; assert **separately** zero calls to real Host observation/start/stop, Docker/sbx/VM, GuestFS, SSH/sudo, credentials, network, inference, Collector and Apply. Fake `host.shutdown` is expected, not an external-effect violation.
- [ ] **Step 2 (RED — unknown precedence):** Add `test_guest_stop_unverified_is_pending_despite_later_success` using `FakeGuestStopper(..., stop_verdict=StopVerdict(STATUS_GUEST_QUIESCENCE_UNVERIFIED, ("stop not proven",)))` (the existing `StopVerdict` requires a nonempty `reasons` tuple for this status). Assert `GUEST_STOP_UNVERIFIED` or `GUEST_QUIESCENCE_UNVERIFIED` in coordinator result, aggregate `PENDING`, `run_slice_b` nonzero, Guest repo and Session receipt retained and no Collector/Apply; later Fake `VM_ISOLATION_VERIFIED` or preservation stage **cannot** turn the result into success. Add `test_restart_epoch_drift_or_isolation_unknown_not_success` and `test_preservation_readback_unknown_remains_unverified` with existing fixture/Host Lifecycle failure controls.
- [ ] **Step 3 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter -v`; expect new lifecycle mapping/order/retention tests to fail before changing Task 2's placeholder.
- [ ] **Step 4 (minimal GREEN):** In `run_slice_b`, call `coordinate_host_controlled_stop(ops.stop_request(authority, writer.identity))` using the **same** Session/Writer authority. Interpret `result.failures` and quiescence stages **before** considering positive stages or preservation disposition. Guest stop unverified ⇒ `PENDING` irrespective of other Fake success. Host identity/isolation unknown ⇒ `PENDING`, preservation unavailable/unverified ⇒ `PRESERVATION_UNVERIFIED`; observed tampering/mismatch ⇒ fail-closed `REJECTED`/bounded failure reason. Never delete Guest originals/Receipt on uncertain outcomes, invoke real ops, treat a Fake stop as live Host proof, or issue a Collection Digest/Apply authorization. The test Fake records outcomes; it does not persist a false production success state.
- [ ] **Step 5 (GREEN + bounded regression):** Run:

```bash
python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2 -v
python3 -m unittest sandbox.tests.test_oc2_slice_b_git sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_image sandbox.tests.test_oc2_slice_b_entrypoint sandbox.tests.test_oc2_slice_b_tty sandbox.tests.test_oc2_writer sandbox.tests.test_oc2_supervisor sandbox.tests.test_oc2_host_lifecycle -v
python3 -m unittest sandbox.tests.test_oc2_e2e -v
```

Expect zero failures/errors in the actual output. Check fixed production `--slice-b` HOLD remains nonzero and the original Phase 1–5 tests still run; no real infrastructure test is launched. 
- [ ] **Step 6 (stop at Owner checkpoint):** Report observed RED and GREEN results, tested/untested claims, scoped diff, Host HEAD/Index/worktree preservation, retained Guest artifacts on uncertainty, and `Live Acceptance: NOT_RUN` / `Host Isolation: NOT_VERIFIED`. If tests fail, report observed failures and stop rather than automatically entering independent remediation/re-review cycles. Do not Commit/Push/PR/Merge without separate explicit Owner authorization.

## Acceptance evidence and completion decision

**Offline success evidence (all required):**

1. Fixed nonzero Production HOLD is proven for ordinary and `--dry-run` Slice B, incompatible flags and attempted Fake bypass; default launcher unchanged.
2. An **actual local Git** baseline is bundled and imported into an **independent** Guest fixture, then separately read back; real receipt/image validation issues `VerifiedGuestAuthority`. No synthetic-only shortcut.
3. Exactly one simulated Writer/TUI transaction and fixed fixture commit can be correlated to the same Session/Writer/HEAD/Manifest/Image identity. The host fixture's HEAD/Index/worktree is unchanged.
4. Existing Fake Host Lifecycle event order includes allowed Fake shutdown; a separate assertion proves zero **real** infrastructure effects.
5. Unverified Guest stop takes precedence over all positive Fake stages, records `PENDING` and retains original/Session evidence; incomplete preservation never becomes verified real recovery.
6. Test logs show genuine RED→GREEN and relevant offline regression PASS. All live acceptance dimensions remain `NOT_RUN`/`NOT_VERIFIED`.

**Fail-closed stop:** Stop immediately on real infrastructure dependency, missing validated Authority, unsupported Git topology, external credential/paid inference need, data-loss/cleanup risk, scope change, or need for extra review/Commit not authorized by Owner. Preserve evidence and identify the affected blocker; do not automatically widen scope or start new tasks.

**Owner checkpoint:** This plan does not adopt Design R0.1.1 or grant implementation authority. Human Owner decides **separately** whether to (a) adopt the Design and (b) authorize **only Tasks 1–3 offline TDD** under this plan. Plan creation itself ends here; no deployment, Host acceptance, Collector/Apply, Release or next-phase automation follows.
