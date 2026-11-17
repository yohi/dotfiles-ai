# OC2 Alternative A — Vertical Slice B Implementation Plan R0.1.2 (F-002 MODE A ALIGNMENT)

> **For agentic workers:** Human Owner decision `F002_ARCHIVE_CONFIG_IDENTITY_IMPLEMENTATION_GO` authorizes only the limited mode A source changes and offline verification described in the current task. Do not begin Task 6/7, perform live Docker/Sandbox/Writer actions, or Commit/Push/PR.

**Goal:** In a Mountless Sandbox, use one non-privileged Writer to launch OpenCode v2.2.5 TUI and then run a deterministic offline edit/test/fixture Git Commit based on the Host's exact Clean Local Branch HEAD, preserving Guest evidence and leaving Host Git untouched.

**Architecture:** Extend `oc2.py` with an explicit `--slice-b` dispatch to a small Host/Guest adapter. A strictly screened Git Bundle seeds an independent Session-private Guest repository. A digest-pinned, trusted Host-prebuilt Writer image runs one fixed PID 1 entrypoint; the Trusted Guest Supervisor attaches to the same container ID, observes exit, and retains the Guest original with a conservative `PENDING` disposition.

**Tech Stack:** Python 3 and `unittest` (matching existing tests), Git CLI in a sanitized/locked-down configuration, Docker CLI/OCI image archive, Docker Sandboxes `sbx`, pinned OpenCode v2.2.5.

**Spec:** `docs/superpowers/specs/2026-11-16-oc2-alternative-a-vertical-slice-b-design.md` **R0.1.5**. Parent design: `docs/superpowers/specs/2026-11-13-oc2-daily-launcher-design.md` R0.2.

**Plan status:** `F002_MODE_A_IMPLEMENTATION_APPROVED / OFFLINE_IMPLEMENTATION_IN_PROGRESS / LIVE_ACCEPTANCE_NOT_RUN`. **Revision R0.1.2:** align only the existing F-002 and dependent receipt/Writer contracts with the Owner-approved Archive/Config ID identity mode. The independent Docker probe found that `RepoDigests` may be lost after Load; F-002 remains **UNRESOLVED** until separately approved live verification of the implemented path. No Docker/Sandbox/TTY operation, Commit/Push/PR, Task 6/7, Collect or Host Apply is authorized by this plan revision.

## Global Constraints

