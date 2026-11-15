# OC2 Alternative A — Vertical Slice B Implementation Plan R0.1.1 (DRAFT / BLOCKED)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (native execution) or `superpowers:subagent-driven-development` only **after** Human Owner expressly authorizes implementation. Steps use checkboxes (`- [ ]`) for tracking. No implementation or review loop is authorized merely by this plan.

**Goal:** In a Mountless Sandbox, use one non-privileged Writer to launch OpenCode v2.2.5 TUI and then run a deterministic offline edit/test/fixture Git Commit based on the Host's exact Clean Local Branch HEAD, preserving Guest evidence and leaving Host Git untouched.

**Architecture:** Extend `oc2.py` with an explicit `--slice-b` dispatch to a small Host/Guest adapter. A strictly screened Git Bundle seeds an independent Session-private Guest repository. A digest-pinned, trusted Host-prebuilt Writer image runs one fixed PID 1 entrypoint; the Trusted Guest Supervisor attaches to the same container ID, observes exit, and retains the Guest original with a conservative `PENDING` disposition.

**Tech Stack:** Python 3 and `unittest` (matching existing tests), Git CLI in a sanitized/locked-down configuration, Docker CLI/OCI image archive, Docker Sandboxes `sbx`, pinned OpenCode v2.2.5.

**Spec:** `docs/superpowers/specs/2026-11-16-oc2-alternative-a-vertical-slice-b-design.md` **R0.1.4**, VB-F-005/006/007 documentary alignment on the same feature branch, branch `feature/oc2-alta-vertical-slice-b-design-20261116`. Parent design: `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md` R0.2.

**Plan status:** `PLAN_CANDIDATE / DESIGN_FORMAL_ADOPTION_PENDING / IMPLEMENTATION_BLOCKED`. **Revision R0.1.1:** VB-F-005/006/007 limited plan consistency correction; F-001–F-004 preserved. F-004 is document-resolved; AC-08/09 live validation is `NOT_RUN`. **F-002 remains `UNRESOLVED`** until digest-qualified image resolution after Docker import is evidenced. There is **no Implementation GO** and no authorization for Docker/Sandbox/TTY, source modifications, PR, merge, Collect or Host Apply. This plan is not a finding closure or permission to start work.

## Global Constraints

- Scope: Clean **Local Branch** with existing HEAD only. Reject Dirty/intent-to-add, detached, submodule, linked-worktree, shallow/partial/alternates, sparse/split-index, LFS/filter-dependent and uninspectable histories before side effects. Host-side intent-to-add remains prohibited.
- Host Baseline (VB-F-006): exact HEAD Commit OID, full branch ref, Tree OID, Index digest and Working Tree manifest; selective fully inspected Git Bundle and canonical `SliceBBundleManifestV1` SHA-256 bound to immutable `WriterSessionKey`, `transfer_policy_id`, verified non-secret `runtime_sha256` and `SliceBReceipt`. Host/Guest private, separate readback; never from mutable Guest `.git` as authority. No `.git` copy or Host RW mount.
- Writer: **UID/GID 10001**, `--network none`, `--cap-drop ALL`, `no-new-privileges`, read-only rootfs, bounded resources, `--restart no`, Session-only Guest Repo RW + validated tmpfs, no privileged socket or credential.
- Image: trusted Host offline prebuild, verified archive, trusted Guest `docker load`, exact *locally resolvable* `repository@sha256:<manifest-digest>` matching `WriterSpec.image_ref` and image ID. Failure = **BLOCKED**; tag, bare image ID, pull or privileged fallback forbidden.
- Runtime: **OpenCode v2.2.5** and non-secret pinned Phase 5 assets only; no OAuth/Mixin/Proxy, Provider request, external inference or network installation.
- Writer execution: fixed image `Config.Entrypoint=["/opt/oc2/slice-b/entrypoint"]`, `WriterSpec.command=("run",)`, one PID 1; exact full 64-hex container ID. Dedicated bounded `docker attach` transport with stdin+TTY, no `docker exec`.
- Protocol (VB-F-005): once-only Supervisor-issued `OC2_SLICE_B_START <session-generation> <head-oid> <branch-ref> <manifest-sha256>` line, exactly five ASCII tokens, LF, ≤512 bytes, **30-second deadline**; authority is the Host-issued manifest/Receipt validated by trusted Guest Supervisor **outside** the Writer mount, not mutable `.git`. Existing `WriterSpec.command=("run",)` and env allowlist remain unchanged. TUI exit `0` is required before fixture. Never reinterpret TUI render as AI inference success.
- Fixture: `/workspace/oc2-slice-b-fixture.txt`, exact UTF-8 bytes `OC2 Slice B offline fixture PASS\n`, fixed Python assertion, then **Guest Writer only** `git add -N -- oc2-slice-b-fixture.txt` followed by `git commit --only --no-verify --no-gpg-sign -m "test(oc2): verify offline writer fixture" -- oc2-slice-b-fixture.txt`; fixed Author/Committer `OC2 Slice B Fixture <oc2-slice-b-fixture@example.invalid>`, deterministic date/locale, no signing/hooks/filter. No change to non-fixture staged/unstaged state.
- Commit evidence: **exactly one Parent OID == Host Baseline HEAD**, exactly one changed path, expected regular Blob bytes/SHA-256, same SessionKey + Container ID + image ID + StartedAt. Writer self-reports alone are not proof.
- Stopping: never manufacture `STOPPED_VERIFIED`; quiescence unknown => `PENDING / GUEST_QUIESCENCE_UNVERIFIED`. Preserve Guest repository and private Session receipt. If preservation cannot be evidenced => `PRESERVATION_UNVERIFIED` (not complete). No Collector, Collection Digest, ApplyAuthorization or Host Apply.
- No automatically spawned separate reviewer, correction task, PR, merge or next phase. After one bounded execution/verification cycle, return to Human Owner checkpoint; don't extend work solely to eliminate findings.

