# OC2 — First Offline Vertical Slice B Wiring Implementation Plan R0.1.2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended by the skill) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **For this project, Human Owner's explicit scope and review-loop restrictions override any default automated reviews, follow-on work, or commits.**

**Status:** `PLAN_LIMITED_CORRECTION / DESIGN_ADOPTION_PENDING / IMPLEMENTATION_AUTHORIZATION_HOLD / LIVE_ACCEPTANCE_NOT_RUN`  
**Revision:** R0.1.2 — RG-OC2-B-003 conditional preservation completion and RG-OC2-B-006 Writer identity binding; prior RG-OC2-B-001/002/004/005 retained; historical Plan Task 6 unchanged  
**Date:** 2026-11-21 (JST)  
**Repository:** `yohi/dotfiles-ai`  
**Planning baseline:** `master@34d0c023925d01f2bb4f91a5b61ee7c871c4a5df`; **Reviewed HEAD** `feature/oc2-slice-b-offline-e2e-wiring-design-20261121@61d954d0221e7e36d1c903d7c300124de2f4b742` (Design R0.1.2 and Plan R0.1.1 already committed). Earlier `8ae1d916b830ee2cfa6355429321f7583e13739c` is historical; **this R0.1.2 local correction is not committed**.  
**Goal:** Connect an actual isolated imported Git fixture, checked Guest Authority, Fake Writer/TUI, and existing Fake Host Lifecycle into one test-first offline path, while keeping `oc2 --slice-b` in fixed, nonzero Production HOLD.

**Architecture:** Add a minimal early CLI HOLD in `oc2.py`, separate from the Python-only `run_slice_b(..., ops: SliceBOps)` entry. Inside the test harness use existing safe Git Bundle/import, Session Receipt, Archive/Config-ID validation, and verified Guest Authority APIs; pass Fake Writer and Fake Host Lifecycle adapters via an explicit `SliceBOps`. A passing Fake scenario is offline wiring evidence only, never live Host Isolation proof.

