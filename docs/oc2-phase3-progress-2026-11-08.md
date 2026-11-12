# OC2 Phase 3 Progress — 2026-11-08

## 1. Purpose / Scope

This record summarizes verified OpenCode v2.2.5 Phase 3 implementation and
acceptance evidence on branch
`feature/oc2-phase3-apm-native-integration-20261107`. The status recorded in
earlier sections reflects evidence available at that time. The final verdict
below records completion of the non-inference integration scope only.

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
`NATIVE_AGENT_CONFIG_PASS`. Normal Runtime TUI recognition and selection were
subsequently confirmed by the Human Owner, as recorded in Section 5.

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

### Normal Runtime

- Sandbox: `oc2-p3-core-accept-20261108`
- Runtime ID: `8496c04faec39ba6`
- OpenCode: `v2.2.5`
- Identification verdict: `NORMAL_RUNTIME_IDENTIFIED`
- `RUNTIME_EXISTS`, `CONFIG_EXISTS`, `ASSET_RECEIPT_EXISTS`: PASS.
- `AGENT_SET`, `HEPHAESTUS_PRIMARY`, `ORACLE_SUBAGENT`, `MODELS`,
  `ORACLE_READ_ONLY`: PASS.
- `PLUGIN_DISABLED`, `MCP_DISABLED`: PASS.
- `RECEIPT_ID`, `RECEIPT_ASSET_SHA`: PASS.

The receipt for this Runtime is `assets-receipt.json`. The absence of
`receipt.json` in this generation path is expected and was not treated as an
error. This Normal Runtime is distinct from the Verification Runtime above.

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

The Human Owner confirmed the following Normal Runtime TUI checks on
`2026-11-08 JST` using OpenCode `v2.2.5`:

1. TUI started normally: PASS.
2. `hephaestus` appeared in the Agent selection UI and was selected: PASS.
3. `oracle` appeared using `@oracle`: PASS.
4. `oracle` was inserted into the input field without sending the input: PASS.
5. TUI exited normally: PASS.

The Normal Runtime Agents are `hephaestus` (Primary) and `oracle` (read-only
Subagent); both are fixed to `openai/gpt-6-luna`. No prompt was sent and no
inference was performed. These interactive results are based on the Human
Owner's report; they were not automated or recorded by the agent.

The Human Owner also reported the following Verification Runtime TUI checks as
passing:

- TUI startup, command UI startup, and key input.
- MCP status display.
- Superpowers listed by `/plugins`.
- Superpowers Skills listed by `/skills` and available through `@` completion.

The Verification Runtime intentionally does not contain Native Agents. Its
acceptance covers the Plugin, Skills, and MCP behavior listed above; it is not
the Normal Runtime Native Agent TUI target. In OpenCode `v2.2.5`, Skills being
available through `@` completion rather than `/` completion is expected.

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

- Model-driven Superpowers Bootstrap injection.
- Agent-mediated MCP Tool Call.
- Actual LLM inference response.
- Paid inference.

Direct MCP JSON-RPC evidence for `initialize`, `tools/list`, and `tools/call` is
reused from the prior acceptance. Those calls were not repeated in this run.
The model-driven Bootstrap, agent-driven MCP Tool Call, actual LLM inference
response, and paid inference were not executed. These are unverified execution
scenarios, not observed failures, and do not block completion of the
non-inference integration scope.

## 8. Current Verdict

```text
PHASE3_STATUS: NON_INFERENCE_COMPLETE
PHASE3_NON_INFERENCE_ACCEPTANCE: PASS

Normal Runtime:
  Sandbox: oc2-p3-core-accept-20261108
  Runtime ID: 8496c04faec39ba6
  OpenCode: v2.2.5
  TUI: PASS
  hephaestus Primary selection: PASS
  oracle Subagent reference and insertion: PASS
  Model pin: openai/gpt-6-luna (both Agents)
  Oracle read-only permissions: PASS

Verification Runtime:
  ACCEPTANCE_PASS
  TUI: PASS
  Superpowers Plugin: PASS
  Native Skills (15): PASS
  oc2-status MCP connected: PASS

Native Agents:
  PASS

Superpowers Plugin:
  PASS

Native Skills:
  PASS

Local MCP Integration:
  PASS

Model-driven Bootstrap:
  NOT_EXECUTED

Agent-driven MCP Tool Call:
  NOT_EXECUTED

Actual LLM Inference Response:
  NOT_EXECUTED

Paid Inference:
  NOT_EXECUTED
```