## File Structure / Owned Interfaces

| File | Responsibility |
| --- | --- |
| Modify `sandbox/scripts/oc2.py` | Early `--slice-b` dispatcher; legacy path unchanged |
| Create `sandbox/scripts/oc2_slice_b.py` | Host/Guest flow orchestration and dependency-injected effects |
| Create `sandbox/scripts/oc2_slice_b_git.py` | Host Clean validation, historical object/secret checks, selective Bundle plus canonical Manifest/sha256 and Guest baseline verification |
| Create `sandbox/scripts/oc2_slice_b_session.py` | Private Host/Guest Session receipt, immutable Bundle/Manifest/Runtime identity, verified baseline authority and typed startup message |
| Create `sandbox/scripts/oc2_slice_b_image.py` | Trusted Host image/archive manifest and Guest image identity verification; no fallback |
| Create `sandbox/oc2_slice_b/Dockerfile` | Offline-only fixed image build inputs and digest-pinned base |
| Create `sandbox/oc2_slice_b/entrypoint.py` | Fixed PID 1 startup barrier → TUI → fixture control flow |
| Create `sandbox/oc2_slice_b/offline_fixture.py` | Fixed fixture edit/test/intent-to-add/pathspec Commit inside Writer |
| Modify `sandbox/scripts/oc2_writer.py` | Minimal stdin/TTY validation and exact baked-in image command contract |
| Modify `sandbox/scripts/oc2_supervisor.py` | Identity-bound narrow attach capability; existing Docker lifecycle allowlist unchanged |
| Create `sandbox/scripts/oc2_slice_b_acceptance.py` | Constrained read-only Guest Git object/Session evidence checker; **not Collector** |
| Create `sandbox/tests/test_oc2_slice_b_{git,session,image,entrypoint,tty,acceptance,adapter}.py` | Isolated `unittest` TDD checks |
| Modify `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, `sandbox/tests/test_oc2.py` | Existing-contract regression/negative tests only |

Interfaces introduced by the **plan** below are proposed implementation names, **not claims about current code**. The Design R0.1.4 §4.2.1/§5.2/§7 typed contracts are normative for these planned interfaces; do not invent alternate transport, metadata or lifecycle layers. Use the existing `oc2_writer.WriterSessionKey`, `WriterSpec`, `WriterIdentity`, and `GuestSupervisor` types; never replace their identity/security model.

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

## Task 1 — Host Git admission and selective Bundle + Manifest (VB-F-006)

**Files:** Create `sandbox/scripts/oc2_slice_b_git.py`; Test `sandbox/tests/test_oc2_slice_b_git.py`.

**Interfaces (VB-F-006):** `@dataclass(frozen=True) class GitBaseline: root: Path; branch_ref: str; head_oid: str; tree_oid: str; object_format: str; index_sha256: str; worktree_sha256: str`; `def admit_clean_repo(root: Path) -> GitBaseline`. Add `@dataclass(frozen=True) class SliceBBundleManifestV1: schema: Literal["dotfiles-ai/oc2-slice-b-bundle/v1"]; key: WriterSessionKey; baseline: GitBaseline; bundle_sha256: str; bundle_size_bytes: int; transfer_policy_id: Literal["oc2-slice-b-clean-git-bundle-v1"]; runtime_sha256: str`. Add `@dataclass(frozen=True) class BundleArtifact: bundle_path: Path; bundle_sha256: str; manifest_path: Path; manifest_sha256: str; baseline: GitBaseline; key: WriterSessionKey; transfer_policy_id: str; runtime_sha256: str`. `def build_verified_bundle(baseline: GitBaseline, output: Path, *, key: WriterSessionKey, runtime_sha256: str) -> BundleArtifact`; `def verify_bundle_manifest(artifact: BundleArtifact, *, expected_key: WriterSessionKey, expected_manifest_sha256: str, expected_runtime_sha256: str) -> SliceBBundleManifestV1`; `def recheck_host_baseline(baseline: GitBaseline) -> None`. Manifest schema, OID-length-vs-object-format, strict validated branch ref, 64-hex digests, size bound, fixed transfer policy, canonical JSON (sorted compact UTF-8 + LF, no duplicate/unknown keys), and key validation are mandatory. `root: Path` is encoded as its canonical absolute string. `runtime_sha256` comes from trusted verified non-secret Runtime/image-build inputs, **not** the repo. Raise `SliceBGitRejected` on ambiguity; no Host Git writes.

- [ ] Write `test_accept_clean_branch`, `test_reject_dirty_staged_unstaged_untracked`, `test_reject_ita_and_unknown_index`, `test_reject_detached_submodule_sparse_partial_alternates`, `test_reject_secret_in_ancestor`, `test_bundle_only_pinned_head`, `test_manifest_canonical_bytes_and_digest`, `test_reject_bundle_manifest_key_runtime_policy_mismatch`, `test_reject_tampered_or_missing_manifest` and `test_detect_host_change_without_index_mutation` using disposable Git repos and injected safe command runner.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_git -v`; expect **FAIL** for absent interface.
- [ ] Implement the strict Index v2/v3 flag/checksum reader or reuse a demonstrably equivalent existing reader; use sanitized noninteractive Git CLI with disabled optional locks/hooks/filter/remote behavior, explicit argv and bounded object scan. Pin HEAD/branch/tree and transfer only selected ref history; reject unbounded or uninspectable data. Produce the **canonical Manifest only after Bundle verification**, include exact Bundle SHA/size and Host-supplied trusted Runtime SHA, hash its exact bytes, and return both paths/digests as one `BundleArtifact`; reject key/policy/manifest mismatch.
- [ ] Run the same suite; expect PASS, with any policy-unknown input rejected rather than skipped.
- [ ] Commit only Task 1 files **after Implementation GO**: `test(oc2): admit clean Git baseline and verify bundle`.

