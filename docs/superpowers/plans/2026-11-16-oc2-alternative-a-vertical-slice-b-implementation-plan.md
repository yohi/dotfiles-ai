# OC2 Alternative A — Vertical Slice B Implementation Plan R0.1 (DRAFT / BLOCKED)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (native execution) or `superpowers:subagent-driven-development` only **after** Human Owner expressly authorizes implementation. Steps use checkboxes (`- [ ]`) for tracking. No implementation or review loop is authorized merely by this plan.

**Goal:** In a Mountless Sandbox, use one non-privileged Writer to launch OpenCode v2.2.5 TUI and then run a deterministic offline edit/test/fixture Git Commit based on the Host's exact Clean Local Branch HEAD, preserving Guest evidence and leaving Host Git untouched.

**Architecture:** Extend `oc2.py` with an explicit `--slice-b` dispatch to a small Host/Guest adapter. A strictly screened Git Bundle seeds an independent Session-private Guest repository. A digest-pinned, trusted Host-prebuilt Writer image runs one fixed PID 1 entrypoint; the Trusted Guest Supervisor attaches to the same container ID, observes exit, and retains the Guest original with a conservative `PENDING` disposition.

**Tech Stack:** Python 3 and `unittest` (matching existing tests), Git CLI in a sanitized/locked-down configuration, Docker CLI/OCI image archive, Docker Sandboxes `sbx`, pinned OpenCode v2.2.5.

**Spec:** `docs/superpowers/specs/2026-11-16-oc2-alternative-a-vertical-slice-b-design.md` **R0.1.3**, commit `09fda5deb85957c98343d4e351c1326d13e2bec6`, branch `feature/oc2-alta-vertical-slice-b-design-20261116`. Parent design: `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md` R0.2.

**Plan status:** `PLAN_CANDIDATE / DESIGN_FORMAL_ADOPTION_PENDING / IMPLEMENTATION_BLOCKED`. F-004 is document-resolved; AC-08/09 live validation is `NOT_RUN`. **F-002 remains `UNRESOLVED`** until digest-qualified image resolution after Docker import is evidenced. There is **no Implementation GO** and no authorization for Docker/Sandbox/TTY, source modifications, PR, merge, Collect or Host Apply. This plan is not a finding closure or permission to start work.

## Global Constraints

- Scope: Clean **Local Branch** with existing HEAD only. Reject Dirty/intent-to-add, detached, submodule, linked-worktree, shallow/partial/alternates, sparse/split-index, LFS/filter-dependent and uninspectable histories before side effects. Host-side intent-to-add remains prohibited.
- Host Baseline: exact HEAD Commit OID, branch, Tree OID, Index digest and Working Tree manifest; selective fully inspected Git Bundle and separate SHA-256-bound manifest. No `.git` copy or Host RW mount.
- Writer: **UID/GID 10001**, `--network none`, `--cap-drop ALL`, `no-new-privileges`, read-only rootfs, bounded resources, `--restart no`, Session-only Guest Repo RW + validated tmpfs, no privileged socket or credential.
- Image: trusted Host offline prebuild, verified archive, trusted Guest `docker load`, exact *locally resolvable* `repository@sha256:<manifest-digest>` matching `WriterSpec.image_ref` and image ID. Failure = **BLOCKED**; tag, bare image ID, pull or privileged fallback forbidden.
- Runtime: **OpenCode v2.2.5** and non-secret pinned Phase 5 assets only; no OAuth/Mixin/Proxy, Provider request, external inference or network installation.
- Writer execution: fixed image `Config.Entrypoint=["/opt/oc2/slice-b/entrypoint"]`, `WriterSpec.command=("run",)`, one PID 1; exact full 64-hex container ID. Dedicated bounded `docker attach` transport with stdin+TTY, no `docker exec`.
- Protocol: once-only `OC2_SLICE_B_START <session-generation>` line, **30-second deadline**. TUI exit `0` is required before fixture. Never reinterpret TUI render as AI inference success.
- Fixture: `/workspace/oc2-slice-b-fixture.txt`, exact UTF-8 bytes `OC2 Slice B offline fixture PASS\n`, fixed Python assertion, then **Guest Writer only** `git add -N -- oc2-slice-b-fixture.txt` followed by `git commit --only --no-verify --no-gpg-sign -m "test(oc2): verify offline writer fixture" -- oc2-slice-b-fixture.txt`; fixed Author/Committer `OC2 Slice B Fixture <oc2-slice-b-fixture@example.invalid>`, deterministic date/locale, no signing/hooks/filter. No change to non-fixture staged/unstaged state.
- Commit evidence: **exactly one Parent OID == Host Baseline HEAD**, exactly one changed path, expected regular Blob bytes/SHA-256, same SessionKey + Container ID + image ID + StartedAt. Writer self-reports alone are not proof.
- Stopping: never manufacture `STOPPED_VERIFIED`; quiescence unknown => `PENDING / GUEST_QUIESCENCE_UNVERIFIED`. Preserve Guest repository and private Session receipt. If preservation cannot be evidenced => `PRESERVATION_UNVERIFIED` (not complete). No Collector, Collection Digest, ApplyAuthorization or Host Apply.
- No automatically spawned separate reviewer, correction task, PR, merge or next phase. After one bounded execution/verification cycle, return to Human Owner checkpoint; don't extend work solely to eliminate findings.

