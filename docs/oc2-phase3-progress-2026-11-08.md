# OC2 Phase 3 Progress — 2026-11-08

## 1. Purpose / Scope

This record summarizes verified OpenCode v2.2.5 Phase 3 implementation and
acceptance evidence on branch
`feature/oc2-phase3-apm-native-integration-20261107`. It records current
progress only; Phase 3 is not declared complete.

The verification used the existing `oc2-p3-verify-20261108` Sandbox and fixed
Superpowers commit `8ca22dba9a94f28898bbce59f2537ff4d87c747d`.

## 2. Implementation Summary

### Native Agents

- `hephaestus` is configured as the Primary Agent.
- `oracle` is configured as a read-only Subagent.
- Both use `openai/gpt-6-luna`; the configuration constrains unintended
  default/fallback model use.
- Oracle edit, shell, task, and MCP permissions are denied.
- `apm.yml` remains the single source of truth.

Configuration checks passed: `AGENT_SET`, `AGENT_MODES`, `AGENT_MODELS`,
`ORACLE_READ_ONLY`, `NORMAL_PLUGIN_DISABLED`, `NORMAL_MCP_DISABLED`, and
`NATIVE_AGENT_CONFIG_PASS`. Recognition and selection of these agents in a
Normal Runtime TUI remain unverified.

### Superpowers Plugin, Skills, and MCP

- The fixed local Git checkout was verified against the APM lock, origin, clean
  status, and commit `8ca22dba9a94f28898bbce59f2537ff4d87c747d`.
- The Node entrypoint is `package.json`'s
  `.opencode/plugins/superpowers.js`; its fixed-commit imports are the Node
  built-ins `path`, `fs`, and `url`.
- Those three bare specifiers are explicitly allowed. Unapproved Node specifiers
  and external dependencies remain rejected.
- The Asset Bundle contains the selected Plugin dependency closure and all 15
  `skills/*/SKILL.md` files: 18 Plugin-related files total.
- The Asset Bundle is 243,796 bytes, below the unchanged 512 KiB limit.
- Plugin source files are checked against the clean Git checkout, then checked
  against the pinned 229-file source tree in the Guest Runtime.
- `plugin.use` remains deny-first, with an allow rule for only the Runtime's
  absolute Superpowers directory.
- `oc2-status` is the only individually allowed MCP server; `mcp.use` remains
  deny-first.

## 3. Runtime Identity / Hashes

- Verification Runtime ID: `30cb255a5d039267`
- Manifest SHA-256:
  `37937c2f4f436e1dcbbc3a8b2ed19774992f93825efb5f09b83e471f834d79a4`
- Asset SHA-256:
  `a0446729fbbd56e3a210f7070d6ff2ea01fb1e17ff51fd7eb93b5c95bec3753f`
- Verification generator fingerprint:
  `fbf29d2a9cafc283fe026ff0310fe7cf991d7ecf0194f8056d9b0f527e3e80e4`
- Pinned source: 229 files, 1,974,678 bytes, tree SHA-256
  `19ba95fe50e96fb94d8260972cb50595ed31ada3f993e370b381a1e7718c5036`.

The identity includes the manifest, assets, Guest materializer, Native helper,
and Identity helper. Host and Guest calculation agree; a collision fails
closed. Existing Runtime IDs `40b9d5de2aa84145` and `37e2c02e57019067` were
preserved.

## 4. Test and Acceptance Evidence

The latest focused regression runs passed:

- `test_oc2.py`: 176 tests.
- `test_oc2_guest_verification.py`: 8 tests.
- `test_oc2_verification.py`: 4 tests.
- `test_oc2_plugin_mcp.py`: 19 tests.
- Total: 207 tests passed.
- Ruff checks and `git diff --check` passed.

The tests cover the fixed package entrypoint, the three required Node built-ins,
rejection of unapproved dependencies, collection and SHA verification of Skill
assets, Guest verification against the pinned tree, absolute-path Plugin policy,
Runtime identity agreement, and fail-closed Runtime collision behavior.

## 5. TUI Acceptance

The Human Owner reported the following Verification Runtime TUI checks as
passing:

- TUI startup, command UI startup, and key input.
- MCP status display.
- Superpowers listed by `/plugins`.
- Superpowers Skills listed by `/skills` and available through `@` completion.

The Verification Runtime intentionally does not contain Native Agents.
Normal Runtime Agent recognition and selection in the TUI have not been tested.

## 6. Security Boundaries

- Docker Sandbox isolation and Network Deny were retained.
- No provider credentials were added and no Paid inference was run.
- Provider, Integration, Plugin, and MCP policies remain deny-first; only the
  fixed Plugin absolute path and `oc2-status` MCP server have individual allow
  rules.
- File-count, per-file, and total Asset limits remain unchanged. Symlink and
  fixed-commit SHA checks remain enabled.
- The managed OpenCode service's temporary local authentication state was
  removed after normal shutdown. No credential state remains from acceptance.
- Neither protected Runtime was modified or deleted.

## 7. Remaining Verification

- Normal Runtime TUI recognition and selection of `hephaestus` and `oracle`.
- Model-driven Superpowers Bootstrap injection.
- Agent-mediated MCP Tool Call.

Direct MCP JSON-RPC evidence for `initialize`, `tools/list`, and `tools/call` is
reused from the prior acceptance. Those calls were not repeated in this run.
Unexecuted items are not classified as failures.

## 8. Current Verdict

```text
PHASE3_STATUS: IN_PROGRESS

Verification Runtime:
  ACCEPTANCE_PASS

Verification Runtime TUI:
  PASS

Native Agent Configuration:
  PASS

Normal Runtime Native Agent TUI:
  NOT_EXECUTED

Model-driven Bootstrap:
  NOT_EXECUTED

Agent-driven MCP Tool Call:
  NOT_EXECUTED
```