- Scope: Clean **Local Branch** with existing HEAD only. Reject Dirty/intent-to-add, detached, submodule, linked-worktree, shallow/partial/alternates, sparse/split-index, LFS/filter-dependent and uninspectable histories before side effects. Host-side intent-to-add remains prohibited.
- Host Baseline (VB-F-006): exact HEAD Commit OID, full branch ref, Tree OID, Index digest and Working Tree manifest; selective fully inspected Git Bundle and canonical `SliceBBundleManifestV1` SHA-256 bound to immutable `WriterSessionKey`, `transfer_policy_id`, verified non-secret `runtime_sha256` and `SliceBReceipt`. Host/Guest private, separate readback; never from mutable Guest `.git` as authority. No `.git` copy or Host RW mount.
- Writer: **UID/GID 10001**, `--network none`, `--cap-drop ALL`, `no-new-privileges`, read-only rootfs, bounded resources, `--restart no`, Session-only Guest Repo RW + validated tmpfs, no privileged socket or credential.
- Image mode A: Host pins Source Revision, Artifact digest, Runtime digest, base digest, Dockerfile/build-context hashes, Config ID, Archive SHA-256/size and platform in an immutable Image Record/Receipt. Guest verifies the private Archive and Record, loads it through an explicit Guest socket, and inspects the exact Config ID. `RepoDigests` is provenance only and may be empty. Config-ID Create is permitted only with a sealed Receipt/Session-bound Guest authority; unverified bare IDs, tags, Pull and privileged fallback remain forbidden.
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
| `sandbox/scripts/oc2_slice_b_image.py` plus `oc2_slice_b_image_{record,verify,build,host,guest,io}.py` | Canonical Host Image Record, offline Build/Save by Config ID, safe Guest Archive Load, exact Config ID inspection and sealed image capability |
| Create `sandbox/oc2_slice_b/Dockerfile` | Offline-only fixed image build inputs and digest-pinned base |
| Create `sandbox/oc2_slice_b/entrypoint.py` | Fixed PID 1 startup barrier → TUI → fixture control flow |
| Create `sandbox/oc2_slice_b/offline_fixture.py` | Fixed fixture edit/test/intent-to-add/pathspec Commit inside Writer |
| Modify `sandbox/scripts/oc2_writer.py` | Minimal stdin/TTY validation and exact baked-in image command contract |
| Modify `sandbox/scripts/oc2_supervisor.py` | Identity-bound narrow attach capability; existing Docker lifecycle allowlist unchanged |
| Create `sandbox/scripts/oc2_slice_b_acceptance.py` | Constrained read-only Guest Git object/Session evidence checker; **not Collector** |
| Create `sandbox/tests/test_oc2_slice_b_{git,session,image,entrypoint,tty,acceptance,adapter}.py`, `test_oc2_slice_b_image_io.py`, `oc2_slice_b_test_support.py` | Isolated `unittest` TDD checks and Fake Runner fixtures |
| Modify `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, `sandbox/tests/test_oc2.py` | Existing-contract regression/negative tests only |

Interfaces introduced by the **plan** below are proposed implementation names, **not claims about current code**. The Design R0.1.4 §4.2.1/§5.2/§7 typed contracts are normative for these planned interfaces; do not invent alternate transport, metadata or lifecycle layers. Use the existing `oc2_writer.WriterSessionKey`, `WriterSpec`, `WriterIdentity`, and `GuestSupervisor` types; never replace their identity/security model.

## Review Focus — five inputs with owning tests

1. **Clean-looking index with `CE_INTENT_TO_ADD` or unknown extension:** reject before Sandbox access (`Task 1: test_reject_ita_and_unknown_index`).
2. **Historical secret blob despite a Clean current tree:** abort Bundle transfer (`Task 1: test_reject_secret_in_ancestor`).
3. **Loaded image has matching Archive hash and Config ID but no RepoDigest:** proceed only through the Host Record + sealed Guest authority mode A path (`Task 2/3/5`); never treat Config ID alone as trusted.
4. **TUI stages an unrelated file:** fixed fixture commit excludes it and preserves Index/Working Tree (`Task 4: test_other_staged_changes_survive`).
5. **Attach to changed/short/foreign container ID or lost process exit evidence:** reject/no fixture, retain PENDING (`Task 5: test_attach_identity_mismatch`, `Task 7: test_unknown_exit_retains_pending`).

---

## Gate G0 — F-002 Digest Resolution evidence and mode A authorization

**Completed before this implementation task. Do not repeat the live probe.** The isolated Docker 29.6.2 → 29.1.3 probe saved and loaded an existing `linux/amd64` image; Archive SHA-256 and Config ID matched, but the Destination `RepoDigests` was empty and the exact repository digest lookup failed. Human Owner decision `F002_ARCHIVE_CONFIG_IDENTITY_IMPLEMENTATION_GO` adopts the Host-pinned Archive/Config ID identity mode for this limited implementation.

- Preserve the observed FAIL as evidence; do not tag, Pull, Build or retry the same Save/Load probe.
- Implement only the Host Image Record/Receipt, Guest Archive Load and Config-ID verification, authority binding and Writer pre-create gate in Tasks 2/3/5.
- Do not start Tasks 6/7, live Docker/Sandbox/TTY/Writer operations, Commit/Push/PR or Host Apply.

**Evidence limit:** the live probe proves only that this tested image's Config ID survived Load while `RepoDigests` did not. It does **not** prove the actual Writer image build/import path or Writer execution. Live Docker and AC-04–13 remain `NOT_RUN`.

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

**Interfaces (VB-F-005/006, F-002 mode A):** `SliceBReceipt` pins `key`, `baseline`, Bundle/Manifest/transfer-policy/Runtime identities and a canonical `ImagePin` plus its `image_record_sha256`; all are immutable after creation. `verify_session_receipt(path, expected_key, expected_receipt_sha256)` returns a sealed `VerifiedSliceBReceipt` only after exact Host Receipt hash/key/Manifest readback. `import_guest_image(GuestImageLoadRequest, GuestImageRunner)` accepts the Host Receipt's Image Record, verifies the Supervisor-only Archive and hash, loads into an empty Store through an explicit socket, rechecks the Archive, then inspects the exact Config ID and returns a sealed `VerifiedImageAuthority`. `verify_guest_authority(VerifiedSliceBReceipt, GitBaseline, VerifiedImageAuthority)` produces sealed `VerifiedGuestAuthority` only when SessionKey, Manifest, Bundle, Runtime, Image Record, Archive digest and Config ID agree. `verify_guest_authority_from_host_record(request, runner)` connects those steps without accepting a caller-supplied Image ID. Writer launch consumes only this verified authority; Guest `.git` never supplies expected identity. `SliceBStartMessage` retains the existing baseline wire contract. The existing `oc2_session.py` v2 receipt remains separate; no Collector/Apply lifecycle is added.

- [ ] Write `test_refuse_receipt_inside_workspace`, `test_reject_symlink_or_partial_receipt`, `test_readback_identity_and_generation`, `test_atomic_preservation_on_interruption`, `test_guest_head_branch_tree_match`, `test_guest_rejects_tampered_bundle`, `test_reject_missing_or_wrong_manifest_digest`, `test_reject_runtime_or_policy_mismatch`, `test_reject_guest_manifest_as_untrusted_authority`, `test_reject_receipt_identity_rebinding` and `test_reject_wrong_generation_start_message`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_session sandbox.tests.test_oc2_slice_b_git -v`; expect FAIL for missing behavior.
- [ ] Implement owner-only state root, no-follow descriptor checks, exclusive/atomic receipt writes with fsync, immutable SessionKey **plus immutable baseline/Bundle SHA/Manifest SHA/transfer policy/Runtime SHA/Image Record/Image Record SHA**, explicit legal states (`REJECTED`, `RUNNING`, `PENDING`, `PRESERVATION_UNVERIFIED`) and reasons; preserve Guest original and separate identity evidence without Host repo mount.
- [ ] Implement Guest Bundle/Manifest hash verification, isolated `git init` + import/checkout without Host remote/config/hooks/filters, and independent HEAD/branch/tree/worktree readback. Host stores canonical Manifest and Receipt separately in the private state root; the trusted Guest verifier requires an out-of-band Host Receipt SHA/SessionKey, then uses that Receipt's Image Record as the only expected Archive/Config/Runtime source. It invokes `import_guest_image` with an explicit Guest socket and Supervisor-only archive path; Guest `.git` never provides expected values. Build sealed `VerifiedGuestAuthority` only after Bundle, policy, Runtime, imported Git baseline and loaded-image Config ID checks agree; only it can authorize Slice B Writer Create and produce `SliceBStartMessage`. Any mismatch/unknown state rejects launch.
- [ ] Re-run related Session/Receipt/Authority tests; expect PASS. Do not Commit in this authorized implementation task.