**Tech Stack:** Python 3, `unittest`, local Git CLI on temporary fixture repositories, current OC2 Git/Session/Image/Writer/Host Lifecycle Python modules. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-21-oc2-first-offline-vertical-slice-b-wiring-design.md` R0.1.3 (local limited correction). Context: `docs/superpowers/specs/2026-11-16-oc2-alternative-a-vertical-slice-b-design.md` R0.1.5 and historical `docs/superpowers/plans/2026-11-16-oc2-alternative-a-vertical-slice-b-implementation-plan.md` Task 6. The historical plan's production dispatch instructions are **not** automatically adopted: the current Design R0.1.3 fixed HOLD governs this slice.

## Global Constraints

- **Approval gate:** Planning is authorized by the `writing-plans` invocation; Design adoption and source-code implementation are **separate pending Human Owner decisions**. No execution, source edit, test run, Commit/Push/PR or Merge is authorized by the creation of this plan.
- **Production HOLD / argparse precedence (RG-OC2-B-004):** In the effective raw argv (explicit `argv` or `sys.argv[1:]`), an exact `--slice-b` token or `--slice-b=...` variant always returns **1** with `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED` on stderr **before `argparse.parse_args()`**, even with `--help`, `--version`, unknown or incompatible flags, and `--dry-run`. No stdout help/version is produced in those cases. Without a Slice B selector, ordinary `--help`/`--version` remain argparse `SystemExit(0)`, unknown args remain `SystemExit(2)`, with unchanged diagnostics. The pre-parse HOLD does not touch `SliceBOps`, `run_slice_b`, OAuth, broker, APM/runtime preparation, Docker/sbx, or any real Host/VM action.
- **Harness entry:** Only Python `unittest` calls `run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int` directly with explicit Fake ports. No user CLI flag or environment variable can inject Fake ports or bypass HOLD.
- **Git identity / re-observation (RG-OC2-B-005):** Host admission uses `admit_clean_repo()` and `recheck_host_baseline()`; verified Bundle/Manifest precedes **real `import_guest_baseline()`** into a new separate temporary Guest Git repository. Independently re-observe that Guest with `admit_clean_repo(guest_repo)` and compare against the imported frozen Guest Baseline **immediately before Authority verification**; call `recheck_host_baseline(host_baseline)` and `recheck_host_baseline(imported_guest_baseline)` **again immediately before `ops.run_writer`**. All HEAD/tree/ref/Index/worktree/root identities must match. A stale saved `GitBaseline` must never authorize Writer execution. Never use a synthetic-only authority.
- **Authority:** Create/read an actual `SliceBReceipt` using `create_session_receipt()`, then use `GuestAuthorityVerificationRequest` + `verify_guest_authority_from_host_record()` with existing `FakeGuestImageRunner` **after real Guest re-observation**; this validation API does not itself re-read Guest Git. `VerifiedGuestAuthority` is never constructed directly or extracted from writable Guest `.git` as expected authority.
- **Identity/policy — RG-OC2-B-006:** Preserve `WriterSessionKey`, pinned Runtime SHA-256, Bundle/Manifest, Archive and Config ID, Guest Git HEAD/tree/ref/worktree, full Writer Container ID, StartedAt, one Writer/Session, and existing failure semantics. After `ops.run_writer`, verify `SliceBWriterObservation.identity.container_id` is **exactly 64 lowercase hex**, `.image_id == authority.image_config_id` (`sha256:` + 64 lowercase hex), `.started_at` is nonempty, not the zero sentinel and valid UTC RFC3339 `YYYY-MM-DDTHH:MM:SS[.fraction]Z` (1–9 fraction digits, valid calendar date). Require the exact `(container_id, image_id, started_at)` tuple unchanged in Writer/TUI/fixture/stop observations. Bad/mismatched identities → test-only `REJECTED` / `OBSERVED_MISMATCH` / return `1`; preserve Guest/Receipt, no new Writer/Apply. Existing Writer/Authority/Host Lifecycle contracts remain unchanged.
- **Stop and preservation — RG-OC2-B-003:** Reuse `coordinate_host_controlled_stop()` with `FakeGuestStopper`, `FakeHostControl`, `FakePreserver`. Fake `host.observe`, `host.shutdown`, `host.wait`, `preserve` are allowed in the recorded sequence; they are **not** real Host actions. Guest stop unverified means aggregate `PENDING` even if later Fake stages are successful. `result.failures == ()` is **insufficient** to pass: `OFFLINE_FAKE_PASS` also requires positive verified Guest stop/quiescence, `VM_ISOLATION_VERIFIED` with `host_isolation.verified`, and `PreservationDisposition.VERIFIED` with `OFFLINE_PRESERVATION_VERIFIED`, never the `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED` stage. `CONDITIONALLY_ACCEPTED` maps to test-only `PRESERVATION_UNVERIFIED`/return `1` even without a LifecycleFailure.
- **No real infrastructure:** Zero real VM/Host Docker/sbx/Writer/GuestFS/SSH/sudo calls, credentials, egress, paid inference, Collector/Host Apply. Local temporary Git fixture creation/import/fixture commits are allowed as offline test data, not operations on the user's real checkout.
- **Default behavior:** `bin/oc2` and existing no-flag Phase 1–5 path unchanged. No general launcher migration, credential adjustments, daemon/systemd installation, Sandbox reuse or rollback changes.
- **Receipt vs offline outcome (RG-OC2-B-003):** Production `SliceBReceipt.state` stays strictly within `REJECTED|RUNNING|PENDING|PRESERVATION_UNVERIFIED`; **no offline success state is added**. Fake outcome is a separate test-only `SliceBOfflineOutcome = Literal["OFFLINE_FAKE_PASS", "REJECTED", "PENDING", "PRESERVATION_UNVERIFIED"]`, passed to `ops.record_result` without persisting it into a Receipt. Fully green Fake returns `0` with `OFFLINE_FAKE_PASS` while production Receipt remains conservatively `PENDING` (no real acceptance evidence). All other Fake outcomes return `1`; observed mismatch uses `REJECTED` with reason `OBSERVED_MISMATCH`, not `NOT_VERIFIED`.
- **Data retention:** On uncertainty, keep Guest original and private Session evidence; never claim real preservation or live Host Isolation `PASS` from Fake observations. Live acceptance stays `NOT_RUN`/`NOT_VERIFIED`.
- **Exit:** A bounded RED→GREEN→REFACTOR cycle plus relevant offline regressions and a short evidence report, then **Human Owner Checkpoint**. No automatic independent review, correction loop, later task, PR, release, or real Host trial. Any future Commit/Push requires separate explicit approval.

## File structure and ownership

| Path | Future responsibility |
| --- | --- |
| Modify `sandbox/scripts/oc2.py` | Raw-argv pre-parse fixed HOLD for `--slice-b` before argparse help/version; all default paths untouched |
| Create `sandbox/scripts/oc2_slice_b.py` | Plan Task 6-compatible internal orchestrator; narrow `SliceBOps` protocol and offline-only result mapping |
| Modify `sandbox/tests/test_oc2.py` | Production CLI HOLD, `--dry-run`/incompatible-flags/env non-bypass, default launcher regression |
| Create `sandbox/tests/test_oc2_slice_b_adapter.py` | Actual isolated Git import + verified authority + same-Writer Fake TUI/fixture + Fake Host Lifecycle and negatives |
| Reuse without changes | `oc2_slice_b_git.py`, `oc2_slice_b_session.py`, `oc2_slice_b_image*.py`, `oc2_writer.py`, `oc2_supervisor.py`, `oc2_host_lifecycle.py`, `oc2_host_control.py`, `sandbox/oc2_slice_b/offline_fixture.py`, `sandbox/tests/oc2_slice_b_test_support.py`, `sandbox/tests/oc2_host_lifecycle_test_support.py` |

**Scope control:** Do not add a new production `--fake`, gate-override environment variable, general-purpose shell executor, separate Collect/Apply module, or new image/authority schema. A demonstrated RED failure may justify a narrow fix to an existing dependency only after explicit Owner scope approval; do not expand this plan automatically.

## Review Focus

The five consequential failure classes that each have a test below:

1. `--slice-b` combined with `--help`, `--version`, unknown options, `--dry-run`, credential/inference or Fake-looking environment variables accidentally bypassing HOLD → Task 1 tests raw-argv precedence, fixed nonzero HOLD and zero effects.
2. Dirty/changed Host baseline or Guest repository changed **after Import** or **after Authority verification** → Task 2 asserts fresh Host+Guest re-observation, pre-Writer `REJECTED`, original evidence retained.
3. Forged Guest evidence, changed Archive/Config-ID/Runtime/Manifest or synthetic authority replacing real import, or **Fake Writer Image ID different from pinned Config ID/invalid or changed StartedAt/full CID** → Task 2 asserts rejection and an actual `import_guest_baseline()` readback; Task 3 forbids later success.
4. Fake `host.shutdown` mistaken for a real Host call, or wrong event ordering → Task 3 separately asserts correct Fake sequence and zero real infrastructure calls.
5. Fake success persisted as `RUNNING`/`SUCCESS`, `result.failures == ()` mistaken for success with **`CONDITIONALLY_ACCEPTED`**, or Guest stop unverified after positive stages → Task 3 tests `PreservationDisposition.VERIFIED` requirement, conditional preservation → `PRESERVATION_UNVERIFIED`, test-only outcome vs Receipt, retained originals and no live PASS/Collect/Apply.

---

### Task 1 — Fixed Production CLI HOLD (no execution dispatch)

**Files:**
- Modify: `sandbox/scripts/oc2.py` (`main()` raw argv check **before** `argparse.ArgumentParser` / `parse_args`)
- Test: `sandbox/tests/test_oc2.py`

**Interfaces:**
- Consumes: existing `main(argv: list[str] | None = None) -> int` and existing `Stop`/`OC2_STOP` error conventions.
- Produces: any raw argv containing `--slice-b` (or `--slice-b=...`) exits **1** with exact `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED` on stderr, **empty stdout**, before argparse help/version/unknown-argument handling and before any runtime/credential/VM effects. Without this selector, legacy argparse help/version raise `SystemExit(0)` and unknown options raise `SystemExit(2)` with their existing output. No import or invocation of `run_slice_b()` from CLI.

- [ ] **Step 1 (RED):** Add `test_slice_b_hold_precedes_help_version_and_unknown`, `test_slice_b_dry_run_cannot_bypass_hold`, `test_slice_b_rejects_credential_and_inference_modes`, `test_slice_b_env_cannot_inject_fake`, and `test_legacy_argparse_help_version_unknown_unchanged` in `sandbox/tests/test_oc2.py`. Use `oc2.main(["--slice-b", "--help"])`, `... --version`, `... --unknown`, `... --dry-run`, `... --use-host-broker`, `... --slice-b=1` and selector-free `--help`/`--version`/`--unknown`. For selected cases assert **return `1`**, exact stderr `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED\n`, stdout empty, and zero `run_slice_b`/external-effect calls. For selector-free cases assert normal argparse `SystemExit(0)` (help/version) or `SystemExit(2)` (unknown); no runtime side effect. Run a subprocess check via `python3 sandbox/scripts/oc2.py --slice-b --help` and `--slice-b --version` with isolated nonsecret environment; assert same HOLD.
- [ ] **Step 2 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2 -v`; expect at least the new fixed-HOLD precedence assertions to fail before source change. Do not misreport argparse exit `0`/`2` as GREEN.
- [ ] **Step 3 (minimal GREEN):** At the start of `main()`, derive effective argv exactly as `argv if argv is not None else sys.argv[1:]`. **Before building the ArgumentParser**, if a token is `--slice-b` or begins with `--slice-b=`, write `OC2_STOP: SLICE_B_LIVE_NOT_ACCEPTED` with newline to stderr and return `1`. Do not call `parse_args`, instantiate `SliceBOps`, or touch runtime/credential/Host. No change to selector-free parser or existing Phase 1–5 dispatch; never expose a bypass option/env.
- [ ] **Step 4 (verify GREEN):** Re-run `python3 -m unittest sandbox.tests.test_oc2 -v` and selected subprocess commands; check exact exit codes/stdout/stderr and zero forbidden effects. Existing no-selector `--help`, `--version`, unknown and default Phase 1–5 tests remain unchanged.
- [ ] **Step 5:** Record observed RED/GREEN output and scoped diff; **no Commit/Push without separate Owner permission**.

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