## Task 2 — Session receipt and independent Guest baseline

**Files:** Create `sandbox/scripts/oc2_slice_b_session.py`; Test `sandbox/tests/test_oc2_slice_b_session.py`; implement import/readback in `sandbox/scripts/oc2_slice_b_git.py` and its tests.

**Interfaces (VB-F-005/006):** `@dataclass(frozen=True) class SliceBReceipt: key: WriterSessionKey; baseline: GitBaseline; bundle_sha256: str; manifest_sha256: str; transfer_policy_id: str; runtime_sha256: str; image_ref: str; image_config_id: str; state: str; reason: str | None; writer_id: str | None; started_at: str | None`. Identity fields (through `image_config_id`) are immutable after creation; `writer_id`/`started_at` bind **once** only to the inspected full-ID Writer. `@dataclass(frozen=True) class VerifiedGuestAuthority: key: WriterSessionKey; manifest: SliceBBundleManifestV1; manifest_sha256: str; image_ref: str; image_config_id: str` is created **only by trusted Guest Supervisor after** comparing the Guest's private control-copy of canonical Manifest bytes with the Host-issued Receipt and expected hash/key, imported Bundle SHA and Runtime/Image identity; it is never derived from writable Guest Git. `@dataclass(frozen=True) class SliceBStartMessage: session_generation: str; head_oid: str; branch_ref: str; manifest_sha256: str`. `def create_session_receipt(state_root: Path, receipt: SliceBReceipt, artifact: BundleArtifact) -> Path`; `def update_session_receipt(path: Path, receipt: SliceBReceipt) -> None`; `def verify_session_receipt(path: Path, expected_key: WriterSessionKey) -> SliceBReceipt`; `def import_guest_baseline(bundle: BundleArtifact, repo: Path, *, expected_manifest_sha256: str, expected_key: WriterSessionKey, expected_runtime_sha256: str) -> GitBaseline`; `def verify_guest_authority(guest_control_manifest: Path, receipt: SliceBReceipt, guest_baseline: GitBaseline, image_config_id: str) -> VerifiedGuestAuthority`; `def build_start_message(authority: VerifiedGuestAuthority) -> SliceBStartMessage`. The existing `oc2_session.py` v2 receipt remains separate; do not silently convert it into a completed lifecycle/Collector.