## Task 3 — Trusted offline image builder and F-002 enforcement

**Files:** Modify `sandbox/scripts/oc2_slice_b_image.py` and `sandbox/oc2_slice_b/Dockerfile`; create the focused Image Record/Build/Host/Guest/Verify/I/O support modules listed in File Structure; Test `sandbox/tests/test_oc2_slice_b_image.py` and `sandbox/tests/test_oc2_slice_b_image_io.py`.

**Interfaces:** Canonical immutable `ImagePin` records Source Revision, Artifact SHA-256, Runtime SHA-256, digest-pinned base, build-context/Dockerfile hashes, Config ID, Archive SHA-256/size, platform and optional provenance-only `image_ref`; canonical bytes have `record_sha256`. `build_and_export_image(ImageBuildRequest, HostImageRunner) -> ImagePin` uses an explicit socket, verifies the local base, builds with `--pull=false --network=none --quiet`, captures the Config ID, and saves by Config ID without tagging. `import_guest_image(GuestImageLoadRequest, GuestImageRunner) -> VerifiedImageAuthority` checks the owner-only Archive and Host Record, imports only into an empty Guest Store, rechecks Archive identity after Load, and inspects the full Config ID. `verify_loaded_image` validates Config ID, platform, recorded build labels and Writer Config; it does not require RepoDigests. Host/Guest runners expose only fixed operations and require explicit Unix sockets. The legacy `WriterSpec.image_ref` digest mode remains unchanged.