Define only the internal data needed for this one offline scenario in `oc2_slice_b.py`. `SliceBOfflineOutcome` is a **test-only** `Literal["OFFLINE_FAKE_PASS", "REJECTED", "PENDING", "PRESERVATION_UNVERIFIED"]`, not `SliceBReceipt.state`:

```python
from typing import Literal

SliceBOfflineOutcome = Literal[
    "OFFLINE_FAKE_PASS", "REJECTED", "PENDING", "PRESERVATION_UNVERIFIED"
]

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
    def record_result(self, outcome: SliceBOfflineOutcome, reason: str | None,
                      result: HostControlledStopResult | None) -> None: ...
```

**Orchestrator-bound observation — RG-OC2-B-006:** Validate `SliceBWriterObservation.identity` before accepting any Fake Writer/TUI/fixture result. `identity.container_id`: full 64 lowercase hexadecimal CID (existing `validate_container_id` behavior); `identity.image_id`: exact `authority.image_config_id`, with `sha256:` + 64 lowercase hex; `identity.started_at`: UTC RFC3339 `YYYY-MM-DDTHH:MM:SS[.fraction]Z` with 1–9 fractional digits when present, a real calendar datetime, neither empty nor Docker zero sentinel. The same **unmodified** `(container_id, image_id, started_at)` must correlate the Fake observation, TUI/fixture evidence and `stop_request(authority, writer.identity)`. Never infer trust from the presence of a `WriterIdentity` dataclass alone or silently substitute another Writer. Detected mismatch → `REJECTED` / `OBSERVED_MISMATCH` / `1`, retain Guest/Receipt and no Apply. This is an Orchestrator check only, not a modification to existing Writer or Authority validators.

