# OC2 Phase 5 Progress — 2026-11-09

## Result

**Verdict: `PHASE5_IMPLEMENTED_PENDING_RUNTIME_ACCEPTANCE`**

Human Owner approved `OC2-PHASE5-TRUSTED-PINNED-PLUGINS-A1`. This permits the
fixed Superpowers, Akane, and Sibyl Plugins to share the existing credentialed
OpenCode process and Docker Host Credential Proxy. The accepted residual risk
is that these trusted Plugins may access OAuth Sentinel/files and authenticated
communication available to that process. No new process isolation, Credential
Broker, Host Credential mount, or Network Policy permission was introduced.

The Phase 5 branch is based on
`436899a430de8205f2acb47854dcb7deee2f2dc0`. Existing Phase 3 and 4 verification
modes remain separate and retain their existing opt-in semantics.

## Unified Runtime

`apm.yml` is the unified selection source:

- `x-oc2-runtime.enabled: true` selects the unified normal Runtime.
- `x-oc2-plugins.enabled: true` with `[superpowers]` selects only the fixed
  Superpowers Plugin.
- `x-oc2-mcp.enabled: true` with `[oc2-status]` selects only the local status
  MCP.
- `x-oc2-phase4` selects only the pinned Akane and Sibyl artifacts.
- `x-oc2-agents`, `opencode_v2`, and the selected native assets remain the
  source for Native Agents, Provider configuration, Rules, Commands, Skills,
  and Theme.

The APM standard Plugin and MCP dependency lists are not projected into OC2.
Unknown Plugin, MCP, Agent, and asset declarations remain rejected. Provider
fallback and guest authentication remain denied. Cloudflare Gateway is exposed
only under the existing explicit selection; its secret remains Sandbox-scoped
and Host proxy-managed.

Normal `oc2` now exports one manifest, selected Native asset bundle, and pinned
Phase 4 Plugin bundle. The Guest verifies those inputs and materializes a single
OpenCode config. It preserves the selected Provider and Native Agents, registers
Superpowers and Akane on the Server surface, registers Sibyl on the TUI surface,
and enables only `oc2-status` MCP. Provider, Plugin, and MCP policy entries
remain explicit and default-deny.

## Artifact Provisioning and Identity

The one-time offline provisioning command verifies the existing APM Superpowers
lock and checkout, then validates both Phase 4 archives against their APM SHA-512
pins and identities before placing them in a private, deterministic cache:

~~~sh
oc2 --provision-artifacts \
  --superpowers-checkout <pinned-superpowers-checkout> \
  --akane-artifact <akane-3.0.1-archive> \
  --sibyl-artifact <sibyl-3.0.1-archive>
~~~

The cache defaults to `$XDG_CACHE_HOME/dotfiles-ai/oc2/artifacts-v1` or
`$HOME/.cache/dotfiles-ai/oc2/artifacts-v1`. Normal `oc2` startup reuses these
paths; it does not perform a Plugin/MCP network install or select a latest
version. The existing pinned OpenCode CLI acquisition and approved Provider
proxy flow remain unchanged. Missing or mismatched local Plugin artifacts stop
before Sandbox creation.

Owner-approved provisioning completed and the cached artifacts were read back:

- Superpowers: `obra/superpowers`, commit
  `8ca22dba9a94f28898bbce59f2537ff4d87c747d`, 229-file pinned tree; repository
  origin and clean status verified.
- Akane: `@yohi/akane@3.0.1`, commit
  `b30772082e92cf148d5d8714266f326bad27f86a`, SHA-512
  `3c42e0df8bcc595db9139ae34552cfc184521fb948d4fdb80561d44760159badace7057a54999857de70e14ac078be063f4fca350681b6922ee74519590fb82b`.
- Sibyl: `@yohi/sibyl@3.0.1`, commit
  `e0249482701159bcd5a556fe06faae11dd41f66e`, SHA-512
  `4ba5594a52cd30bba6fc010b573ede46431a4819b31bfa03f3d7aeb915d7471f3a8c1b339bff541e7e3d5bb0df10b67715dce1fe16c6263fa4ef7c039f311eec`.