- [ ] Write `test_reject_unpinned_base_or_artifact`, `test_reject_credential_bearing_build_context`, canonical Record roundtrip/tamper tests, `test_reject_changed_archive`, `test_config_id_load_without_repo_digests`, `test_archive_toctou_fails_closed`, `test_reject_image_config_or_runtime_label_mismatch` and explicit-socket/no-tag Fake Runner tests.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_image -v`; expect FAIL.
- [ ] Implement the trusted Host offline Build/Export path and immutable Record using the verified binary, Runtime, Dockerfile/context and digest-pinned base. Build with an explicit Host socket and `--pull=false --network=none --quiet`; obtain the resulting Config ID directly and Save by Config ID, without a tag. The Guest verifies the Host Receipt/Record and private Archive SHA-256/size, refuses a non-empty Image Store, Loads through an explicit Guest socket, rechecks the same Archive identity, and inspects only the exact Config ID. `RepoDigests` are provenance-only and may be empty. Issue `VerifiedImageAuthority` only after checks pass. Do not Pull, Tag, or permit ordinary bare-ID Create. Use Fake Runners only; do not execute Build/Save/Load in this task.
- [ ] Run the image and I/O Fake Runner suites; expect PASS. Mark actual Host Build, Guest Load and Writer compatibility **NOT_VERIFIED**. Do not Commit in this authorized task.

## Task 4 — Image-baked PID 1 and F-004 safe fixture

**Files:** Create `sandbox/oc2_slice_b/entrypoint.py`, `sandbox/oc2_slice_b/offline_fixture.py`; Test `sandbox/tests/test_oc2_slice_b_entrypoint.py`.

**Interfaces (VB-F-005):** consume `SliceBStartMessage` defined in Task 2. `def parse_start_line(line: str) -> SliceBStartMessage` accepts **only** ASCII `OC2_SLICE_B_START <session-generation> <head-oid> <branch-ref> <manifest-sha256>\n`, exact five tokens, ≤512 bytes, LF, fixed validated canonical UUID4/40- or 64-hex OID/full approved branch ref/64-hex manifest SHA. `def run_entrypoint(start_line: str) -> int` verifies **actual Guest** HEAD/ref against the **expected values from the Trusted Supervisor line** before TUI, never discovers its own trusted expected baseline from writable `.git`. `def run_offline_fixture(repo: Path, baseline_head: str, baseline_ref: str) -> str` (Commit OID or `SliceBFixtureError`) consumes the parsed trusted values. Entrypoint is the fixed image PID 1, no env metadata key or dynamic argv; `WriterSpec.command=("run",)` stays fixed.

- [ ] Write `test_bad_or_late_start_line_skips_tui`, `test_tui_nonzero_skips_fixture`, `test_fixture_exact_bytes_and_author`, `test_uses_exact_add_N_then_commit_only_argv`, `test_other_staged_changes_survive`, `test_failure_preserves_ita_and_worktree`, `test_existing_fixture_rejected`, `test_head_divergence_skips_fixture`, `test_missing_or_late_baseline_line_skips_tui`, `test_tampered_head_ref_or_manifest_line_skips_tui`, `test_expected_baseline_not_taken_from_guest_git`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_entrypoint -v`; expect FAIL.
- [ ] Implement the 30s bounded **five-token Supervisor Baseline startup gate**, strict type/ref validation, actual HEAD/ref match before TUI, TUI exit status check and deterministic fixture in the same image PID 1 control flow. After PID 1 reaps TUI with exit 0, use the existing attach transport for a dedicated framed `FIXTURE_BOUNDARY_READY` → Supervisor snapshot → `FIXTURE_BOUNDARY_CONTINUE` barrier. PID 1 must block before fixture writes until CONTINUE; TUI terminal bytes are opaque data frames and cannot be parsed as control frames. The trusted Supervisor—not Writer—takes and retains the non-fixture Index/Working Tree snapshot while PID 1 is blocked. No new env variable, Writer file, Docker verb, or dynamic command argument. Missing/invalid/altered expected values cannot be supplied from a repo file or unlisted env variable. Exact fixed argv: `git add -N -- oc2-slice-b-fixture.txt` then `git commit --only --no-verify --no-gpg-sign -m "test(oc2): verify offline writer fixture" -- oc2-slice-b-fixture.txt`. Disable hooks/filters/signing/identity inheritance; preserve unrelated Index/WT state and abort rather than repair on uncertainty.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): run offline fixture after TUI with pathspec-only commit`.

## Task 5 — Strict Writer stdin/TTY and exact-container attach

**Files:** Modify `sandbox/scripts/oc2_writer.py`, `sandbox/scripts/oc2_supervisor.py`; Test `sandbox/tests/test_oc2_writer.py`, `sandbox/tests/test_oc2_supervisor.py`, create `sandbox/tests/test_oc2_slice_b_tty.py`.

**Interfaces:** Retain opt-in `stdin_open: bool = False` and `tty: bool = False`. Add an explicit `WriterImageIdentityMode`: existing callers default to `LEGACY_DIGEST_REF`; Slice B Config-ID mode requires `image_config_id`, `image_record_sha256`, Runtime SHA-256 and a sealed `VerifiedGuestAuthority`. `build_create_argv` emits the Config ID only for that mode and only when the authority matches the WriterSessionKey and record. `CliDockerRunner.run` rejects such a Create; only its authority-aware Create path accepts the matching sealed capability and always uses its explicit Guest socket. `validate_writer_inspect` requires both top-level `Image` and `Config.Image` to match the verified Config ID before Start and after Start. `GuestSupervisor` requires the authority at construction and before calling `WriterLifecycle.launch`; there is no ordinary bare-ID relaxation. Keep `attach_writer(identity, transport, authority)` and `InteractiveTransport` unchanged as the separate raw-byte, identity-bound interface with no generic Docker exec capability.

- [ ] Write `test_create_exact_it_only_for_slice_b`, `test_no_legacy_writer_behavior_change`, `test_unverified_config_id_rejected_by_lifecycle_and_runner`, `test_launch_requires_authority_before_factory`, `test_create_and_inspect_bind_config_id`, `test_attach_identity_mismatch`, `test_reject_short_id_and_unlisted_attach_shape`, `test_attach_transport_failure_stops_and_preserves`, `test_unverified_stop_never_reported_verified`, `test_attach_rejects_missing_or_tampered_authority`, `test_start_line_emitted_once_after_identity_verification`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_writer sandbox.tests.test_oc2_supervisor sandbox.tests.test_oc2_slice_b_tty -v`; expect FAIL for new behavior.
- [ ] Add only exact Config-ID mode, authority-gated Create, top-level/Config.Image and pre-Start/post-Start identity checks while retaining the digest-only Legacy mode and lifecycle allowlist. Preserve the existing TTY/attach implementation; no additional attach or fixture behavior is introduced by F-002.
- [ ] Re-run related Writer/Supervisor tests; expect PASS and no regression. Do not Commit in this authorized task.