`SliceBOps` is supplied **only by the test**; no CLI or production implementation. The existing `GuestImageRunner` interface is implemented by `FakeGuestImageRunner` in the harness, whose `load_image()` operates on a test archive only. An observed Writer commit from a Fake is **not** production acceptance evidence. `record_result` records the **test-only outcome**, never writes a new `SliceBReceipt.state` or a production acceptance claim; it is not a Collection or Apply capability. `dry_run=True` in this internal function exits `1` before `ops.inputs()` or any fixture mutation; it never changes the CLI HOLD policy.

- [ ] **Step 1 (RED):** Add `test_imported_guest_git_and_verified_authority_reach_same_writer`. Use a temporary **actual clean local Git repository** (as in `test_oc2_slice_b_session.py`) to create a real commit, `admit_clean_repo()` and a separate `bundle_path`. Feed `SliceBOfflineInputs` through the test Fake. Require `run_slice_b()` to call `build_verified_bundle()`/`verify_bundle_manifest()`, `import_guest_baseline()` into an **absent, separate** Guest path, `create_session_receipt()`, `verify_guest_authority_from_host_record(GuestAuthorityVerificationRequest(...), FakeGuestImageRunner(pin))`, and `build_start_message()`. After Import, require a **fresh** `admit_clean_repo(guest_repo_path)` and equality with the imported Guest baseline before calling `verify_guest_authority_from_host_record`. Before Fake Writer start, require fresh `recheck_host_baseline(host_baseline)` and `recheck_host_baseline(imported_guest_baseline)` after the Authority verification. Assert Guest HEAD/tree/ref/worktree equal the admitted Host baseline; **Guest Index** matches the immutable post-Import Guest baseline, while the **Host Index** is rechecked against its own originally admitted Host baseline (do not require byte-identical Host/Guest Git Index files); the **Guest root differs from Host**, and Authority/Receipt/Manifest/Runtime/Config ID/SessionKey match. The Fake's `run_writer` checks the trusted start message and returns a full valid 64-lowercase-hex `WriterIdentity.container_id`, `image_id` exactly equal to `authority.image_config_id`, and valid UTC `started_at`; it simulates TUI exit `0`, invokes existing deterministic `run_offline_fixture()` against the separate imported Guest repo, and records the exact single commit OID. Require the exact same Writer tuple in TUI/fixture/stop evidence; identity mismatch is never Fake success. Independently assert its parent is Host HEAD, exact fixture blob/path, and unchanged Host HEAD/Index/worktree. This test must not substitute `make_verified_authority()` for the real import/receipt flow.
- [ ] **Step 2 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter -v`; expect failure from missing `oc2_slice_b.py` or missing `run_slice_b`, not from an unrelated dependency or an actual external operation.
- [ ] **Step 3 (minimal GREEN):** In `oc2_slice_b.py`, define the above protocol/data types and `run_slice_b` only. First reject `dry_run=True`, invalid workspace/Host baseline and changed baseline; then run existing bounded Bundle+Manifest and Guest import; **immediately re-observe actual Guest** with `admit_clean_repo(guest_repo_path)` and require equality with the imported immutable Guest Baseline. Create a private `SliceBReceipt` initially `state='PENDING'`, `reason='NOT_RUN'`, `writer_id=None`, `started_at=None`, with the pinned `ImagePin` and `runtime_sha256`; create/verify the receipt via the real APIs; then call `verify_guest_authority_from_host_record()` with the injected `image_runner` and **freshly re-observed Guest Baseline**. Re-run `recheck_host_baseline(host_baseline)` **and** `recheck_host_baseline(imported_guest_baseline)` **again immediately before** Fake Writer start; issue `build_start_message()` only after verifying authority. Call exactly one Fake Writer operation; before accepting its TUI/fixture result validate full CID, exact Image Config ID equality to the sealed Authority, well-formed nonzero UTC StartedAt and unchanged Writer tuple across Fake observation/TUI/stop. Reject incorrect Image ID, malformed CID, changed/invalid StartedAt, nonzero TUI status, missing fixture evidence or identity drift as `REJECTED`/`OBSERVED_MISMATCH`/return `1`, preserving Guest/Receipt; never launch a replacement Writer. Do not manufacture a `VerifiedGuestAuthority`, run a real writer, shell out to Docker or call Collect/Apply. Defer lifecycle mapping to Task 3 with a fail-closed placeholder result (nonzero / `PENDING`, not falsely complete).
- [ ] **Step 4 (verify GREEN for the admission/Writer boundary):** Re-run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2_slice_b_git sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_image sandbox.tests.test_oc2_slice_b_entrypoint -v`; expect each tested admission/Writer behavior to pass, with lifecycle-completion assertions reserved for Task 3. Do not declare the full E2E complete yet.
- [ ] **Step 5 (security negatives):** Add tests `test_dirty_or_changed_host_rejected_before_writer`, `test_guest_path_already_exists_or_overlaps_host_rejected`, `test_manifest_archive_runtime_or_config_id_drift_rejected`, `test_unverified_guest_baseline_or_forged_authority_rejected`, `test_guest_mutated_after_import_rejected_before_authority`, `test_guest_mutated_after_authority_rejected_before_writer`, `test_host_changed_after_authority_rejected_before_writer`, `test_writer_identity_or_tui_failure_preserves_guest`, `test_writer_image_id_differs_from_authority_rejected`, `test_writer_invalid_full_cid_rejected`, and `test_writer_invalid_or_changed_started_at_rejected`. For Image-ID negative Fake, return another syntactically valid `sha256:` + 64-hex ID **different from** `authority.image_config_id`, and assert `REJECTED`/`OBSERVED_MISMATCH`, return `1`, Guest/Receipt retained, no Fake success/Host Apply and **no replacement Writer**. For StartedAt negative, test missing/zero/invalid timestamp and changed value on readback/stop correlation. For the two Guest mutation tests modify HEAD/Index/worktree through controlled local fixture actions after Import or after Authority issuing (e.g. a one-time monkeypatched wrapper around those calls), then assert a **fresh real Git observation** catches the drift; a stale stored `GitBaseline` cannot enable Writer. Assert test-only `REJECTED` with reason `OBSERVED_MISMATCH` for independently detected mismatch, Guest/Receipt retained if created and zero `run_writer` after prelaunch rejection. Never alter the user's Host checkout. Follow RED→GREEN for these assertions. Reuse existing validators; do not weaken them.
- [ ] **Step 6:** Record test outputs, private-fixture file/Host checkout invariant and scoped diff; **do not Commit/Push without separate Owner permission**.