## File Structure / Owned Interfaces

| File | Responsibility |
| --- | --- |
| Modify `sandbox/scripts/oc2.py` | Early `--slice-b` dispatcher; legacy path unchanged |
| Create `sandbox/scripts/oc2_slice_b.py` | Host/Guest flow orchestration and dependency-injected effects |
| Create `sandbox/scripts/oc2_slice_b_git.py` | Host Clean validation, historical object/secret checks, selective Bundle, Guest baseline verification |
| Create `sandbox/scripts/oc2_slice_b_session.py` | Minimal private immutable Session receipt, transitions, identity/preservation readback |
| Create `sandbox/scripts/oc2_slice_b_image.py` | Trusted Host image/archive manifest and Guest image identity verification; no fallback |
| Create `sandbox/oc2_slice_b/Dockerfile` | Offline-only fixed image build inputs and digest-pinned base |
| Create `sandbox/oc2_slice_b/entrypoint.py` | Fixed PID 1 startup barrier → TUI → fixture control flow |
| Create `sandbox/oc2_slice_b/offline_fixture.py` | Fixed fixture edit/test/intent-to-add/pathspec Commit inside Writer |
| Modify `sandbox/scripts/oc2_writer.py` | Minimal stdin/TTY validation and exact baked-in image command contract |
| Modify `sandbox/scripts/oc2_supervisor.py` | Identity-bound narrow attach capability; existing Docker lifecycle allowlist unchanged |
| Create `sandbox/scripts/oc2_slice_b_acceptance.py` | Constrained read-only Guest Git object/Session evidence checker; **not Collector** |
| Create `sandbox/tests/test_oc2_slice_b_{git,session,image,entrypoint,tty,acceptance,adapter}.py` | Isolated `unittest` TDD checks |
| Modify `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, `sandbox/tests/test_oc2.py` | Existing-contract regression/negative tests only |

Interfaces introduced by the **plan** below are proposed implementation names, **not claims about current code**. Use the existing `oc2_writer.WriterSessionKey`, `WriterSpec`, `WriterIdentity`, and `GuestSupervisor` types; never replace their identity/security model.

## Review Focus — five inputs with owning tests

1. **Clean-looking index with `CE_INTENT_TO_ADD` or unknown extension:** reject before Sandbox access (`Task 1: test_reject_ita_and_unknown_index`).
2. **Historical secret blob despite a Clean current tree:** abort Bundle transfer (`Task 1: test_reject_secret_in_ancestor`).
3. **Loaded image has matching archive hash but no locally resolvable digest reference:** F-002 remains BLOCKED (`Gate F-002`, `Task 3: test_reject_unresolvable_digest`).
4. **TUI stages an unrelated file:** fixed fixture commit excludes it and preserves Index/Working Tree (`Task 4: test_other_staged_changes_survive`).
5. **Attach to changed/short/foreign container ID or lost process exit evidence:** reject/no fixture, retain PENDING (`Task 5: test_attach_identity_mismatch`, `Task 7: test_unknown_exit_retains_pending`).

---

## Gate G0 — F-002 feasibility and Owner authority (STOP before implementation)

**Existing blocker; NOT a new implementation task or a claimed PASS.**

- [ ] Human Owner **formally decides whether to accept Design R0.1.3 with F-002 HOLD**; acceptance of this plan is not Implementation GO.
- [ ] Obtain **separate explicit approval** for a disposable, credential-free Docker/Sandbox **evidence check only**; without it, mark `NOT_RUN / OWNER_APPROVAL_REQUIRED` and **STOP**. Do not create/edit source code.
- [ ] Use a disposable locally vetted digest-qualified image/archive and a distinct disposable Mountless Sandbox; verify Host image config ID, archive SHA-256 and expected repo digest; transfer with `sbx cp` while staying within the authorized Sandbox scope.
- [ ] Trusted Guest imports using `docker load`, then checks `docker image inspect repository@sha256:<manifest-digest>` **locally**, confirms expected config ID and absence of a registry pull, and records exact command/result/environment identity without secrets.
- [ ] If digest-qualified resolution fails, is inconclusive or is not authorized, record `F-002 = UNRESOLVED / IMPLEMENTATION_BLOCKED`, preserve any authorized proof artifacts, and **STOP**. **No tag/ID fallback, no new architecture decision here.**
- [ ] Only on confirmed bounded feasibility evidence may the Human Owner consider **separate Implementation GO**. Implementation is not auto-started when G0 passes.

**Evidence limit:** G0 proves the tested image-transfer/reference-resolution mechanism only, **not** that the actual OpenCode Writer image, TUI or full workflow runs. Live AC-04–13 remain `NOT_RUN` without independent Sandbox/TTY permission.

## Task 1 — Host Git admission and selective Bundle

**Files:** Create `sandbox/scripts/oc2_slice_b_git.py`; Test `sandbox/tests/test_oc2_slice_b_git.py`.

**Interfaces:** `@dataclass(frozen=True) class GitBaseline: root: Path; branch_ref: str; head_oid: str; tree_oid: str; object_format: str; index_sha256: str; worktree_sha256: str`; `def admit_clean_repo(root: Path) -> GitBaseline`; `@dataclass(frozen=True) class BundleArtifact: path: Path; sha256: str; baseline: GitBaseline`; `def build_verified_bundle(baseline: GitBaseline, output: Path) -> BundleArtifact`; `def recheck_host_baseline(baseline: GitBaseline) -> None`. Raise `SliceBGitRejected` on rejection; no Host Git writes.

- [ ] Write `test_accept_clean_branch`, `test_reject_dirty_staged_unstaged_untracked`, `test_reject_ita_and_unknown_index`, `test_reject_detached_submodule_sparse_partial_alternates`, `test_reject_secret_in_ancestor`, `test_bundle_only_pinned_head` and `test_detect_host_change_without_index_mutation` using disposable Git repos and injected safe command runner.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_git -v`; expect **FAIL** for absent interface.
- [ ] Implement the strict Index v2/v3 flag/checksum reader or reuse a demonstrably equivalent existing reader; use sanitized noninteractive Git CLI with disabled optional locks/hooks/filter/remote behavior, explicit argv and bounded object scan. Pin HEAD/branch/tree and transfer only selected ref history; reject unbounded or uninspectable data.
- [ ] Run the same suite; expect PASS, with any policy-unknown input rejected rather than skipped.
- [ ] Commit only Task 1 files **after Implementation GO**: `test(oc2): admit clean Git baseline and verify bundle`.