## Task 6 — Dispatcher and Slice B end-to-end orchestration

**Files:** Create `sandbox/scripts/oc2_slice_b.py`; Modify `sandbox/scripts/oc2.py`; Test `sandbox/tests/test_oc2_slice_b_adapter.py`, `sandbox/tests/test_oc2.py`.

**Interfaces:** `def run_slice_b(repo_root: Path, workspace: Path, sandbox_name: str, *, dry_run: bool, ops: SliceBOps) -> int` with a protocol `SliceBOps` wrapping **only explicitly authorized** Sandbox/Git/Image/Writer operations, and injecting a fake in offline tests. Branch before credential provisioning and OAuth; maintain all existing non-Slice-B CLI behavior.

- [ ] Write `test_slice_b_dispatch_before_oauth`, `test_slice_b_rejects_credential_flags`, `test_slice_b_dry_run_no_side_effects`, `test_dirty_repo_rejected_before_sbx`, `test_baseline_changed_before_writer`, `test_unknown_exit_retains_pending`, `test_no_host_apply_or_collector_calls`, `test_legacy_launcher_unchanged`, `test_reject_host_guest_manifest_key_digest_drift`, `test_reject_untrusted_guest_baseline_source`, `test_reject_missing_runtime_identity`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_adapter sandbox.tests.test_oc2 -v`; expect FAIL.
- [ ] Implement the `--slice-b` opt-in branch before normal Credential Mixin/OAuth/`sbx exec -it` launch, preserving default behavior. Orchestrate selected and verified Runtime/image pin → verified Host Git baseline + Bundle/Manifest (passing the selected `runtime_sha256`) → immutable Host Receipt → trusted Guest private Manifest readback → `VerifiedGuestAuthority` → one exact Writer-ID `SliceBStartMessage`/TTY → bounded stop and evidence readback. The Host pins expected `manifest_sha256`, `WriterSessionKey`, `image_ref` and `image_config_id` over trusted orchestration; Guest `.git` may be checked as observed state, never used to issue expected Baseline values. All error paths maintain the Session/original; no Collect/Apply.
- [ ] Re-run tests; expect PASS. Commit after GO: `feat(oc2): connect clean Git Slice B through isolated Writer`.

## Task 7 — Constrained acceptance readback and bounded verification

**Files:** Create `sandbox/scripts/oc2_slice_b_acceptance.py`; Test `sandbox/tests/test_oc2_slice_b_acceptance.py`, extend `sandbox/tests/test_oc2_slice_b_adapter.py`.

**Interfaces (VB-F-006):** `@dataclass(frozen=True) class FixtureEvidence: session_key: WriterSessionKey; container_id: str; image_id: str; started_at: str; baseline_head: str; manifest_sha256: str; bundle_sha256: str; runtime_sha256: str; transfer_policy_id: str; commit_oid: str; parent_oid: str; fixture_sha256: str`; `@dataclass(frozen=True) class FixtureBoundarySnapshot: session_key: WriterSessionKey; container_id: str; image_id: str; started_at: str; phase: Literal["pre_fixture", "post_fixture"]; index_sha256: str; non_fixture_index_entries: tuple[...]; non_fixture_worktree_sha256: str; non_fixture_worktree_manifest: ...`; `def verify_fixture_acceptance(evidence: FixtureEvidence, before: FixtureBoundarySnapshot, after: FixtureBoundarySnapshot, guest_reader: ReadOnlyGuestReader, trusted_receipt: SliceBReceipt, authority: VerifiedGuestAuthority) -> str` returns `PASS | FAIL | NOT_VERIFIED`; both snapshots are captured by the trusted Supervisor/Guest read-only observer, pre-fixture after the READY barrier and before CONTINUE, post-fixture after Writer exit. Compare identity, Index and Working Tree snapshots as well as Manifest/Runtime/Session/Bundle/Image identity and Guest Git OIDs. Missing/mismatched phase or Writer-reported-only snapshot is `NOT_VERIFIED`. Reader is strictly constrained to non-executing Git-object/tree/Index/WT observations, **not** the Collector.

- [ ] Write `test_exact_one_parent_and_one_fixture_path`, `test_reject_unrelated_path_in_commit`, `test_reject_fixture_blob_hash_mismatch`, `test_reject_session_container_mismatch`, `test_unreadable_guest_is_not_verified`, `test_supervisor_snapshot_after_tui_before_fixture`, `test_pre_post_index_and_worktree_snapshot_match`, `test_writer_reported_snapshot_not_trusted`, `test_missing_or_wrong_phase_snapshot_not_verified`, `test_pending_for_unknown_quiescence`, `test_preservation_unverified_is_incomplete`, `test_receipt_manifest_bundle_runtime_round_trip`, `test_detect_tampered_guest_manifest_and_runtime`, `test_missing_independent_identity_readback_not_verified`.
- [ ] Run `python3 -m unittest sandbox.tests.test_oc2_slice_b_acceptance sandbox.tests.test_oc2_slice_b_adapter -v`; expect FAIL.
- [ ] Implement bounded read-only Guest OID/parent/tree/Blob and Supervisor-acquired pre/post non-fixture Index/WT snapshot comparison, correlate full Writer ID and Session generation with the Host Receipt and separately verified Guest control Manifest/Bundle SHA/Runtime SHA/transfer policy; missing or mismatched identity/snapshot/barrier is **FAIL/NOT_VERIFIED**, never an inferred PASS. Never run repository-supplied hooks, external filter or privileged arbitrary exec. Record separate `AC-13a` credential absence, `AC-13b` effective external egress, `AC-13c` inference-request nonoccurrence verdicts; untested/incomplete proof is `NOT_RUN`/`NOT_VERIFIED`, **not PASS**.
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

1. **Current checkpoint:** F-002 mode A implementation is authorized by `F002_ARCHIVE_CONFIG_IDENTITY_IMPLEMENTATION_GO`; the dedicated live probe recorded the prior RepoDigest-loss FAIL. The current task covers implementation and offline tests only.
2. Use the local branch `feature/oc2-slice-b-f002-archive-config-identity`; do not Commit/Push/PR. Follow TDD for Tasks 2/3/5 only.
3. Do not execute Tasks 6/7, Docker/Sandbox/TTY/Writer or Container operations, credentials, inference, Collector or Host Apply. Do not run an independent review loop.
4. Real Guest Load/Inspect and Writer execution remain **NOT_RUN**. A separate Owner decision is required before live acceptance.
5. Report implemented files, offline test outputs, static-check limits, residual safety concerns and the remaining live verification status. Return to Human Owner checkpoint; **no automatic PR, Merge, follow-on task, Collector or Host Apply**.

**Stop condition (F-002 mode A implementation):** Update this Plan only where its old RepoDigest-required contract contradicts mode A. Implement and verify Host Image Record/Archive handling, Receipt/Authority binding and Writer Create gating using Fake Runners. Do not modify Tasks 6/7 or execute live Docker/Sandbox/TTY/Writer actions. Stop at the Human Owner checkpoint without Commit/Push/PR.
