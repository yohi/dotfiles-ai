# OC2 Phase 4 Progress — 2026-11-09

## 1. Scope and Result

This record documents the opt-in integration of Akane Server and Sibyl TUI
plugins into an isolated OpenCode `v2.2.5` verification Runtime. The work is on
branch `feature/oc2-phase4-akane-sibyl-integration-20261108`, based on
`00a7b8c633686f1584e5932e1393e8f2de29f4f8`.

The implementation and non-inference Runtime preparation are complete. Actual
Sibyl sidebar rendering has not received visual or Human Owner acceptance. The
current verdict is therefore `IMPLEMENTED_PENDING_TUI`.

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
- Guest readback confirmed Akane in the server plugin configuration and Sibyl
  in the CLI/TUI plugin configuration. `oc2-status` remained present; no model
  or provider was configured.
- The Sandbox was created without static MCP mounts and with a deny-all network
  policy. Policy checks denied `github.com` and `api.openai.com`.
- A scrubbed, no-inference PTY startup was attempted and then stopped. The
  Akane state file reported no sessions and `pingsSent=0`; no Recovery Ping,
  prompt, model inference, or credential transfer was performed.
- No OpenCode process remained in the Sandbox at the time of final status
  inspection.

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

## 6. TUI Acceptance and Remaining Work

The TUI launch path was exercised in a scrubbed PTY, but no fresh xterm.js
browser capture was produced. The visual capture attempt was blocked because
`@xterm/xterm/lib/xterm.js` was unavailable to the QA harness. As a result,
Sibyl sidebar rendering and Human Owner visual acceptance remain unverified.

The Human Owner must inspect the prepared Runtime TUI and confirm the sidebar
appears and cleans up on exit. Until that confirmation is recorded, this report
does not claim `ACCEPTANCE_PASS`.

```text
IMPLEMENTATION: COMPLETE
ISOLATED_RUNTIME_PREPARATION: PASS
NETWORK_DENY: PASS
INFERENCE_OR_RECOVERY_PING: NOT_EXECUTED
SIBYL_TUI_VISUAL_ACCEPTANCE: PENDING_HUMAN_OWNER
VERDICT: IMPLEMENTED_PENDING_TUI
```