- [ ] Write `test_refuse_receipt_inside_workspace`, `test_reject_symlink_or_partial_receipt`, `test_readback_identity_and_generation`, `test_atomic_preservation_on_interruption`, `test_guest_head_branch_tree_match`, `test_guest_rejects_tampered_bundle`, `test_reject_missing_or_wrong_manifest_digest`, `test_reject_runtime_or_policy_mismatch`, `test_reject_guest_manifest_as_untrusted_authority`, `test_reject_receipt_identity_rebinding` and `test_reject_wrong_generation_start_message`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_git -v`; expect FAIL for missing behavior.
- [ ] Implement owner-only state root, no-follow descriptor checks, exclusive/atomic receipt writes with fsync, immutable SessionKey **plus immutable baseline/Bundle SHA/Manifest SHA/transfer policy/Runtime SHA/image reference/image config ID**, explicit legal states (`REJECTED`, `RUNNING`, `PENDING`, `PRESERVATION_UNVERIFIED`) and reasons; preserve Guest original and separate identity evidence without Host repo mount.
- [ ] Implement Guest Bundle/manifest hash verify, isolated `git init` + import/checkout without Host remote/config/hooks/filters, and independent HEAD/branch/tree/worktree readback. Host stores canonical Manifest and Receipt separately in the private state root; Guest Supervisor stores a hash/key-verified Manifest outside the Writer mount. Build `VerifiedGuestAuthority` from the Host-authoritative expected hash and Receipt only after Bundle, policy, Runtime, imported Git baseline and image checks agree; only it can produce `SliceBStartMessage`. Any mismatch/unknown state rejects launch, and no mutable Guest repository field is a baseline authority.
- [ ] Re-run tests; expect PASS. Commit Task 2 files after GO: `feat(oc2): persist Slice B identity and verified Guest baseline`.

## Task 3 — Trusted offline image builder and F-002 enforcement

**Files:** Create `sandbox/scripts/oc2_slice_b_image.py`, `sandbox/oc2_slice_b/Dockerfile`; Test `sandbox/tests/test_oc2_slice_b_image.py`.

**Interfaces:** `@dataclass(frozen=True) class ImagePin: source_revision: str; artifact_sha256: str; runtime_sha256: str; image_ref: str; config_id: str; archive_sha256: str`; `def verify_build_inputs(source_root: Path) -> None`; `def verify_image_archive(archive: Path, pin: ImagePin) -> None`; `def verify_loaded_image(inspect: dict, pin: ImagePin) -> None`. Implement trusted Docker interactions behind an injectable constrained runner; retain `WriterSpec.image_ref` digest-required validation.

- [ ] Write `test_reject_unpinned_base_or_artifact`, `test_reject_credential_bearing_build_context`, `test_reject_changed_archive`, `test_reject_unresolvable_digest`, `test_reject_image_config_or_entrypoint_mismatch`, `test_reject_runtime_sha256_vs_bundle_manifest` and `test_no_network_install_or_pull` using fake build/import/inspect results.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_image -v`; expect FAIL.
- [ ] Implement **one** trusted Host offline build/archive-manifest route with pinned official CLI v2.2.5 and vetted non-secret assets. The Dockerfile copies Task 4’s image-baked `entrypoint.py` as executable `/opt/oc2/slice-b/entrypoint` (Python shebang; no writable-repo script execution). In this Task, test the build/import policy with fakes; **the final image archive cannot be built or accepted until Task 4 has supplied the fixed entrypoint and fixture**. Guest verifies archive hash, imports with trusted Docker authority, checks local exact `repository@sha256:<manifest-digest>` resolution and config ID **before** Writer create. Do not add bare ID/tag fallback or soften security checks. If G0 failed, **STOP before this task**.
- [ ] Run test suite; expect PASS for offline fakes only. Mark actual image compatibility **NOT_VERIFIED** until Owner-approved live execution.
- [ ] Commit after GO: `feat(oc2): pin offline Writer image and verify imported digest`.