## Task 2 — Session receipt and independent Guest baseline

**Files:** Create `sandbox/scripts/oc2_slice_b_session.py`; Test `sandbox/tests/test_oc2_slice_b_session.py`; implement import/readback in `sandbox/scripts/oc2_slice_b_git.py` and its tests.

**Interfaces:** `@dataclass(frozen=True) class SliceBReceipt: key: WriterSessionKey; baseline: GitBaseline; bundle_sha256: str; state: str; reason: str | None; writer_id: str | None; image_id: str | None; started_at: str | None`; `def create_session_receipt(state_root: Path, receipt: SliceBReceipt) -> Path`; `def update_session_receipt(path: Path, receipt: SliceBReceipt) -> None`; `def verify_session_receipt(path: Path, expected_key: WriterSessionKey) -> SliceBReceipt`; `def import_guest_baseline(bundle: BundleArtifact, repo: Path) -> GitBaseline` (trusted Guest only). The existing `oc2_session.py` **v2** receipt is not silently converted to a completed v3 lifecycle.

- [ ] Write `test_refuse_receipt_inside_workspace`, `test_reject_symlink_or_partial_receipt`, `test_readback_identity_and_generation`, `test_atomic_preservation_on_interruption`, `test_guest_head_branch_tree_match` and `test_guest_rejects_tampered_bundle`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_git -v`; expect FAIL for missing behavior.
- [ ] Implement owner-only state root, no-follow descriptor checks, exclusive/atomic receipt writes with fsync, immutable SessionKey, explicit legal states (`REJECTED`, `RUNNING`, `PENDING`, `PRESERVATION_UNVERIFIED`) and reasons; preserve Guest original and separate identity evidence without Host repo mount.
- [ ] Implement Guest Bundle/manifest hash verify, isolated `git init` + import/checkout without Host remote/config/hooks/filters, and independent HEAD/branch/tree/worktree readback. Unknown state rejects the launch.
- [ ] Re-run tests; expect PASS. Commit Task 2 files after GO: `feat(oc2): persist Slice B identity and verified Guest baseline`.

## Task 3 — Trusted offline image builder and F-002 enforcement

**Files:** Create `sandbox/scripts/oc2_slice_b_image.py`, `sandbox/oc2_slice_b/Dockerfile`; Test `sandbox/tests/test_oc2_slice_b_image.py`.

**Interfaces:** `@dataclass(frozen=True) class ImagePin: source_revision: str; artifact_sha256: str; image_ref: str; config_id: str; archive_sha256: str`; `def verify_build_inputs(source_root: Path) -> None`; `def verify_image_archive(archive: Path, pin: ImagePin) -> None`; `def verify_loaded_image(inspect: dict, pin: ImagePin) -> None`. Implement trusted Docker interactions behind an injectable constrained runner; retain `WriterSpec.image_ref` digest-required validation.

- [ ] Write `test_reject_unpinned_base_or_artifact`, `test_reject_credential_bearing_build_context`, `test_reject_changed_archive`, `test_reject_unresolvable_digest`, `test_reject_image_config_or_entrypoint_mismatch` and `test_no_network_install_or_pull` using fake build/import/inspect results.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_image -v`; expect FAIL.
- [ ] Implement **one** trusted Host offline build/archive-manifest route with pinned official CLI v2.2.5 and vetted non-secret assets. The Dockerfile copies Task 4’s image-baked `entrypoint.py` as executable `/opt/oc2/slice-b/entrypoint` (Python shebang; no writable-repo script execution). In this Task, test the build/import policy with fakes; **the final image archive cannot be built or accepted until Task 4 has supplied the fixed entrypoint and fixture**. Guest verifies archive hash, imports with trusted Docker authority, checks local exact `repository@sha256:<manifest-digest>` resolution and config ID **before** Writer create. Do not add bare ID/tag fallback or soften security checks. If G0 failed, **STOP before this task**.
- [ ] Run test suite; expect PASS for offline fakes only. Mark actual image compatibility **NOT_VERIFIED** until Owner-approved live execution.
- [ ] Commit after GO: `feat(oc2): pin offline Writer image and verify imported digest`.