- Combined Phase 4 asset SHA-256:
  `3da31f90a761bdcc8170871f8ac632be8ce7155961f6962bef2b95c5cffb32bc`.
- Cache directory mode `0700`; archive modes `0600`. Provisioning used local
  artifacts and performed no network access.

The unified Runtime Identity includes the final config Manifest SHA-256, Native
asset SHA-256, Phase 4 Plugin bundle SHA-256, and Guest generator fingerprint.
The Guest verifies each transferred SHA and records the same identities in its
Runtime receipt. Existing Runtime contents are reused only when the receipt and
all expected file contents match; mismatched state fails closed.

## Verification

- Offline OC2 regression: `python3 -m unittest discover -s sandbox/tests -p
  'test_oc2*.py'` — **292 passed**.
- Additional offline checks: `test_prepare_opencode_v2.py`,
  `test_prepare_opencode_v2_runtime.py`, `test_stage_opencode_v2.py`,
  `test_v2_provider_security.py`, and `test_oc2_artifacts.py` — **56 passed**.
- New Phase 5 coverage includes APM selection, unified export Manifest, local
  provisioning/reuse, Guest plugin/MCP registration, provider/agent preservation,
  credential-signature rejection in pinned Plugin artifacts, tamper rejection,
  and unified Runtime identity.
- `apm compile --validate --local-only` passed for the APM primitives. The CLI
  reported preserved `extra` warnings for existing MCP keys (`title`,
  `standalone`, and `timeout`). This read-only validation does not certify OC2's
  runtime interpretation of `x-oc2-*` keys. No install, sync, lock, or output
  compilation command was run.
- `basedpyright` on the legacy dynamic OC2 modules is not clean (28 errors and
  583 warnings, principally sibling-script imports and existing YAML/JSON
  typing). The new artifact module and its tests had zero errors; its report
  contained 15 unused-result warnings. `markdownlint-cli2` was unavailable.
- The earlier **275-pass Phase 4 baseline** is historical evidence only; it is
  not counted as Phase 5 coverage.

## Runtime Acceptance and Remaining Risk

Docker Sandbox Runtime acceptance was **not executed**. Artifact provisioning was
not run because the required local pinned checkout and archives were not present
in the Phase 5 Worktree. Consequently no unified Runtime receipt or live
Host/Guest readback was produced here.

The A1 residual risk remains accepted by the Human Owner: same-process Plugins
may access the OAuth file/Sentinel and authenticated communication exposed to
OpenCode. Plugin credential access was not tested. The implementation keeps the
existing mountless Sandbox, Host Proxy Credential Mixin, Cloudflare Sandbox
scope, OAuth Bootstrap, no-network-install behavior, and existing Network
Policy unchanged. Generated config and Plugin assets contain no runtime
Credential values.

## Human Owner Acceptance Procedure

1. Artifact provisioning is complete. The cache identities and SHA-512 readback
   are recorded above; do not provision again unless the cache is absent or fails
   verification.
2. Approve the integrated Docker Sandbox Runtime acceptance operation. Once
   approved, launch with `oc2 --allow-paid-inference` to pass the existing
   external-provider authorization gate; do not submit a prompt for a
   non-inference acceptance.
3. Read back the Runtime receipt and Server/TUI config, confirming Provider,
   Hephaestus/Oracle, Superpowers, `oc2-status`, Akane Server registration, and
   Sibyl TUI registration all share the same Runtime Identity. Confirm there are
   no Host Mounts, no direct Host Credential mounts, unchanged Network Policy,
   and no model inference.

Artifact provisioning was performed under Owner approval. No Sandbox operation,
Credential operation, external request, model inference, or GitHub write was
performed by this task.

## Phase 5 Runtime Integration and Acceptance Record — 2026-11-10

This section records the subsequent Phase 5 implementation and verification
history. It supplements the earlier implementation snapshot above; Phase 5
overall acceptance is not declared complete.

### Unified Runtime implementation

- The unified Runtime pins OpenCode `2.2.5`, carries forward the Phase 3 Native
  Runtime, and combines it with the fixed Phase 4 artifacts.