## Task 4 — Image-baked PID 1 and F-004 safe fixture

**Files:** Create `sandbox/oc2_slice_b/entrypoint.py`, `sandbox/oc2_slice_b/offline_fixture.py`; Test `sandbox/tests/test_oc2_slice_b_entrypoint.py`.

**Interfaces (VB-F-005):** consume `SliceBStartMessage` defined in Task 2. `def parse_start_line(line: str) -> SliceBStartMessage` accepts **only** ASCII `OC2_SLICE_B_START <session-generation> <head-oid> <branch-ref> <manifest-sha256>\n`, exact five tokens, ≤512 bytes, LF, fixed validated canonical UUID4/40- or 64-hex OID/full approved branch ref/64-hex manifest SHA. `def run_entrypoint(start_line: str) -> int` verifies **actual Guest** HEAD/ref against the **expected values from the Trusted Supervisor line** before TUI, never discovers its own trusted expected baseline from writable `.git`. `def run_offline_fixture(repo: Path, baseline_head: str, baseline_ref: str) -> str` (Commit OID or `SliceBFixtureError`) consumes the parsed trusted values. Entrypoint is the fixed image PID 1, no env metadata key or dynamic argv; `WriterSpec.command=("run",)` stays fixed.

- [ ] Write `test_bad_or_late_start_line_skips_tui`, `test_tui_nonzero_skips_fixture`, `test_fixture_exact_bytes_and_author`, `test_uses_exact_add_N_then_commit_only_argv`, `test_other_staged_changes_survive`, `test_failure_preserves_ita_and_worktree`, `test_existing_fixture_rejected`, `test_head_divergence_skips_fixture`, `test_missing_or_late_baseline_line_skips_tui`, `test_tampered_head_ref_or_manifest_line_skips_tui`, `test_expected_baseline_not_taken_from_guest_git`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_entrypoint -v`; expect FAIL.
- [ ] Implement the 30s bounded **five-token Supervisor Baseline startup gate**, strict type/ref validation, actual HEAD/ref match before TUI, TUI exit status check and deterministic fixture in the same image PID 1 control flow. Missing/invalid/altered expected values cannot be supplied from a repo file or unlisted env variable. Exact fixed argv: `git add -N -- oc2-slice-b-fixture.txt` then `git commit --only --no-verify --no-gpg-sign -m "test(oc2): verify offline writer fixture" -- oc2-slice-b-fixture.txt`. Disable hooks/filters/signing/identity inheritance; preserve unrelated Index/WT state and abort rather than repair on uncertainty.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): run offline fixture after TUI with pathspec-only commit`.

## Task 5 — Strict Writer stdin/TTY and exact-container attach