## Task 4 — Image-baked PID 1 and F-004 safe fixture

**Files:** Create `sandbox/oc2_slice_b/entrypoint.py`, `sandbox/oc2_slice_b/offline_fixture.py`; Test `sandbox/tests/test_oc2_slice_b_entrypoint.py`.

**Interfaces:** `def run_entrypoint(start_line: str, expected_generation: str, baseline_head: str, baseline_ref: str) -> int`; `def run_offline_fixture(repo: Path, baseline_head: str, baseline_ref: str) -> str` (returns Commit OID, raises `SliceBFixtureError`). Entrypoint script is the fixed image PID 1; baseline metadata is validated non-secret input, never from an unchecked repository command or credential. `WriterSpec.command` remains `("run",)`.

- [ ] Write `test_bad_or_late_start_line_skips_tui`, `test_tui_nonzero_skips_fixture`, `test_fixture_exact_bytes_and_author`, `test_uses_exact_add_N_then_commit_only_argv`, `test_other_staged_changes_survive`, `test_failure_preserves_ita_and_worktree`, `test_existing_fixture_rejected`, `test_head_divergence_skips_fixture`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_entrypoint -v`; expect FAIL.
- [ ] Implement the 30s bounded startup gate, TUI exit status check and deterministic fixture in the same image PID 1 control flow. Exact fixed argv: `git add -N -- oc2-slice-b-fixture.txt` then `git commit --only --no-verify --no-gpg-sign -m "test(oc2): verify offline writer fixture" -- oc2-slice-b-fixture.txt`. Disable hooks/filters/signing/identity inheritance; preserve unrelated Index/WT state and abort rather than repair on uncertainty.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): run offline fixture after TUI with pathspec-only commit`.

