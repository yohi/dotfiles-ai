# OC2 Phase 3 Plugin and Local MCP Implementation Plan

> **For agentic workers:** Implement inline task-by-task with TDD. Do not delegate, start an independent review, run a Sandbox, or perform live acceptance.

**Goal:** Add an explicitly selected verification Runtime containing only the pinned local Superpowers OpenCode plugin and a fixed read-only local stdio MCP server, while keeping ordinary OC2 Runtime behavior disabled for both.

**Architecture:** Extend the existing APM-native parser and deterministic bundle so plugin/MCP selection is validated once and represented in configuration, file hashes, and Runtime Identity. Resolve Superpowers only from a local directory whose root `index.js` and required files can be tied to the APM-locked commit; report `NOT_AVAILABLE` without fetching when that proof is unavailable. Build a separate Runtime configuration/storage path with no real credentials, then verify the MCP implementation both in-process and as an actual local stdio subprocess.

**Tech Stack:** Python 3.14, PyYAML, JSON-RPC over stdio, OpenCode v2.2.5 configuration schema, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-08-oc2-phase3-plugin-mcp-design.md`

## Global Constraints

- Keep `apm.yml` as the source of truth; do not edit generated OpenCode configuration directly.
- Superpowers identity is `obra/superpowers`, tag `v6.4.2`, commit `8ca22dba9a94f28898bbce59f2537ff4d87c747d`; the APM marketplace lock entry is not proof that an OpenCode v2 Plugin is installed.
- Plugin verification accepts only an operator-supplied local Git checkout whose origin is `obra/superpowers`, whose `HEAD` equals the locked commit, whose worktree/index are clean, and whose root `index.js` plus all tracked files required by its local import graph match that commit. The path locates the artifact but does not establish identity. No `git fetch`, package-manager install, URL resolution, or symlink is allowed.
- Never download or install a Plugin/MCP dependency during export, Runtime preparation, or offline tests; missing verifiable local Plugin bytes yield `NOT_AVAILABLE` and fail closed.
- Ordinary OC2 keeps `plugin.use: deny`, `mcp.use: deny`, no enabled Plugin, and no MCP entries.
- Verification Runtime permits only the fixed local Superpowers directory and fixed local MCP server; it has separate config, storage, and Runtime Identity and receives no real OAuth or Cloudflare credentials.
- The MCP server exposes only read-only `oc2_status`; no filesystem, shell, network, credential, or mutation capability is permitted.
- Preserve OpenAI OAuth, Cloudflare Gateway, Guest Proxy, mountless isolation, manifest/SHA checks, no-overwrite behavior, and all existing credential boundaries.
- Do not run APM install/sync, Sandbox operations, external connections, model inference, credential lookup, commit, push, PR, or independent review.
- Offline tests must cover in-process MCP behavior and a real local subprocess stdio protocol roundtrip, including malformed-input termination and stdout cleanliness.

## Review Focus

- An APM lock pin without a local OpenCode `index.js` is `NOT_AVAILABLE`, not proof of an installable Plugin; test lock/source mismatch and absent artifact.
- Runtime mode must not be inferred from config presence; test normal mode remains deny/empty and explicit verification mode produces a distinct identity/storage path.
- Credential values must not enter either Runtime config or child environment; test known credential-shaped input rejection and the sanitized environment allowlist.
- Unknown MCP commands, tools, parameters, or paths must fail closed; test exact schema mismatch and path/command injection.
- Malformed JSON-RPC must not crash with traceback or execute a tool; test parse-error response and controlled process exit.

---

### Task 1: Tighten the APM Plugin/MCP contract and selection model

**Files:**
- Modify: `apm.yml`
- Modify: `sandbox/scripts/oc2_native.py`
- Modify: `sandbox/scripts/oc2_agent_native.py`
- Modify: `sandbox/tests/test_oc2_native.py`
- Create: `sandbox/tests/test_oc2_plugin_mcp.py`

**Interfaces:**
- Consumes: existing `x-oc2-assets`, `x-oc2-agents`, and `x-oc2-mcp` declarations plus the APM lock entry for Superpowers.
- Produces: immutable `PluginSelection` and `McpSelection` values carried by `NativeConfig`; default values mean disabled with empty selections. `parse_apm_native(raw, *, require_oc2_assets=False, verification_only=False)` is the exact parser interface. `verification_only=False` is the default and never upgrades ordinary launch. Parser selection validates the APM declaration; Task 2 separately verifies `apm.lock.yaml` and local Git provenance.
- APM declarations use `x-oc2-plugins: {enabled: false, allowlist: [superpowers]}` and `x-oc2-mcp: {enabled: false, servers: [oc2-status]}`. Disabled declarations describe fixed candidates; only the explicit `--verification-only` build option selects them.
- The only initial Plugin identity is repository `obra/superpowers`, ref `v6.4.2`, commit `8ca22dba9a94f28898bbce59f2537ff4d87c747d`; only a verified local checkout and its root `index.js` can be selected.
- The only MCP identity is server id `oc2-status`, tool name `oc2_status`, fixed Guest interpreter command `python3 -I`, fixed Runtime-contained script path, fixed stdio transport, no caller-supplied arguments, and no added environment variables. The subprocess test uses `sys.executable -I` to isolate its test process.

- [x] **Step 1: Add failing parser tests** for default-disabled declarations, valid explicit verification selection, duplicate/unknown fields, incorrect Superpowers candidate, and unknown MCP server id.
- [x] **Step 2: Run the focused tests** with `python3 -m unittest sandbox.tests.test_oc2_plugin_mcp -v` and confirm the new cases fail for the intended missing behavior.
- [x] **Step 3: Add exact APM declarations and typed selections** in `apm.yml` and `oc2_native.py`; reject every field/value outside the fixed allowlists.
- [x] **Step 4: Run the focused tests** with `python3 -m unittest sandbox.tests.test_oc2_plugin_mcp sandbox.tests.test_oc2_native -v`; all parser and default-boundary cases must pass.

### Task 2: Resolve and export the local Superpowers Plugin artifact

**Files:**
- Modify: `sandbox/scripts/oc2_assets.py`
- Modify: `sandbox/scripts/oc2_native.py`
- Test: `sandbox/tests/test_oc2_plugin_mcp.py`

**Interfaces:**
- Consumes: Task 1's `PluginSelection`; a local source path passed to `resolve_superpowers_plugin(repo, source)` as an artifact locator.
- Produces: immutable `PluginArtifact(source_commit, files)` where each `PluginFile` includes a relative path, committed bytes, and SHA-256; absent path, unavailable `.git` provenance, wrong origin/`HEAD`, dirty checkout, missing required import, symlink, or file mismatch reports `NOT_AVAILABLE`.
- The resolver accepts the supplied path only as a locator, then verifies Git origin `obra/superpowers`, exact `HEAD`, clean tracked state, and committed file bytes locally. A path that fails any check reports `NOT_AVAILABLE`. It does not use the host's full OpenCode `plugin` list or resolve an npm/git URL.
- The exported OpenCode v2 `plugins` value is the absolute Guest Runtime directory containing root `index.js`, not an npm package specifier or a file path.

- [x] **Step 1: Add failing resolver tests** for a pinned checkout with a relative dependency, absent source (`NOT_AVAILABLE`), wrong origin/commit, and dirty worktree.
- [x] **Step 2: Run the focused exporter tests** and confirm the expected failures.
- [x] **Step 3: Implement local artifact resolution** using the exact APM lock identity, a clean local Git checkout, the root `index.js`, and its allowlisted relative import closure; prohibit unbundled package imports and never fetch or install dependencies.
- [x] **Step 4: Run `python3 -m unittest sandbox.tests.test_oc2_plugin_mcp.SuperpowersPluginResolverTest -v`**; resolver success must produce the exact tracked closure and every failed provenance check must return `NOT_AVAILABLE`.

### Task 3: Add the fixed read-only local MCP stdio server

**Files:**
- Create: `sandbox/scripts/oc2_local_mcp.py`
- Test: `sandbox/tests/test_oc2_local_mcp.py`

**Interfaces:**
- Produces: a Python stdio JSON-RPC server supporting protocol initialization, initialized notification, `tools/list`, and one `tools/call` named `oc2_status`.
- `oc2_status` returns only a fixed schema/version and allowlisted component identifiers; it accepts no parameters and performs no filesystem or network access.
- Invalid JSON emits a JSON-RPC parse error and exits in a controlled nonzero manner without traceback; valid JSON-RPC errors return protocol errors without invoking tools.

- [x] **Step 1: Add failing in-process tests** for initialization, initialized notification gating, one-tool discovery, `oc2_status` output, and invalid tool arguments.
- [x] **Step 2: Run** `python3 -m unittest sandbox.tests.test_oc2_local_mcp -v` and confirm failures.
- [x] **Step 3: Implement the minimal stdio server** with newline-delimited JSON-RPC, fixed server metadata, strict request validation, and no non-protocol stdout output.
- [x] **Step 4: Run in-process tests** and confirm all allowed and rejected requests behave as specified.
- [x] **Step 5: Add subprocess protocol tests** that launch `sys.executable -I sandbox/scripts/oc2_local_mcp.py`, exchange `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`, then verify the response sequence, clean EOF, stdout-only protocol messages, malformed-input error, and controlled process exit.
- [x] **Step 6: Run** `python3 -m unittest sandbox.tests.test_oc2_local_mcp -v`; all in-process and subprocess protocol tests must pass without network access.

### Task 4: Export the verification-only Plugin/MCP bundle

**Files:**
- Modify: `sandbox/scripts/prepare_opencode_v2.py`
- Modify: `sandbox/scripts/stage_opencode_v2.py`
- Modify: `sandbox/scripts/oc2_assets.py`
- Modify: `sandbox/scripts/oc2.py`
- Test: `sandbox/tests/test_oc2_native.py`
- Test: `sandbox/tests/test_oc2_plugin_mcp.py`
- Test: `sandbox/tests/test_oc2_verification.py`
- Test: `sandbox/tests/test_oc2.py`
- Test: `sandbox/tests/test_prepare_opencode_v2.py`
- Test: `sandbox/tests/test_stage_opencode_v2.py`

**Interfaces:**
- Consumes: validated Task 1 selections, Task 2 Plugin bytes/provenance, and Task 3 MCP entrypoint.
- Produces: ordinary provider and asset bundles with disabled selection; explicit `--verification-only --plugin-dir PATH --prepare-only` exports mode-marked provider and asset bundles whose selected components and bytes are covered by manifest hashes. Host provider config remains minimal and credential-free; Guest materialization is Task 5.
- `prepare_opencode_v2._read_apm_source(root, verification_only=False)` and `oc2_assets.build(repo, verification_only=False, plugin_dir=None)` remain disabled by default. `plugin_dir` is required and validated only when `verification_only=True`.
- `oc2.py` verification mode requires `--prepare-only`, an already-existing compatible mountless Sandbox, and an already-present pinned CLI; it must neither create a Sandbox nor seed/install/download a CLI. Ordinary invocation behavior is unchanged.

- [x] **Step 1: Add failing exporter tests** for unchanged normal output, verification-mode config marker/shape, Plugin/MCP selection plus asset hashes, required `--plugin-dir`, refusal of verification mode without `--prepare-only`, and Guest-stage verifier acceptance/rejection of the verification bundle format.
- [x] **Step 2: Run focused exporter tests** and confirm the expected failures.
- [x] **Step 3: Implement mode-marked verification-only bundle export and Host option validation** in `prepare_opencode_v2.py`, `oc2_assets.py`, and `oc2.py`; preserve normal behavior and bind selections/files to deterministic hashes.
- [x] **Step 4: Run `python3 -m unittest sandbox.tests.test_prepare_opencode_v2 sandbox.tests.test_stage_opencode_v2 sandbox.tests.test_oc2_plugin_mcp sandbox.tests.test_oc2_verification sandbox.tests.test_oc2_native sandbox.tests.test_oc2 -v`**; normal and verification exports must match their respective exact allowlists.

### Task 5: Verify Guest acceptance and separate Runtime preparation

**Files:**
- Modify: `sandbox/scripts/oc2_guest.py`
- Modify: `sandbox/scripts/oc2.py`
- Create: `sandbox/tests/test_oc2_guest_verification.py`
- Test: `sandbox/tests/test_oc2_plugin_mcp.py`
- Test: `sandbox/tests/test_oc2_e2e.py`
- Test: `sandbox/tests/test_oc2.py`

**Interfaces:**
- Consumes: Task 4's mode-marked bundle and fixed allowlisted Plugin/MCP artifacts.
- Produces: ordinary Guest config with Plugin/MCP denied; alternate Runtime materialized only from a mode-marked bundle and explicit verification-only request, with exact Plugin/MCP permissions, isolated storage, and identity derived from bundle mode and hashes.
- Guest validation requires exact agreement between APM-derived selection, exported file set, plugin entrypoint, MCP command, config, and hashes; no existing Runtime is overwritten. The launcher environment uses a fixed allowlist without OAuth, Cloudflare, Docker credential proxy, or ambient credential variables.
- Guest Runtime preparation does not launch the OpenCode TUI/server. The Host's `--prepare-only` requirement prevents implicit launch; it only checks the existing pinned CLI with `--version`. A separately authorized live acceptance is needed to execute the prepared Runtime.

- [x] **Step 1: Add failing Guest tests** for mode/config/manifest mismatch, normal deny defaults, verification-only permission allowlist, exact Plugin directory and MCP command, distinct Runtime Identity/storage, refusal to overwrite existing Runtime, and no real credential or implicit OpenCode execution.
- [x] **Step 2: Run focused Guest/runtime tests** and confirm the expected failures.
- [x] **Step 3: Implement mode-aware Guest validation/materialization**; require exact mode agreement, include mode in identity/receipt, allow only fixed Plugin/MCP permissions, isolate storage, and preserve no-overwrite checks.
- [x] **Step 4: Run `python3 -m unittest sandbox.tests.test_oc2_guest_verification sandbox.tests.test_oc2_verification sandbox.tests.test_oc2_plugin_mcp sandbox.tests.test_oc2 sandbox.tests.test_oc2_e2e -v`**; both modes must be separated and Guest mismatch/tampering rejected.

### Task 6: Full offline regression and safety verification

**Files:**
- Test: `sandbox/tests/test_oc2_native.py`
- Test: `sandbox/tests/test_oc2.py`
- Test: `sandbox/tests/test_oc2_e2e.py`
- Test: `sandbox/tests/test_prepare_opencode_v2.py`
- Test: `sandbox/tests/test_prepare_opencode_v2_runtime.py`
- Test: `sandbox/tests/test_stage_opencode_v2.py`
- Test: `sandbox/tests/test_oc2_plugin_mcp.py`
- Test: `sandbox/tests/test_oc2_guest_verification.py`
- Test: `sandbox/tests/test_oc2_verification.py`
- Test: `sandbox/tests/test_oc2_local_mcp.py`

**Interfaces:**
- Consumes: all Task 1–5 outputs.
- Produces: verified offline regression evidence only; OpenCode runtime loading, actual Sandbox behavior, external calls, and model inference remain `NOT_VERIFIED`.

- [x] **Step 1: Run the full sandbox suite once** with `python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v`; all tests must pass.
- [x] **Step 2: Run syntax checks** with `python3 -m py_compile` for every changed/new Python module and test; all files must compile.
- [x] **Step 3: Run `git diff --check`**; it must report no whitespace errors.
- [x] **Step 4: Inspect the final diff and worktree state**; confirm only the intended spec, plan, source, and test files changed, no credentials or absolute machine paths were introduced, and no live operation or commit was performed.

## Execution Notes

- The current worktree does not contain an OpenCode Plugin checkout for Superpowers. The exporter must represent this state as `NOT_AVAILABLE`; fixture-based positive tests may validate resolver logic, but must not be reported as proof that the real Plugin can be loaded.
- No OpenCode process is started during offline tests. The only subprocess test is the local MCP server under `sys.executable -I` with an isolated environment and no network/API calls.
- No commit step is included because this task's instructions prohibit committing.