**Files:** Modify `sandbox/scripts/oc2_writer.py`, `sandbox/scripts/oc2_supervisor.py`; Test `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, create `sandbox/tests/test_oc2_slice_b_tty.py`.

**Interfaces:** Extend `WriterSpec` with **opt-in** `stdin_open: bool = False` while retaining `tty: bool = False`; `build_create_argv` adds `-i -t` only when both booleans are true under a fixed Slice B image command; `validate_writer_inspect` checks `Config.OpenStdin` alongside existing `Config.Tty`, image, labels and security flags. Add `def attach_writer(self, identity: WriterIdentity, transport: InteractiveTransport, authority: VerifiedGuestAuthority) -> AttachOutcome` to `GuestSupervisor`; the trusted Supervisor derives and sends exactly one `SliceBStartMessage` from the immutable `VerifiedGuestAuthority` (Task 2) **after** exact-ID/StartedAt/label and manifest/Receipt checks, before forwarding any TTY input. `InteractiveTransport` remains a separate raw-byte, identity-bound interface, with no generic Docker exec capability.

- [ ] Write `test_create_exact_it_only_for_slice_b`, `test_no_legacy_writer_behavior_change`, `test_attach_identity_mismatch`, `test_reject_short_id_and_unlisted_attach_shape`, `test_attach_transport_failure_stops_and_preserves`, `test_unverified_stop_never_reported_verified`, `test_attach_rejects_missing_or_tampered_authority`, `test_start_line_emitted_once_after_identity_verification`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_writer sandbox.tests.test_oc2_supervisor sandbox.tests.test_oc2_slice_b_tty -v`; expect FAIL for new behavior.
- [ ] Add only exact `-i`+`-t` builder/parser/inspect checks; keep lifecycle allowlist and privileged socket denial. Implement separate `docker attach <full-cid>` raw PTY channel with pre/post ID, image, labels and StartedAt verification. Do **not** let transport return imply TUI/fixture success; inspect final container exit code. Support Ctrl-C, unexpected detach and terminal restoration without retry/restart. Do not allow the attached client, repository or terminal input to substitute for the Supervisor-issued trusted Baseline start message.
- [ ] Re-run tests; expect PASS and no regression. Commit after GO: `feat(oc2): allow identity-bound interactive Writer attach`.

## Task 6 — Dispatcher and Slice B end-to-end orchestration

**Files:** Create `sandbox/scripts/oc2_slice_b.py`; Modify `sandbox/scripts/oc2.py`; Test `sandbox/tests/test_oc2_slice_b_adapter.py`, `sandbox/tests/test_oc2.py`.

**Interfaces:** `def run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int` with a protocol `SliceBOps` wrapping **only explicitly authorized** Sandbox/Git/Image/Writer operations, and injecting a fake in offline tests. Branch before credential provisioning and OAuth; maintain all existing non-Slice-B CLI behavior.

- [ ] Write `test_slice_b_dispatch_before_oauth`, `test_slice_b_rejects_credential_flags`, `test_slice_b_dry_run_no_side_effects`, `test_dirty_repo_rejected_before_sbx`, `test_baseline_changed_before_writer`, `test_unknown_exit_retains_pending`, `test_no_host_apply_or_collector_calls`, `test_legacy_launcher_unchanged`, `test_reject_host_guest_manifest_key_digest_drift`, `test_reject_untrusted_guest_baseline_source`, `test_reject_missing_runtime_identity`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2 -v`; expect FAIL.
- [ ] Implement the `--slice-b` opt-in branch before normal Credential Mixin/OAuth/`sbx exec -it` launch, preserving default behavior. Orchestrate verified Host Git baseline + Bundle/Manifest → selected Runtime/image pin → immutable Host Receipt → trusted Guest private Manifest readback → `VerifiedGuestAuthority` → one exact Writer-ID `SliceBStartMessage`/TTY → bounded stop and evidence readback. The Host pins expected `manifest_sha256` and `WriterSessionKey` over trusted orchestration; Guest `.git` may be checked as observed state, never used to issue expected Baseline values. All error paths maintain the Session/original; no Collect/Apply.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): connect clean Git Slice B through isolated Writer`.

## Task 7 — Constrained acceptance readback and bounded verification

**Files:** Create `sandbox/scripts/oc2_slice_b_acceptance.py`; Test `sandbox/tests/test_oc2_slice_b_acceptance.py`, extend `sandbox/tests/test_oc2_slice_b_adapter.py`.