## Task 5 — Strict Writer stdin/TTY and exact-container attach

**Files:** Modify `sandbox/scripts/oc2_writer.py`, `sandbox/scripts/oc2_supervisor.py`; Test `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, create `sandbox/tests/test_oc2_slice_b_tty.py`.

**Interfaces:** Extend `WriterSpec` with **opt-in** `stdin_open: bool = False` while retaining `tty: bool = False`; `build_create_argv` adds `-i -t` only when both booleans are true under a fixed Slice B image command; `validate_writer_inspect` checks `Config.OpenStdin` alongside existing `Config.Tty`, image, labels and security flags. Add `def attach_writer(self, identity: WriterIdentity, transport: InteractiveTransport) -> AttachOutcome` to `GuestSupervisor`, where `InteractiveTransport` is a separate raw-byte, identity-bound interface; no generic Docker exec capability.

- [ ] Write `test_create_exact_it_only_for_slice_b`, `test_no_legacy_writer_behavior_change`, `test_attach_identity_mismatch`, `test_reject_short_id_and_unlisted_attach_shape`, `test_attach_transport_failure_stops_and_preserves`, `test_unverified_stop_never_reported_verified`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_writer sandbox.tests.test_oc2_supervisor sandbox.tests.test_oc2_slice_b_tty -v`; expect FAIL for new behavior.
- [ ] Add only exact `-i`+`-t` builder/parser/inspect checks; keep lifecycle allowlist and privileged socket denial. Implement separate `docker attach <full-cid>` raw PTY channel with pre/post ID, image, labels and StartedAt verification. Do **not** let transport return imply TUI/fixture success; inspect final container exit code. Support Ctrl-C, unexpected detach and terminal restoration without retry/restart.
- [ ] Re-run tests; expect PASS and no regression. Commit after GO: `feat(oc2): allow identity-bound interactive Writer attach`.

## Task 6 — Dispatcher and Slice B end-to-end orchestration

**Files:** Create `sandbox/scripts/oc2_slice_b.py`; Modify `sandbox/scripts/oc2.py`; Test `sandbox/tests/test_oc2_slice_b_adapter.py`, `sandbox/tests/test_oc2.py`.

**Interfaces:** `def run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int` with a protocol `SliceBOps` wrapping **only explicitly authorized** Sandbox/Git/Image/Writer operations, and injecting a fake in offline tests. Branch before credential provisioning and OAuth; maintain all existing non-Slice-B CLI behavior.

- [ ] Write `test_slice_b_dispatch_before_oauth`, `test_slice_b_rejects_credential_flags`, `test_slice_b_dry_run_no_side_effects`, `test_dirty_repo_rejected_before_sbx`, `test_baseline_changed_before_writer`, `test_unknown_exit_retains_pending`, `test_no_host_apply_or_collector_calls`, `test_legacy_launcher_unchanged`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2 -v`; expect FAIL.
- [ ] Implement the `--slice-b` opt-in branch before normal Credential Mixin/OAuth/`sbx exec -it` launch, preserving default behavior. Orchestrate Git baseline → image proof → Session receipt → Guest baseline → one Writer/TTY → bounded stop and readback. All error paths maintain the Session/original; no Collect/Apply.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): connect clean Git Slice B through isolated Writer`.

## Task 7 — Constrained acceptance readback and bounded verification

**Files:** Create `sandbox/scripts/oc2_slice_b_acceptance.py`; Test `sandbox/tests/test_oc2_slice_b_acceptance.py`, extend `sandbox/tests/test_oc2_slice_b_adapter.py`.

**Interfaces:** `@dataclass(frozen=True) class FixtureEvidence: session_key: WriterSessionKey; container_id: str; image_id: str; started_at: str; baseline_head: str; commit_oid: str; parent_oid: str; fixture_sha256: str`; `def verify_fixture_acceptance(evidence: FixtureEvidence, guest_reader: ReadOnlyGuestReader) -> str` returns `PASS | FAIL | NOT_VERIFIED`; reader is strictly constrained to non-executing Git-object/tree/Index/WT observations, **not** the Collector.

