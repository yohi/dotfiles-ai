# OC2 Alternative A — Vertical Slice B Integration Design R0.1

- Date: 2026-11-16 (JST)
- Repository: `yohi/dotfiles-ai`
- Base: `master` at `efe4515106846e961507c1faebfd373096053e57` (PR #182 merge)
- Status: **DESIGN_CANDIDATE / OWNER_FORMAL_ADOPTION_PENDING**
- Authority: **DOCUMENT_ONLY**. This commit authorizes neither implementation, Docker/Sandbox operations, credential operations, model inference, GitHub PR/Merge, nor Host Apply.
- Parent design: [OC2 Daily Launcher Design R0.2](2026-11-13-oc2-daily-launcher-design.md). This bounded document narrows, but does not silently replace, its production Collection/Apply contracts.

## 1. Goal, outcome and boundary

The eventual product goal is to run `oc2` from the root of a Git repository and develop safely in OpenCode v2. For this **Vertical Slice B**, the independently verifiable result is narrower:

1. Accept a **clean, ordinary local-branch Git repository** on the Host.
2. Transfer a verified Git baseline preserving the exact Host HEAD commit OID and selected branch identity into a **new independent Guest repository**.
3. Run OpenCode v2.2.5 TUI under the **non-privileged Writer Container** controlled by the Trusted Guest Supervisor.
4. Support file edits, one deterministic offline test and a Git add/commit inside **that same Writer Container**.
5. Preserve the Guest Git repository and Session identity after Writer shutdown, while leaving Host HEAD, Index and Working Tree unchanged.

**Explicit non-goals:** real LLM inference, credentials, Relay, read-only Git Collector, automatic or manual Host-side Collection, Collection Digest, ApplyAuthorization, Host Apply, production-mode switching, Dirty Repository support, and superblock read-only sealing. A `PENDING` terminal state is expected when quiescence cannot be established; it must not be disguised as `STOPPED_VERIFIED` or a finalized Collection.

## 2. Existing implementation and gaps

| Existing source | Reuse and limitation |
| --- | --- |
| `bin/oc2` → `sandbox/scripts/oc2.py` | Retain the normal Phase 1–5 launch path. Add an explicit Slice B dispatch before entering credentialed setup. Current launcher passes a Git-less workspace snapshot to Guest and starts the TUI through `sbx exec`. |
| `sandbox/scripts/oc2_guest.py`, `oc2_assets.py`, `oc2_native.py`, `apm.yml` | Reuse verified v2.2.5 binary/assets and APM selections only to the extent they operate without external authentication. Do not reuse credentialed HOME, OAuth sentinel database or privileged runtime execution. |
| `sandbox/scripts/oc2_workspace.py` | Reuse suitable file/path/secret rejection logic. Its snapshot intentionally excludes `.git` and is **not** a valid Git baseline. |
| `sandbox/scripts/oc2_writer.py` | Reuse SessionKey, strict Writer spec, pinned image-reference validation, launch/stop lifecycle and hardening. Current `tty=True` creates `-t` but does **not** provide a complete interactive stdin/attach contract. |
| `sandbox/scripts/oc2_supervisor.py` | Reuse single-Writer lifecycle, container identity checks and conservative stop verdict. Its normal transport closes stdin; there is no approved interactive attach path or durable Session recovery. |

Prior PR: [#182](https://github.com/yohi/dotfiles-ai/pull/182). The foundation is merged; it is **not** connected to `oc2.py` as an end-to-end development flow.

## 3. Adopted candidate architecture

~~~text
Host clean Git repository (NO rw Guest mount)
  ├─ fail-closed Git & file preflight / branch+HEAD pin
  ├─ reachable-object & secret/path scan (bounded)
  └─ verified selective Git Bundle + Baseline Manifest
                 │ digest-bound transfer
                 ▼
Host oc2.py  --slice-b  [new explicit dispatcher]
                 │
       Slice B Host/Guest Adapter
                 │
       Mountless Docker Sandbox
         ├─ Trusted Guest Supervisor (Docker authority)
         ├─ Session-private Git repository (verified baseline)
         └─ Non-privileged Writer Container
              ├─ OpenCode v2.2.5 TUI / offline tools
              └─ edit → offline test → git add → git commit
                 │
                 ▼
       stop request → conservative verdict
                 │
         PENDING if quiescence unverified
         Guest original + private Session receipt retained

   NO Relay / credential / inference / Collector / Host Apply
~~~

**Selection:** verified Git Bundle + bounded integration adapter. Do not fabricate Git history from a workspace snapshot, transmit an unchecked `.git` directory, or implement a bespoke Git object transport for this slice. Git transfer and subsequent Writer/TTY operations are one Session with fixed identifiers.

**Proposed module boundary:**

- `oc2.py`: opt-in `--slice-b` dispatcher only; keep default behavior and existing flags unchanged. Reject incompatible credential, inference and legacy verification flags in Slice B **before any Sandbox side effect**.
- `oc2_slice_b.py` (new): orchestrate preflight, Session identity, verified staging, Guest setup, Writer launch/attach/stop and evidence recording.
- Narrow Git baseline helper (new or private to adapter): isolation-safe Git invocation, Bundle/Manifest generation and verification, Secret/allowlist checks.
- `oc2_writer.py` / `oc2_supervisor.py`: extend only the input/TTY capability and exact Identity-bound attach path needed for this slice; do **not** broadly permit arbitrary Docker CLI verbs.
- Existing Phase 5 builders: reuse only vetted artifact materialization and fingerprint validation; do not copy the privileged Guest's credential-bearing runtime environment into Writer.

`--slice-b` is a proposed opt-in flag, **not an existing CLI option**. No default-`oc2` migration is authorized by this design.

## 4. Host Git admission and deterministic baseline

### 4.1 Admitted repository

Only an ordinary **local, non-detached branch** with an existing HEAD commit is accepted. Before creating a Session, require all staged/unstaged/untracked changes to be absent; ignored files are not transferred and cannot be relied on by the offline test. At minimum reject:

- Detached/unborn HEAD, unresolved index or intent-to-add, unsupported/unknown Index formats, sparse/split index, linked worktree or `.git` file.
- Submodules; shallow or partial clones; alternates; replace refs/grafts; external object stores; Git LFS or required external clean/smudge filters.
- Ref/HEAD mismatch, unexpected ref names, unsupported object format, malicious repository-local configuration, unsupported symlinks/hardlinks or forbidden path content.
- A repo for which **every transferable reachable object** cannot be safely enumerated, validated and scanned under finite time/size/object-count limits.

Do not rely solely on `git status`, which can refresh Index or invoke untrusted filters. Use isolated, explicitly bounded, noninteractive Git commands with optional locks disabled, sanitized config/environment, no hooks, no pager, no remote access and no repository-provided external executables. Verify raw Index flags and checksum as required by the parent R0.2 contract. If a required safe read is unavailable, **reject** rather than downgrade checks.

### 4.2 Bundle & manifest

Capture the selected full `refs/heads/<branch>`, HEAD commit OID, tree OID, Git object format, canonical Git root/Workspace ID, raw Index digest, working-tree manifest digest, transfer-policy identity, and SessionGeneration. Prevent option injection and normalize/validate all ref and path input.

Build a **selective Bundle containing only the pinned HEAD and its reachable ancestors/trees/blobs**, not other branches, remote refs, tags, stashes or reflogs. Preflight **all** objects the Bundle can expose, including old commits' blobs (current Clean does not imply safe history). Reject forbidden paths, secrets, unsupported mode/type or unbounded history. The entire Bundle and accompanying manifest must be size-limited, SHA-256-bound, transferred without shared Host filesystem mounts, and independently verified in the Guest. An uninspected secret-bearing historical blob is a transfer failure, not a tolerable warning.

Import into a newly initialized, Session-private Git repository with isolated Git configuration and empty/nonexecuting hook setup. Do not copy Host `.git/config`, hooks, remotes, credential helpers, user identity, SSH agent, Git filters, or push access. After materializing the tree, require exact HEAD/branch/tree OID match, normal clean Index and expected file manifest. Neither source-provided Git config nor attributes may cause arbitrary external command execution during extraction or checkout.

Check the Host HEAD/branch, Index and worktree before Bundle creation, immediately before starting Writer and again after Writer exits; divergence means `PENDING / HOST_BASELINE_CHANGED` with no Host mutation. This does **not** prove that independent Host writers did not perform transient writes between observations.

### 4.3 Boundaries of reusability

Since a full safe history scan can reject real-world repositories, use a tiny disposable Clean fixture for the first actual demonstration. Do **not** silently substitute a synthetic one-commit repository for the requested Host baseline. Later support for large or Dirty repositories is a separate Owner decision.

## 5. Writer runtime and interactive TTY

The Supervisor remains outside the untrusted Writer. The Writer must retain the PR #182 containment contract: UID/GID 10001, no capabilities, `no-new-privileges`, read-only rootfs, bounded PID/memory, `--restart no`, `--network none`, no Docker/containerd socket, no sudo, no privileged bind and only its Session-private repository RW plus explicitly validated tmpfs mounts.

Supply a **digest-pinned verified image** containing or securely materializing OpenCode v2.2.5, Git, required offline test tools and compatible Phase 5 assets. Do not enable an unverified network install, install to the Host, import the privileged Agent HOME, or give plugins access to the credentialed Host proxy. If v2.2.5 TUI/plugins cannot run inside this boundary, mark `BLOCKED`; do not fall back to a privileged process or an old standalone runtime.

**TTY is a separate bounded capability:**

1. Introduce the minimum validated interactive stdin/TTY allocation required to run the approved Writer entrypoint. Current `tty=True` alone is insufficient.
2. Start only a newly created Writer through the existing lifecycle and verify exact 64-hex Container ID, SessionKey labels, image/config, `StartedAt` and running state.
3. Attach to **that same Writer ID** through a dedicated raw interactive I/O transport. Do not extend the normal bounded-output text transport to carry arbitrary TTY streams.
4. Allow only the exact attach operation and expected terminal modes; reject `exec`, attach to names/short IDs/foreign containers, command injection, implicit container recreation and auto-restart. Do not grant the Writer a path to Docker authority.
5. Handle Ctrl-C, detach, terminal restoration and unexpected transport failure as separate observable outcomes. Always request bounded stop and retain Session provenance; a failed attach is never assumed to mean a stopped Writer.

The deterministic offline Git edit/test/commit fixture executes inside **the same unprivileged Writer**. Passing it is not a claim that an AI model edited the files, and seeing the TUI is not evidence of successful inference.

## 6. Credential-free dispatch and existing Runtime

`oc2 --slice-b` must fork **before** the normal path provisions Credential Mixins, Cloudflare secret scope, OAuth bootstrap/import/readback, or the privileged `sbx exec -it` TUI. The Slice B branch must never execute or pass through these operations; merely sending no prompt is insufficient.

- No Host API token, OAuth sentinel, ambient credential/helper, Docker credential proxy, provider secret or Host socket is supplied to the Writer.
- No paid inference approval flag can be used to bypass the Slice B boundary; all external inference requests are disallowed in this slice.
- Preserve v2.2.5, APM SSOT and pinned Plugin identities where usable offline; reject any active Plugin/MCP dependency that would require privileged credentials or external network access rather than disabling security checks.
- Verify Runtime/CLI/Image digests at the Guest boundary and confirm the finalized Writer image exposes only the intended non-secret assets.

## 7. Session identity, stop and preservation

Use the existing `WriterSessionKey = (WorkspaceID, SandboxID, SessionGeneration)` and bind it to the Host baseline OID/ref, Git Bundle/Manifest digests, Writer full Container ID, StartedAt, image and Runtime digests.

Before Writer launch, atomically persist a **private, durable minimum Host receipt outside the Host Git workspace** (owner-only directory/file permissions, symlink/identity defenses, fsync/atomicity, immutable Session key). Guest Repository is Session-private and is not a Host mount. Confirm matching Guest Session metadata and Repository location before and after execution; distinguish an existing receipt from verified original preservation.

Stop request is owned by the Trusted Supervisor. Current `GuestHostProbe` does not establish kernel-wide RW-holder absence; preserve its conservative `None`/unverified result. Do **not** weaken it to manufacture `STOPPED_VERIFIED`. Record at least:

| Condition | Result and action |
| --- | --- |
| Invalid admission/Baseline or mismatched Guest import | `REJECTED`; do not start Writer |
| TUI/fixture completed; stop quiescence not proven | `PENDING / GUEST_QUIESCENCE_UNVERIFIED`; preserve original and identity |
| Stop/inspect/identity unknown or interrupted | `PENDING` with bounded reason; preserve and never force a new Writer |
| Host baseline changed during Session | `PENDING / HOST_BASELINE_CHANGED`; Host unchanged by OC2 |
| Guest original or identity preservation cannot be verified | `PRESERVATION_UNVERIFIED`; acceptance not achieved |

Do not automatically remove, repair, reuse, restart or mount the Guest repository as a Host worktree. No Collector, Collection Digest, Host Bundle export, Apply authorization or Host Apply may be invoked even when a restricted stop verdict is positive. Kernel immutability is **not** implied by the existence of the Session repository.

## 8. Acceptance and proof boundaries

| ID | Required observable result | Evidence class |
| --- | --- | --- |
| AC-01 | Clean local-branch fixture accepted | Offline integration; live later |
| AC-02 | Dirty/unsupported repo rejected before Sandbox/credential side effects | Offline negative tests |
| AC-03 | Guest HEAD, branch, tree, reachable objects and baseline digests match Host | Offline + Guest readback |
| AC-04 | Mountless Sandbox and hardened Writer identity/permissions match pinned configuration | Explicitly approved Sandbox test |
| AC-05 | Only Trusted Supervisor can create/stop the identified Writer | Offline + Sandbox |
| AC-06 | OpenCode v2.2.5 TUI renders via authorized same-ID interactive attach | Explicitly approved Sandbox test |
| AC-07 | Writer edits a fixture and executes an offline test | Explicitly approved Sandbox test |
| AC-08 | Same Writer creates a Git Commit | Explicitly approved Sandbox test |
| AC-09 | Observed new Guest commit descends from exact Host Baseline HEAD | Guest read-only observation |
| AC-10 | Host HEAD/Index/Working Tree unchanged by this operation | Before/after bounded comparison |
| AC-11 | Session identity and Guest Git original persist and read back | Guest/Host receipt evidence |
| AC-12 | Unverified stop is PENDING and no Collect/Apply occurs | Offline negative + bounded live |
| AC-13 | No credential injection, network access or inference request | Config/inspect/readback |

**Completion candidate:** AC-01 through AC-13 have genuinely been exercised within their approved boundaries, with Guest original preserved and Host unchanged. A correct `PENDING` is **not a failure** of this slice. However `NOT_RUN`, `NOT_VERIFIED`, `BLOCKED` and observed failure are distinct, and a `PRESERVATION_UNVERIFIED` outcome cannot be treated as completed. In particular, offline mocks cannot substitute for actual TTY behavior.

## 9. Human Owner authorization and task closure

- The existing brainstorming selected this architecture as a **candidate**. Formal design adoption is **pending**.
- This task creates **only the design document in its own feature branch**. It does not authorize starting implementation or running containers.
- Subsequent implementation, if explicitly approved, should start from current `master`, use a limited adapter/dispatcher, create a bounded test branch and stop after agreed artifacts and evidence; **no automatic follow-on PR/review/merge**.
- Sandbox/TTY acceptance is a **separate explicit Owner authorization**. Credential, network inference, Collection and Host Apply remain **HOLD**.
- Do not expand the scope in pursuit of zero findings or repeated review PASS. After a necessary bounded correction, return to the Owner checkpoint and prefer functional progress.

### Stop condition for this document task

One proposed design Markdown file is committed on a new feature branch and its path, branch head and diff are read back. No code, tests, Runtime configuration, existing design, PR or external environment is altered.