### Task 3 — Existing Fake Host Lifecycle, conservative outcome, no real side effects

**Files:**
- Modify: `sandbox/scripts/oc2_slice_b.py` (complete Task 2 placeholder only)
- Modify: `sandbox/tests/test_oc2_slice_b_adapter.py`
- Reuse unchanged: `sandbox/scripts/oc2_host_lifecycle.py`, `sandbox/tests/oc2_host_lifecycle_test_support.py`, `sandbox/tests/test_oc2_host_lifecycle.py`.

**Interfaces:**
- Consumes: Task 2 `run_slice_b(..., ops: SliceBOps)`, verified `VerifiedGuestAuthority`, **Orchestrator-checked** `SliceBWriterObservation.identity` (full CID, pinned Config Image ID, valid/stable StartedAt); existing `HostControlledStopRequest`, `HostControlledStopResult`, `coordinate_host_controlled_stop(request)` and `LifecycleFailure.GUEST_STOP_UNVERIFIED` / `HostLifecycleStage.GUEST_QUIESCENCE_UNVERIFIED`; existing `PreservationDisposition` and `HostLifecycleStage.OFFLINE_PRESERVATION_VERIFIED` / `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED`.
- Produces: `ops.record_result(outcome: SliceBOfflineOutcome, reason: str | None, lifecycle_result: HostControlledStopResult | None)` exactly once on completed/uncertain Fake paths. The **only** possible outcomes are `OFFLINE_FAKE_PASS`, `PENDING`, `PRESERVATION_UNVERIFIED`, `REJECTED`; these are **test records only**, never production Receipt values. Return `0` iff `outcome == "OFFLINE_FAKE_PASS"` **and all** checks hold: exact Writer/Authority Image Config ID + full CID + valid/stable StartedAt + verified Fake TUI/fixture + actual Host/Guest admission; `result.failures == ()`; `result.guest_verdict is not None and result.guest_verdict.verified`; `GUEST_QUIESCENCE_VERIFIED` stage present, `GUEST_QUIESCENCE_UNVERIFIED` absent; `result.host_isolation is not None and result.host_isolation.verified` plus `VM_ISOLATION_VERIFIED` stage; `result.preservation is not None and result.preservation.disposition is PreservationDisposition.VERIFIED` plus `OFFLINE_PRESERVATION_VERIFIED` stage, and `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED` absent. An empty `failures` tuple **alone is never sufficient**; every non-green result returns `1`. For observed drift/tamper record `REJECTED` with bounded `OBSERVED_MISMATCH` reason (not `NOT_VERIFIED`). For Guest-stop unverified record `PENDING` even if later Fake stages succeed. Keep persistent `SliceBReceipt.state` in its existing schema (normally `PENDING` for Fake-green), never persist `OFFLINE_FAKE_PASS`, and never imply real preservation/Host Isolation PASS.

