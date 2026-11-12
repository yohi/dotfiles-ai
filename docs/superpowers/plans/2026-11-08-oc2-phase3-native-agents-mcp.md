# OC2 Phase 3 Native Agents and MCP Implementation Plan

> **For agentic workers:** Execute inline in this session. Use the existing unittest suite and TDD; do not delegate or start independent review.

**Goal:** Add two explicitly selected Native Agents to the OC2 Guest config while preserving fail-closed Agent permissions and keeping MCP explicitly disabled when no safe server is available.

**Architecture:** `x-oc2-*` APM extensions select allowlisted settings. A small native-config module parses them and emits a deterministic Agent/MCP payload included in the existing asset manifest. The v2 exporter uses the same validated Agent configuration; the Guest validates the payload and confirms that its Agent map matches the generated config. The existing asset SHA continues to participate in Runtime Identity.

**Tech Stack:** Python 3.14, PyYAML, OpenCode v2.2.5 config schema, unittest.

**Spec:** User-provided “OC2 Phase 3 — Remaining Work Implementation Instruction” and the follow-up approval in this conversation; frozen baseline `2ebcc963ea53f792b88d99f285d7eb75ff96171e`.

## Global Constraints

- Keep `hephaestus` as `primary`, `oracle` as `subagent`; both use only `openai/gpt-6-luna`.
- Do not set `default_agent`, model fallback, category routing, or automatic subagent launch.
- `oracle` is read-only; deny edit, shell, task/delegation, web, and MCP permissions.
- MCP default is disabled, its allowlist is empty, and `mcp.use` remains denied.
- Preserve OAuth, Cloudflare Gateway, Guest Proxy, mountless isolation, Credential isolation, Manifest/SHA-256, and no-overwrite behavior.
- Do not run APM install/sync, Sandbox operations, external connections, model inference, Commit, Push, PR, or independent review.

## Review Focus

- Duplicate or malformed YAML extension keys and non-vendor extension names must fail closed.
- Agent names, modes, model IDs, and permission tuples must match the fixed allowlist exactly.
- APM source hashes used by the config export and native-asset manifest must match.
- Any enabled or unknown MCP server must fail closed; default output must have no server entries.
- Guest config/asset mismatch or an existing Runtime must not be overwritten.

---

### Task 1: Parse and constrain OC2 native declarations

**Files:**
- Modify: `sandbox/scripts/oc2_native.py`
- Modify: `sandbox/scripts/oc2_agent_native.py`
- Modify: `apm.yml`
- Test: `sandbox/tests/test_oc2_native.py`

**Interfaces:**
- Produces `NativeConfig` containing the validated Agent map, disabled MCP state, and selected Asset source paths.
- Agent IDs are restricted to `hephaestus` and `oracle`; model is fixed to `openai/gpt-6-luna` and must remain in the enabled OpenAI APM whitelist, independently of the global V2 default.
- `oc2_agent_native.py` owns the stdlib-only native payload schema and shared Agent/Plugin/MCP identifiers and validation contracts used by Host and Guest. Keep its `AgentName`, `AgentMode`, `Permission`, `build_native_payload`, `validate_agent_map`, `validate_native_asset`, and `validate_component_selection` interfaces aligned with `oc2_native.py` parsing and serialization.
- The APM extension contract includes fixed disabled candidate declarations: `x-oc2-plugins: {enabled: false, allowlist: [superpowers]}` and `x-oc2-mcp: {enabled: false, servers: [oc2-status]}`. These lists identify candidates only; they do not enable or select them. Native Agents/MCP defaults remain disabled/empty unless an explicit verification selection is specified. Reject unknown fields, candidate IDs, and enabled values.

- [x] Add failing tests for valid declarations, unknown/duplicate names, unauthorized model/permission fields, and enabled/unknown MCP entries.
- [x] Run `python3 -m unittest sandbox.tests.test_oc2_native -v` and confirm the expected failures.
- [x] Add the APM `x-oc2-assets`, `x-oc2-agents`, `x-oc2-plugins`, and `x-oc2-mcp` extensions with fixed disabled candidate lists; migrate the existing asset declaration without changing its selected paths.
- [x] Implement typed parsing and exact allowlist checks in `oc2_native.py`; pass focused tests.

### Task 2: Bind Native Agents to the existing asset/config/runtime flow

**Files:**
- Modify: `sandbox/scripts/oc2_assets.py`, `sandbox/scripts/oc2_native.py`, `sandbox/scripts/oc2_agent_native.py`, `sandbox/scripts/prepare_opencode_v2.py`, `sandbox/scripts/oc2_guest.py`, `sandbox/scripts/oc2.py`
- Test: `sandbox/tests/test_oc2_native.py`, `sandbox/tests/test_oc2.py`, `sandbox/tests/test_oc2_e2e.py`

**Interfaces:**
- Asset manifest adds a deterministic native-config artifact with the validated Agent map and disabled Plugin/MCP candidate selections as represented by `oc2_agent_native.py`; the disabled candidate allowlists in `apm.yml` are not active selections.
- The V2 config exporter emits the same Agent map using the OpenCode v2.2.5 `agents` object schema.
- Guest validation compares the config Agent map to the verified native-config artifact; the existing asset SHA remains in Runtime Identity.

- [x] Add failing tests for native-config manifest inclusion, model/mode/permission validation, source SHA agreement, Guest mismatch rejection, and no default Agent.
- [x] Implement the shared native-config projection and connect it to export, Guest verification, and the existing Runtime identity path.
- [x] Verify `oracle` cannot write, execute shell, delegate, access external tools, or use MCP; verify `hephaestus` has explicit permissions and requires approval for shell/delegation.
- [x] Run the focused OC2 tests and confirm Task A OAuth/Gateway assertions remain intact.

### Task 3: Lock offline Skill, Theme, APM, and MCP boundaries

**Files:**
- Modify: `sandbox/tests/test_oc2.py`, `sandbox/tests/test_oc2_e2e.py`

**Interfaces:**
- MCP remains absent/disabled in the emitted v2 config and the existing deny policy remains unchanged.
- Skill/Theme/APM checks are static; runtime loading and visual appearance remain `NOT_VERIFIED` without starting a Sandbox or model.

- [x] Add structural tests for both Skill frontmatters and config/command paths, the `tokyonight` CLI theme value, and the APM `x-` extension contract.
- [x] Add tests that MCP is disabled with an empty server list and that an unapproved server cannot be serialized.
- [x] Run the full sandbox unittest suite once.
- [x] Run `py_compile` for changed Python files and `git diff --check`.
- [x] Report verified vs. unverified runtime behavior and the remaining TOCTOU risk; stop without Commit/Push/PR.
