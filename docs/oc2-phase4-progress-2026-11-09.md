# OC2 Phase 4 Progress — 2026-11-09

## 1. Scope and Result

This record documents the opt-in integration of Akane Server and Sibyl TUI
plugins into an isolated OpenCode `v2.2.5` verification Runtime. The work is on
branch `feature/oc2-phase4-akane-sibyl-integration-20261108`, based on
`00a7b8c633686f1584e5932e1393e8f2de29f4f8`.

The implementation, non-inference Runtime preparation, and Human Owner
non-inference acceptance are complete. The final verdict is
`PHASE4_NON_INFERENCE_COMPLETE`; `ACCEPTANCE_PASS` applies only to the Phase 4
non-inference acceptance scope documented here.

## 2. Pinned Sources and Artifacts

| Plugin | Package | Version | Source commit | Acquisition |
| --- | --- | --- | --- | --- |
| Akane | `@yohi/akane` | `3.0.1` | `b30772082e92cf148d5d8714266f326bad27f86a` | Verified GitHub Packages tarball |
| Sibyl | `@yohi/sibyl` | `3.0.1` | `e0249482701159bcd5a556fe06faae11dd41f66e` | Deterministic local build from the pinned source; `3.0.1` was not published in GitHub Packages at verification time |

OpenCode tag `v2.2.5` resolves to commit
`9bbb8ce18c80f099e0e448775f59d965ead40a21`. Both source commits and package
artifacts were pinned and verified before Guest Runtime preparation. The
combined Phase 4 plugin asset bundle SHA-256 is
`0567503116a1186a61d2fd237e926b3e18432b98e40855f99617ff2a00f449ee`.

## 3. Implementation Summary

- `apm.yml` declares exactly Akane and Sibyl as opt-in Phase 4 candidates, with
  immutable source identities, package versions, acquisition details, and
  artifact hashes. Normal and Phase 3 Runtime selection remains unchanged.
- Host export and Guest readback validate tarball integrity, source identity,
  package exports, file hashes, allowed paths, and the Phase 4 Runtime identity.
  Untrusted or mismatched assets fail closed.
- Akane is registered only on the server-plugin surface and restricted to the
  reserved fixture agent `__oc2_phase4_fixture__`. Its bounded settings suppress
  waiting notices and constrain ping behavior.
- Sibyl is registered only on the CLI/TUI-plugin surface. Its observer settings
  suppress model, provider, latest-text, and reasoning-summary display.
- Phase 4 requires explicit `--phase4-plugins` opt-in and a dedicated
  `oc2-phase4-*` Sandbox. Existing Runtime directories are not reused.

## 4. Isolated Runtime Evidence

- Sandbox: `oc2-phase4-akane-sibyl-20261109`.
- Runtime identity: `987f8124dbbe7407`.
- Human Owner Runtime readback reported:

  ```text
  PHASE4_RUNTIME_READBACK_PASS
  AKANE_SERVER_REGISTERED
  SIBYL_TUI_REGISTERED
  RECOVERY_TARGET_RESTRICTED
  ```

- The Sandbox has no Host Mount or Runtime Mount. The existing Network Deny
  configuration was not changed; previous policy checks denied `github.com`
  and `api.openai.com`.
- Runtime configuration and fixed-asset verification passed. `oc2-status`
  remained connected and no model provider was configured.
- Human Owner confirmed Akane's active state and zero Recovery Pings. The exact
  execution output and evidence attribution are recorded in Section 6. The
  subsequent `enabled: false` state after shutdown is consistent with Akane's
  cleanup.
- A scrubbed, no-inference PTY startup was attempted and then stopped. The
  previous automated inspection reported no sessions and `pingsSent=0`; no
  prompt, model inference, or credential transfer was performed in that run.

## 5. Verification

The focused verification runs recorded for this implementation passed:

- Fresh local regression run: **275 tests passed** with
  `python3 -m unittest discover -s sandbox/tests -p 'test_oc2*.py'`.
- Phase 4 selection, asset export, and Guest verification: 18 tests.
- Native configuration regression tests: 16 tests.
- Guest Runtime materialization tests: 9 tests.
- Host staging and orchestration tests: 178 tests.
- Akane upstream suite: 307 passed, 2 skipped; focused lifecycle/shared-state
  suite: 25 passed.
- Sibyl TUI/state/redaction/observer suite: 43 passed.
- Python compilation for changed modules and `git diff --check` passed.

`ruff` was unavailable in the environment. Existing Phase 3 monoliths were not
refactored; new Phase 4 modules passed the targeted no-excuse audit.

## 6. Human Owner TUI Acceptance and Scope Limits

The earlier automated visual-capture attempt did not produce an xterm.js browser
capture because `@xterm/xterm/lib/xterm.js` was unavailable to the QA harness.
This earlier tooling limitation is superseded by the Human Owner's subsequent
inspection of an actual OpenCode `v2.2.5` TUI screenshot. The screenshot was
provided in the conversation; no repository screenshot path or separate
artifact was supplied.

### Facts visible in the Human Owner screenshot

- Parent session: `[phase4] Sibyl parent`.
- Sibyl sidebar and `Akane Watchdog` panel are rendered.
- `Plugin: Enabled`, `Active sessions: 0`, `Pings: 0`, and
  `This session: Not tracked` are displayed.
- A child session card displays `unknown · UNKNOWN (phase4)`.
- `oc2-status` displays `Connected`; no model provider is configured.
- Parent/child session display was checked without model inference. The
  `unknown · UNKNOWN` child status is consistent with no inference having been
  run and is not an acceptance failure.

### Previously reported Human Owner execution output

The following Akane active-state values are from the Owner's execution report,
not inferred from the TUI screenshot:

```text
ENABLED: True
STATE_AGE_MS: 21975
SESSION_COUNT: 0
PINGS_SENT: 0
AKANE_ACTIVE_STATE_PASS
```

Actual model inference, live Recovery Ping injection, Agent execution, and
Agent-execution state transitions were not tested.

```text
PHASE4_STATUS: NON_INFERENCE_COMPLETE
PHASE4_NON_INFERENCE_ACCEPTANCE: PASS

IMPLEMENTATION: COMPLETE
AUTOMATED_TESTS: 275 PASS (PREVIOUSLY RECORDED)

RUNTIME_CONFIGURATION: PASS
ASSET_VERIFICATION: PASS

AKANE_SERVER_REGISTRATION: PASS
AKANE_ACTIVE_STATE: PASS

SIBYL_TUI_REGISTRATION: PASS
SIBYL_VISUAL_RENDERING: PASS
PARENT_CHILD_DISPLAY: PASS

MCP_CONNECTION: PASS
RECOVERY_PINGS_OBSERVED: 0

MODEL_PROVIDER: NOT_CONFIGURED
MODEL_INFERENCE: NOT_EXECUTED
LIVE_RECOVERY_PING: NOT_EXECUTED
AGENT_EXECUTION_STATE_TRANSITIONS: NOT_EXECUTED

VERDICT: ACCEPTANCE_PASS
SCOPE: PHASE4_NON_INFERENCE
```