- [ ] Write `test_exact_one_parent_and_one_fixture_path`, `test_reject_unrelated_path_in_commit`, `test_reject_fixture_blob_hash_mismatch`, `test_reject_session_container_mismatch`, `test_unreadable_guest_is_not_verified`, `test_nonfixture_staging_preserved`, `test_pending_for_unknown_quiescence`, `test_preservation_unverified_is_incomplete`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_acceptance sandbox.tests.test_oc2_slice_b_adapter -v`; expect FAIL.
- [ ] Implement bounded read-only Guest OID/parent/tree/Blob and non-fixture Index/WT comparison, correlate full Writer ID and Session generation; never run repository-supplied hooks, external filter or privileged arbitrary exec. Record separate `AC-13a` credential absence, `AC-13b` effective external egress, `AC-13c` inference-request nonoccurrence verdicts; untested/incomplete proof is `NOT_RUN`/`NOT_VERIFIED`, **not PASS**.
- [ ] Re-run tests. Under a separately authorized implementation environment, assemble the final image/archive with the Task 4 entrypoint and fixture, and verify the build-manifest/hash/reference contract; **do not** execute a live Docker/Sandbox acceptance test absent its own Owner approval. Then run `python3 -m unittest sandbox.tests.test_oc2_slice_b_git sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_image sandbox.tests.test_oc2_slice_b_entrypoint sandbox.tests.test_oc2_slice_b_tty sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2_slice_b_acceptance sandbox.tests.test_oc2_writer sandbox.tests.test_oc2_supervisor sandbox.tests.test_oc2 -v`; expect PASS for the **offline** suites only.
- [ ] Commit after GO: `test(oc2): enforce Slice B acceptance and fail-closed boundaries`. Do not create PR or run live Sandbox/TTY without separate authorization.

## Acceptance mapping and evidence classes

| AC | Owning task | Offline evidence | Live evidence needed? |
| --- | --- | --- | --- |
| AC-01/02 | 1, 6 | Clean and rejection fixtures | Later, if Owner approves |
| AC-03 | 1, 2 | Bundle+Guest HEAD/Branch/Tree/OID | Guest readback |
| AC-04/05 | 3, 5 | Spec/inspect mocks | **Yes**; explicit Sandbox approval |
| AC-06 | 4, 5 | Protocol/attach mocks | **Yes**, real v2.2.5 TUI |
| AC-07/08 | 4, 7 | Fixed fixture, pathspec/staging checks | **Yes**, same Writer ID |
| AC-09 | 7 | Exact parent/tree/Blob/readback tests | **Yes**, Guest observation |
| AC-10/11 | 2, 6, 7 | Host non-write and receipt tests | Bounded Host/Guest readback |
| AC-12 | 2, 5, 6 | PENDING/unknown-state negatives | Limited live observation |
| AC-13a/b/c | 3, 6, 7 | Separate static evidence/negative tests | Separate credential, egress, request-absence proof; don't conflate |

**Observed failure** = `FAIL`, missing evidence = `NOT_VERIFIED`, not executed = `NOT_RUN`, known dependency blocker = `BLOCKED`. An expected protected `PENDING` is not itself a Slice B failure. **Guest original preservation unverified** prevents completion.

## Execution / Owner checkpoint

1. **Current checkpoint:** Design R0.1.3 is `DOCUMENT_READY_WITH_BLOCKERS` but formal adoption **PENDING**, Implementation Readiness **BLOCKED**. The plan is **DRAFT** and does not change those statuses. Task G0 is a candidate for a **separately approved, limited evidence check**, not an automatically launched task.
2. If G0 yields confirmed evidence, request Owner decision on **design adoption** and a distinct **Implementation GO**. No implementation branch, code, test command, Docker/Sandbox action or GitHub write without that decision.
3. If Implementation GO is later granted, use an isolated branch/worktree from then-current master. Follow TDD within each Task; avoid independent review per Task as an automatic loop. Commit only corresponding files and collect actual test outputs.
4. **Live** AC-04–13 requires **additional Sandbox/TTY approval**. If withheld, report `NOT_RUN` and do not label the Slice B completed.
5. On bounded test completion, report achieved behavior, exact test/identity evidence, outstanding `BLOCKED`/`NOT_VERIFIED`, Host nonmutation and preservation verdict. Return to Human Owner checkpoint. **No automatic PR, Merge, Follow-on Task, Collector or Host Apply**.

**Document stop condition:** Implementation plan candidate is written for Owner inspection; **no GitHub repository file is modified**, no execution/verification of the planned software is claimed. There is no active Implementation Plan in the reviewed branch; design-to-plan comparison was previously `NOT APPLICABLE`. This proposed plan is not a retroactive reconciliation claim.