- [ ] **Step 1 (RED — normal Fake ordering):** Add `test_fake_host_stop_order_and_zero_real_infrastructure_calls`. With the **Task 2 imported Guest Authority** (not `HostFixture`'s synthetic authority), construct `FakeGuestStopper`, `FakeHostControl`, `FakePreserver` and `HostControlledStopRequest` sharing exactly its SessionKey and Writer identity. Adapt the existing `HostFixture` observation/evidence fields to that real imported authority's baseline, receipt SHA and Manifest SHA without bypassing identity validation. Assert `record_result("OFFLINE_FAKE_PASS", None, ...)` **only** when `result.failures == ()`, Guest stop/quiescence is positively verified, `host_isolation.verified` and `VM_ISOLATION_VERIFIED` are present, and `preservation.disposition is PreservationDisposition.VERIFIED` plus `OFFLINE_PRESERVATION_VERIFIED` (not conditional) are present; return `0`, keep production Receipt `PENDING`, and preserve the exact matching Writer `(CID, Config ID, StartedAt)` tuple throughout. Assert the existing validated event sequence `['host.observe', 'guest.stop', 'host.observe', 'host.shutdown', 'host.wait', 'preserve']`; assert **separately** zero calls to real Host observation/start/stop, Docker/sbx/VM, GuestFS, SSH/sudo, credentials, network, inference, Collector and Apply. Fake `host.shutdown` is expected, not an external-effect violation.
- [ ] **Step 2 (RED — unknown precedence):** Add `test_guest_stop_unverified_is_pending_despite_later_success` using `FakeGuestStopper(..., stop_verdict=StopVerdict(STATUS_GUEST_QUIESCENCE_UNVERIFIED, ("stop not proven",)))` (the existing `StopVerdict` requires a nonempty `reasons` tuple for this status). Assert `GUEST_STOP_UNVERIFIED` or `GUEST_QUIESCENCE_UNVERIFIED` in coordinator result, `record_result("PENDING", "GUEST_QUIESCENCE_UNVERIFIED", ...)`, `run_slice_b` return `1`, Guest repo and Session receipt retained and no Collector/Apply; later Fake `VM_ISOLATION_VERIFIED` or preservation stage **cannot** turn the result into success. Add `test_restart_epoch_drift_or_isolation_unknown_not_success`, `test_preservation_readback_unknown_remains_unverified`, **`test_conditionally_accepted_preservation_never_passes_even_without_failures`**, `test_observed_digest_mismatch_is_rejected_not_unknown`, `test_wrong_writer_image_id_never_reaches_fake_success`, and `test_fake_success_does_not_persist_receipt_success` with existing fixture/Host Lifecycle failure controls. For conditional preservation, reuse the pattern of `sandbox/tests/test_oc2_host_lifecycle.py::test_conditionally_accepted_preservation_has_distinct_stage`: inject `PreservationDecision(PreservationDisposition.CONDITIONALLY_ACCEPTED, (PreservationFailure.INDEX_MISMATCH_REQUIRES_OWNER,))`, assert `OFFLINE_PRESERVATION_CONDITIONALLY_ACCEPTED` in `result.stages`, `OFFLINE_PRESERVATION_VERIFIED` absent, and **even if `result.failures == ()`** record `PRESERVATION_UNVERIFIED`, return `1`, retain Guest/Receipt, and forbid fake/real Apply.
- [ ] **Step 3 (prove RED):** Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter -v`; expect new lifecycle mapping/order/retention tests to fail before changing Task 2's placeholder.
- [ ] **Step 4 (minimal GREEN):** In `run_slice_b`, call `coordinate_host_controlled_stop(ops.stop_request(authority, writer.identity))` using the **same** Session/Writer authority. Interpret `result.failures` and quiescence stages **before** considering positive stages or preservation disposition. Precedence: independently observed Git/Writer/Image/StartedAt/digest/commit mismatch, or `preservation.disposition is MISMATCH` → `REJECTED` with reason `OBSERVED_MISMATCH` (never an unverified euphemism); else Guest stop/quiescence unverified → `PENDING` with reason `GUEST_QUIESCENCE_UNVERIFIED` even if later Fake stages succeed; else Host identity/isolation uncertainty → `PENDING`; else preservation missing/`UNVERIFIED`/**`CONDITIONALLY_ACCEPTED`** or missing verified preservation stage → `PRESERVATION_UNVERIFIED` (return `1`, even with no `LifecycleFailure`); else any other missing affirmative condition or remaining coordinator failure → bounded `PENDING` (return `1`); **only** when all explicit conditions in Task 3 Interfaces are satisfied → `OFFLINE_FAKE_PASS` with reason `None`. Map that final test-only outcome to return `0` for `OFFLINE_FAKE_PASS`, return `1` otherwise. `record_result` is invoked once and **never mutates the Session Receipt to Fake success**. Never delete Guest originals/Receipt on uncertain outcomes, invoke real ops, treat a Fake stop as live Host proof, or issue a Collection Digest/Apply authorization. The test Fake records outcomes; it does not persist a false production success state.
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

1. Fixed nonzero Production HOLD is proven for `--slice-b` with normal args, `--dry-run`, `--help`, `--version`, unknown/incompatible flags and attempted Fake bypass **before argparse**; without Slice B, help/version/unknown argparse behavior and default launcher remain unchanged.
2. An **actual local Git** baseline is bundled/imported into an independent Guest fixture; actual Guest Git is **freshly re-observed before Authority verification and again before Writer start**, with Host rechecked before Writer. Real receipt/image verification issues `VerifiedGuestAuthority`. Mutations after Import or after Authority are rejected before Writer; no synthetic-only shortcut.
3. Exactly one simulated Writer/TUI transaction and fixed fixture commit can be correlated to the same Session/Writer/HEAD/Manifest/Image identity, including a 64-lowercase-hex Full CID, `WriterIdentity.image_id == authority.image_config_id`, valid nonzero UTC StartedAt, and unchanged tuple across TUI/fixture/stop. Wrong Fake Image ID and invalid/changed StartedAt result in `REJECTED`/`OBSERVED_MISMATCH`/nonzero without replacement Writer. The Host fixture's HEAD/Index/worktree is unchanged.
4. Existing Fake Host Lifecycle event order includes allowed Fake shutdown; a separate assertion proves zero **real** infrastructure effects.
5. A test-only `OFFLINE_FAKE_PASS` outcome maps to return `0` **only** with affirmative Guest stop/quiescence, Host isolation, `PreservationDisposition.VERIFIED` plus stage and `result.failures == ()`, **without** a production Receipt success state. Conditional preservation (`CONDITIONALLY_ACCEPTED`/conditional stage) is `PRESERVATION_UNVERIFIED`/`1` even when the failure tuple is empty. Unverified Guest stop takes precedence over positive Fake stages, records `PENDING` and retains originals; independently observed mismatch maps to `REJECTED`/`OBSERVED_MISMATCH`. No Fake event becomes verified real recovery.
6. Test logs show genuine RED→GREEN and relevant offline regression PASS. All live acceptance dimensions remain `NOT_RUN`/`NOT_VERIFIED`.

**Fail-closed stop:** Stop immediately on real infrastructure dependency, missing validated Authority, unsupported Git topology, external credential/paid inference need, data-loss/cleanup risk, scope change, or need for extra review/Commit not authorized by Owner. Preserve evidence and identify the affected blocker; do not automatically widen scope or start new tasks.

**Owner checkpoint:** This plan does not adopt Design R0.1.3 or grant implementation authority. Human Owner decides **separately** whether to (a) adopt the Design and (b) authorize **only Tasks 1–3 offline TDD** under this plan. Plan creation itself ends here; no deployment, Host acceptance, Collector/Apply, Release or next-phase automation follows.