**Interfaces (VB-F-006):** `@dataclass(frozen=True) class FixtureEvidence: session_key: WriterSessionKey; container_id: str; image_id: str; started_at: str; baseline_head: str; manifest_sha256: str; bundle_sha256: str; runtime_sha256: str; transfer_policy_id: str; commit_oid: str; parent_oid: str; fixture_sha256: str`; `def verify_fixture_acceptance(evidence: FixtureEvidence, guest_reader: ReadOnlyGuestReader, trusted_receipt: SliceBReceipt, authority: VerifiedGuestAuthority) -> str` returns `PASS | FAIL | NOT_VERIFIED`; compare Manifest/Runtime/Session/Bundle/Image identity independently from Guest Git OIDs and stage/Working Tree. Reader is strictly constrained to non-executing Git-object/tree/Index/WT observations, **not** the Collector.

- [ ] Write `test_exact_one_parent_and_one_fixture_path`, `test_reject_unrelated_path_in_commit`, `test_reject_fixture_blob_hash_mismatch`, `test_reject_session_container_mismatch`, `test_unreadable_guest_is_not_verified`, `test_nonfixture_staging_preserved`, `test_pending_for_unknown_quiescence`, `test_preservation_unverified_is_incomplete`, `test_receipt_manifest_bundle_runtime_round_trip`, `test_detect_tampered_guest_manifest_and_runtime`, `test_missing_independent_identity_readback_not_verified`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_acceptance sandbox.tests.test_oc2_slice_b_adapter -v`; expect FAIL.
- [ ] Implement bounded read-only Guest OID/parent/tree/Blob and non-fixture Index/WT comparison, correlate full Writer ID and Session generation with the Host Receipt and separately verified Guest control Manifest/Bundle SHA/Runtime SHA/transfer policy; missing or mismatched identity is **FAIL/NOT_VERIFIED**, never an inferred PASS. Never run repository-supplied hooks, external filter or privileged arbitrary exec. Record separate `AC-13a` credential absence, `AC-13b` effective external egress, `AC-13c` inference-request nonoccurrence verdicts; untested/incomplete proof is `NOT_RUN`/`NOT_VERIFIED`, **not PASS**.
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

## Execution / Owner checkpoint — VB-F-007

1. **Current checkpoint:** Design R0.1.4 is a document-aligned **candidate with F-002 HOLD** but formal adoption **PENDING**, Implementation Readiness **BLOCKED**. The plan is **DRAFT** and does not change those statuses. Task G0 is a candidate for a **separately approved, limited evidence check**, not an automatically launched task.
2. If G0 yields confirmed evidence, request Owner decision on **design adoption** and a distinct **Implementation GO**. No implementation branch, code, test command, Docker/Sandbox action or GitHub write without that decision.
3. If Implementation GO is later granted, use an isolated branch/worktree from then-current master. Follow TDD within each Task; avoid independent review per Task as an automatic loop. Commit only corresponding files and collect actual test outputs.
4. **Live** AC-04–13 requires **additional Sandbox/TTY approval**. If withheld, report `NOT_RUN` and do not label the Slice B completed.
5. On bounded test completion, report achieved behavior, exact test/identity evidence, outstanding `BLOCKED`/`NOT_VERIFIED`, Host nonmutation and preservation verdict. Return to Human Owner checkpoint. **No automatic PR, Merge, Follow-on Task, Collector or Host Apply**.

**Document stop condition (VB-F-007):** Both existing documents are present in this feature branch: **Design R0.1.4 (formal adoption PENDING)** and **Implementation Plan R0.1.1 (DRAFT / BLOCKED)**. The former `NOT APPLICABLE` comparison applied only before the Plan was added. **For VB-F-005/006/007**, typed contracts, consuming/producing interfaces, error/negative tests, evidence, nonfunctional isolation and STOP semantics were compared to the Design and aligned **as documents**, not validated by executing software. Commit/Push/Readback only these two Markdown documents, then stop at the Human Owner checkpoint. G0, Implementation GO, Docker/Sandbox/TTY, Credential/Inference/Relay/Collector/Host Apply, PR/Merge and any follow-on task remain unapproved/HOLD; no further review loop.
