# OC2 Alternative A — Vertical Slice B Integration Design R0.1.1

- Date: 2026-11-16 (JST)
- Repository: `yohi/dotfiles-ai`
- Base: `master` at `efe4515106846e961507c1faebfd373096053e57` (PR #182 merge)
- Revision: **R0.1.1 — bounded Review Gate F-001/F-002/F-003 correction only**.
- Status: **DESIGN_CANDIDATE / OWNER_FORMAL_ADOPTION_PENDING / IMPLEMENTATION_BLOCKED**
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

**Execution selection (F-001):** exactly one image-baked PID 1 entrypoint runs the TUI and, only after successful TUI exit, an offline edit/test/commit fixture **sequentially in the same Writer Container ID**. No `docker exec`, second Writer, Host-executed fixture or privileged fallback is allowed.

**Image selection (F-002):** trusted Host-prebuilt, pinned image archive loaded by the trusted Guest and verified by immutable digest before Writer start. Unsupported image import/resolution is BLOCKED, not a runtime fallback.

**Selection:** verified Git Bundle + bounded integration adapter. Do not fabricate Git history from a workspace snapshot, transmit an unchecked `.git` directory, or implement a bespoke Git object transport for this slice. Git transfer and subsequent Writer/TTY operations are one Session with fixed identifiers.

**Proposed module boundary:**

- `oc2.py`: opt-in `--slice-b` dispatcher only; keep default behavior and existing flags unchanged. Reject incompatible credential, inference and legacy verification flags in Slice B **before any Sandbox side effect**.
- `oc2_slice_b.py` (new): orchestrate preflight, Session identity, verified staging, Guest setup, Writer launch/attach/stop and evidence recording.
- Narrow Git baseline helper (new or private to adapter): isolation-safe Git invocation, Bundle/Manifest generation and verification, Secret/allowlist checks.
- `oc2_writer.py` / `oc2_supervisor.py`: only the fixed image entrypoint with narrowly validated interactive stdin/TTY and attach to the **exact inspected full Container ID**; retain the lifecycle allowlist and prohibit `docker exec`, extra Writer containers and arbitrary command execution.
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

## 5. Writer runtime and interactive TTY — F-001 / F-002

The Supervisor remains outside the untrusted Writer. The PR #182 isolation boundary is unchanged: UID/GID **10001**, no capabilities, `no-new-privileges`, read-only rootfs, PID/memory limits, `--restart no`, **`--network none`**, no Docker/containerd socket or sudo; only the Session-private Guest Git repo is RW-mounted, plus validated tmpfs. Host repositories and credentials are **not** mounted.

### 5.1 F-002 — immutable Writer image, one build/delivery path

**Selected architecture:** trusted **Host builder** prebuilds one verified Writer image **offline** → exports an image archive and immutable build manifest → transfers the verified archive through `sbx cp` → trusted **Guest Supervisor** verifies and imports it via `docker load` → only then creates the Writer with its pinned digest reference. **Neither** Writer nor Guest may build/install/download an alternative runtime. The Host build uses a reviewed version-locked Dockerfile and allowlisted context from this repo baseline, a locally cached base pinned by digest, and `docker build --pull=false --network=none`. No BuildKit network installation, on-demand registry pull or mutable tag fallback.

**Allowlisted image inputs:** existing official SHA-256/size-verified OpenCode **v2.2.5** binary, pinned base supplying Git/Python 3/fixed offline test tools, validated **non-secret** Phase 5 assets supported without Provider access, and fixed trusted entrypoint/fixture files. Reject any Plugin/MCP requiring credentials or external calls rather than secretly replacing the runtime. The build context, layers, image config, ARG/ENV and generated artifacts must not contain Host HOME, OAuth database or sentinel, Credential Mixin, Host Proxy, tokens, SSH agent, Docker authority or other secrets.

**Build-time trust boundary (Host):** verify each pinned input and base digest, then record source revision, Dockerfile/context SHA-256, base digest, v2.2.5 artifact SHA-256, non-secret runtime/fixture digests, resulting image config ID, archive SHA-256 and exact `repository@sha256:<manifest-digest>` reference in the Host-controlled manifest. A successful build **does not** prove Guest runtime acceptance.

**Pre-start trust boundary (Guest):** validate the transferred archive SHA-256 and manifest, import only as trusted Guest, then inspect the resulting local image config ID, Entrypoint/Cmd and vetted assets. The **exact** digest-qualified reference required by the existing `WriterSpec.image_ref` must **resolve locally** and match the pinned manifest/config ID before `docker create`. If `docker save/load` does not preserve a resolvable digest reference, **BLOCK** and do not weaken WriterSpec to accept a tag/bare ID or perform a network pull. This Docker Sandbox behavior and actual TUI compatibility remain **NOT_VERIFIED**.

**Launch-time trust boundary:** Supervisor validates the precise image ID/entrypoint/command, SessionKey labels, UID, mounts, capability, network and env via inspect before allowing attach. Runtime mismatch is **FAIL-CLOSED**; no credential-bearing Phase 5 HOME/OAuth path, privileged fallback or other image architecture is allowed.

### 5.2 F-001 — fixed PID 1, order, input, exit and same-ID evidence

**Single execution mechanism:** the trusted immutable image has `Config.Entrypoint = ["/opt/oc2/slice-b/entrypoint"]` and `WriterSpec.command = ("run",)`, both inspected for exact match. The entrypoint is the single Writer's **PID 1**, baked into the read-only image (never loaded from writable repo). It starts the TUI followed by the fixed fixture in sequence. The Supervisor does not invoke another container, `docker exec`, a Host script or a privileged process to run the fixture.

1. **Start:** after the Guest imports/validates the Host Git Baseline, Supervisor fixes SessionKey, baseline HEAD/branch, image ID and repository bind. Extend Writer create/inspect to demand **both `-i` (open stdin) and `-t` (PTY)**; `tty=True`/`-t` alone is insufficient. The existing lifecycle creates, checks and starts **one** Writer. Identity readback uses its **full 64-hex Container ID**, image ID, labels and `StartedAt`.
2. **Bounded attach barrier:** a dedicated raw interactive transport attaches to that exact full Container ID only (one strict attach argv shape, not added to the general bounded-output Docker transport). PID 1 awaits the single line `OC2_SLICE_B_START <session-generation>` on stdin for at most **30 seconds**. Trusted Supervisor sends it once after pre-attach identity checks. This is a **sequencing guard, not a secret or authentication mechanism**. Missing/mismatched input, attach failure or timeout skips TUI and fixture, requests bounded stop and retains Session evidence.
3. **TUI:** PID 1 verifies the fixed baseline HEAD/branch, then runs image-baked OpenCode **v2.2.5 --standalone** in the same `/workspace` and PTY. Subsequent terminal input is passed to the TUI; no model prompt or Provider call is part of this test.
4. **Offline fixture:** **only on observed TUI exit status 0** and with unchanged baseline HEAD/branch, PID 1 runs its **image-baked** deterministic fixture. It refuses an existing `/workspace/oc2-slice-b-fixture.txt`, writes exactly the UTF-8 text `OC2 Slice B offline fixture PASS\n`, executes a fixed **image-baked Python 3 assertion** of that exact file (no repository-supplied script, shell expansion or network), stages **only that file**, and makes **one Git Commit**: message `test(oc2): verify offline writer fixture`. Author and Committer **both** have name `OC2 Slice B Fixture` and email `oc2-slice-b-fixture@example.invalid`; dates/locale are fixed for this fixture. Disable signing, hooks and untrusted filters; do not inherit any Host identity/config.
5. **Exit:** PID 1 returns **0 only** after TUI=0, fixture assertion=0 and Commit success. TUI nonzero/interrupt, disconnect/detach, invalid HEAD/branch, fixture/test/commit failure or absent trustworthy exit status **never proceeds to the next phase**. Use bounded nonzero failure statuses; unknown outcomes remain **UNKNOWN**. Successful `docker attach` is not proof of process success: Supervisor inspects the same full Container ID and final `State.ExitCode`/`StartedAt`. Even if the TUI or fixture succeeded, request bounded stop and record `PENDING / GUEST_QUIESCENCE_UNVERIFIED` when quiescence is unproven. No restart, cleanup or Host apply.
6. **AC-06–09 evidence:** correlate Supervisor's **same SessionKey + full Container ID + image ID + StartedAt** (before attach, after TUI, after exit) with TUI observation, fixture/test receipt, new Commit OID and its parent OID. Treat Writer-reported records as untrusted until a **constrained read-only Guest Git/object readback**, without executing repository hooks/config or exporting data to Host, confirms observed ancestry from the Host Baseline HEAD. This acceptance-only readback is **not** the deferred Collector, and does not establish immutable tree state. Missing/different ID in any phase prevents PASS.

TUI visibility **does not prove inference**, and deterministic Git Commit success **does not prove AI-authored development**. If Guest original retention/identity cannot be confirmed, mark `PRESERVATION_UNVERIFIED` and do not claim completion.

## 6. Credential-free dispatch and existing Runtime

`oc2 --slice-b` must fork **before** the normal path provisions Credential Mixins, Cloudflare secret scope, OAuth bootstrap/import/readback, or the privileged `sbx exec -it` TUI. The Slice B branch must never execute or pass through these operations; merely sending no prompt is insufficient.

- No Host API token, OAuth sentinel, ambient credential/helper, Docker credential proxy, provider secret or Host socket is supplied to the Writer.
- No paid inference approval flag can be used to bypass the Slice B boundary; all external inference requests are disallowed in this slice.
- Preserve v2.2.5, APM SSOT and pinned Plugin identities where usable offline; reject any active Plugin/MCP dependency that would require privileged credentials or external network access rather than disabling security checks.
- Enforce `5.1's trusted Host offline build and trusted Guest archive/image verification. A non-resolvable digest-qualified image reference is `BLOCKED`; never weaken the Writer image contract.
- Evidence for **no Credential injection**, **no external communication path** and **no inference request** must be reported separately using `8.1; none of these assertions implies either of the other two.

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
| AC-04 | Mountless Sandbox and hardened Writer identity/permissions match pinned configuration | Owner-approved Sandbox test |
| AC-05 | Only Trusted Supervisor can create/stop the identified Writer | Offline + Sandbox |
| AC-06 | Fixed PID 1 renders TUI with approved same-ID attach | Owner-approved TUI evidence + **full Container ID**/SessionKey/StartedAt |
| AC-07 | Only after TUI exit 0, the same Writer edits and offline-tests the baked-in fixture | Owner-approved fixture result + **same Container ID** |
| AC-08 | Same Writer produces fixed-identity Git Commit without `exec` or another Writer | Commit OID + **same Container ID** and entrypoint phase |
| AC-09 | Observed Guest Commit descends from exact Host Baseline HEAD | Constrained read-only Guest OID/parent evidence bound to **same Container ID**, not immutable Collection |
| AC-10 | Host HEAD/Index/Working Tree unchanged | Before/after bounded comparison |
| AC-11 | Guest Git original and Session identity retained independently | Private Host Receipt + Guest original/readback |
| AC-12 | Unverified stop remains PENDING; no Collect/Apply | Offline negative + bounded live test |
| AC-13 | AC-13a / b / c each independently meet their evidence contract | Independent verdicts; never aggregate from only one assertion |

### 8.1 F-003 — AC-13 independent assertions and verdicts

| Gate | Claim | PASS requires | If missing / adverse |
| --- | --- | --- | --- |
| **AC-13a Credential non-injection** | No Host credential, OAuth, proxy auth, Secret or Docker authority reaches the **Writer** | Builder allowlist/image layer/ENV audit; Slice B dispatcher trace showing Credential Mixin/OAuth bootstrap not called; sanitized Writer runtime env/mount/socket/credential-location readback | Absent readback = **NOT_VERIFIED**; observed credential/privileged socket = **FAIL / STOP** |
| **AC-13b No external communication path** | The **Writer** has no usable network egress or Host Proxy route | `NetworkMode=none` plus network namespace/socket/mount inspect and explicit Owner-approved negative connectivity probe | Config-only/mock = effective isolation **NOT_VERIFIED**; usable egress = **FAIL / STOP** |
| **AC-13c No inference request occurred** | No Provider/model inference request during the Slice B session | Validated fixed offline entrypoint/provider restriction **and** reliable, sanitized session-scope request/audit coverage with declared visibility gaps | Incomplete observability = **NOT_VERIFIED**, even if a/b pass; observed request = **FAIL / STOP** |

**Credential absence ≠ network-path absence ≠ inference-request absence.** Trusted Host artifact acquisition, if any, is outside Writer egress scope and must be reported separately, not silently described as zero Host external communication. Static config checks may PASS **only their own static assertions**; they cannot make an unperformed live probe or absent request instrumentation PASS. At design-writing time all three are **NOT_RUN**. Do not print secrets or terminal input in evidence.

**Completion candidate:** AC-01 through AC-13 have genuinely been exercised within their approved boundaries, with Guest original preserved and Host unchanged. A correct `PENDING` is **not a failure**. `NOT_RUN`, `NOT_VERIFIED`, `BLOCKED` and observed failure remain distinct; `PRESERVATION_UNVERIFIED` cannot be treated as complete. Offline mocks cannot substitute for actual TTY behavior.

## 9. Human Owner authorization and task closure

- The existing brainstorming selected this architecture as a **candidate**. Formal design adoption is **pending**.
- This Review Gate R0.1 bounded correction updates **only this existing Design document** (F-001–F-003). It does not authorize implementation, source/test changes, Sandbox operations, PR or Merge.
- Subsequent implementation, if explicitly approved, should start from current `master`, use a limited adapter/dispatcher, create a bounded test branch and stop after agreed artifacts and evidence; **no automatic follow-on PR/review/merge**.
- Sandbox/TTY acceptance is a **separate explicit Owner authorization**. Credential, network inference, Collection and Host Apply remain **HOLD**.
- Do not expand the scope in pursuit of zero findings or repeated review PASS. After a necessary bounded correction, return to the Owner checkpoint and prefer functional progress.

### Stop condition for this document task

Only the existing Vertical Slice B design Markdown is updated and committed on the existing feature branch; the commit/file/diff are read back. Parent Design R0.2 remains unchanged. **There is no Slice B Implementation Plan on this branch**, therefore Design/Plan comparison is **NOT APPLICABLE**, not PASS. Formal design adoption stays OWNER_APPROVAL_PENDING; Implementation GO, Sandbox/TTY execution, credentials, inference, Relay, Collector, Collection Digest, Host Apply and production switching remain NOT_AUTHORIZED/HOLD. No code, test, runtime, PR, Merge, independent review or follow-up Task is started.