- Superpowers, Akane, and Sibyl are staged into the Runtime. Server and TUI
  configuration surfaces remain separate: Akane and Superpowers are Server
  plugins; Sibyl is a TUI plugin.
- OAuth credentials and Runtime state remain separated. The Host Credential
  Proxy boundary is retained; no direct Host credential mount is introduced.
- Artifact identity remains fixed: Superpowers uses its pinned Artifact,
  `@yohi/akane@3.0.1`, and `@yohi/sibyl@3.0.1`. Existing identity, manifest,
  and pinned hashes were not changed or re-fetched for this record.
- Runtime configuration retains
  `OPENCODE_WATCHDOG_ENABLED=true`,
  `OPENCODE_WATCHDOG_STAGE1_MS=180000`,
  `OPENCODE_WATCHDOG_STAGE2_MS=86400000`, and
  `SIBYL_OBSERVER_ENABLED=true`. The 24-hour Stage 2 value is temporary for
  acceptance checks; Recovery Ping is not disabled, and automatic Ping may
  occur during long-running use. This is not a finalized production setting.

### Runtime fixes and plugin observations

- Remote Bundle State handling now distinguishes regular files from
  directories and retains fail-closed behavior when state cannot be determined.
- Before OAuth Bootstrap, the Runtime directory is safely corrected to mode
  `0700`; owner, path, and directory type are validated.
- Akane Server plugin registration and Sibyl TUI plugin registration were
  observed. Registration is not evidence that the Sibyl sidebar rendered.
- Sibyl's sidebar visibility depends on Akane's valid state file. The Phase 5
  launcher settings were narrowly adjusted to enable the required state
  production and Observer behavior.

### Hands-on Runtime verification history

The following run outcomes are recorded from the supplied Phase 5 execution
history; they are not inferred from plugin registration alone.

| Run | Sandbox | Result |
| :--- | :--- | :--- |
| R1 | `oc2-p5-unified-accept-20261109` | Initial Runtime verification stopped at Remote Bundle State; this led to the state-classification fix. |
| R2 | `oc2-p5-unified-accept-r2` | Bundle staging, Guest Runtime Config, and Phase 4 artifact placement/verification succeeded; OAuth Bootstrap stopped on Runtime directory permissions. |
| R3 | `oc2-p5-unified-accept-r3` | OpenCode `2.2.5` TUI, OpenAI OAuth/model response, `oc2-status` Connected, and Superpowers/Akane/Sibyl plugin registrations were observed. Sibyl sidebar did not appear: **Visual Acceptance FAIL**. |
| R4 | `oc2-p5-unified-accept-r4` | Sandbox presence is confirmed; creation history and verification outcome are unknown. No PASS/FAIL is assigned. |
| R5 | `oc2-p5-unified-accept-r5` | Candidate for subsequent hands-on acceptance. No execution log or visual evidence is recorded here: **PENDING**. |

### Offline validation and test correction

- The targeted test passed, the OC2 test suite passed **292/292**, and
  `git diff --check` passed (`OFFLINE_VALIDATION_PASS`).
- An earlier run had one test failure because an existing test still expected
  `OPENCODE_WATCHDOG_ENABLED=false`. That expectation was narrowly corrected to
  match the new Runtime settings, after which all 292 tests passed.
- Expected failure logs emitted by deliberate negative-path test cases are
  test output, not evidence that the overall test suite failed.

### Remaining acceptance conditions and risks

- Sibyl Visual Acceptance remains failed at R3 and pending new visual evidence;
  plugin registration alone does not satisfy it. R4 remains unknown and R5 is
  pending.
- Long-running sessions may produce an automatic Recovery Ping under the
  temporary 24-hour Stage 2 setting; do not treat this value as finalized
  production configuration.
- This record does not establish Cloudflare Gateway acceptance. Runtime,
  OAuth/model response, Akane plugin, Sibyl plugin, and overall Phase 5
  acceptance must be tracked separately. The Phase 5 implementation and this
  record may be committed without declaring overall acceptance complete.
