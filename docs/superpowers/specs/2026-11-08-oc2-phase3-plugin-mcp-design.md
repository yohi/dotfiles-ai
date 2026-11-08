# OC2 Phase 3 Plugin and Local MCP Verification Design

## Status

Design reviewed with limited corrections accepted. This document is not an
acceptance record. No Sandbox, OpenCode runtime, network service, or
credential-bearing process is started by this design or its offline tests.

## Purpose

Extend OC2 Phase 3 so its isolated OpenCode v2 configuration can represent one
explicitly allowlisted external plugin and one fixed local read-only MCP server
for offline verification. Normal OC2 operation remains unchanged: plugins and
MCP are disabled, and generated configuration is never activated implicitly.

## Existing constraints

- `apm.yml` remains the source of truth. Generated OpenCode configuration is
  never edited directly.
- Preserve existing provider, OAuth, Cloudflare Gateway, Guest Proxy,
  mountless isolation, asset manifest/hash, and no-overwrite behavior.
- Keep the extension parser fail-closed. Unknown, duplicate, malformed, or
  additional fields are rejected.
- No APM install/sync, Sandbox operation, external connection, model inference,
  credential lookup, commit, push, or PR is part of offline verification.
- Runtime plugin loading and MCP tool invocation in OpenCode remain explicitly
  unverified until a separately approved live acceptance.

## Configuration and selection

Add OC2-specific plugin and MCP declarations to `apm.yml`, alongside the
existing `x-oc2-assets`, `x-oc2-agents`, and `x-oc2-mcp` declarations. The
normal declarations remain disabled. A dedicated `--verification-only`
export/runtime option may request the fixed allowlist; it must not change the
normal launcher or global OpenCode configuration. The local Plugin path is a
locator only; its Git origin, commit, clean state, and required bytes must all
be verified before use.

The initial external plugin candidate is Superpowers, pinned to the existing
APM dependency `obra/superpowers#v6.4.2`, resolved commit
`8ca22dba9a94f28898bbce59f2537ff4d87c747d`. The APM lock entry records the
marketplace package deployment (Skills and Hooks); it does not prove that an
OpenCode v2 plugin directory is present. The exporter must therefore verify
both the lock pin and a locally present OpenCode v2 plugin directory containing
the root `index.js` and all required files against the fixed commit. OpenCode v2
configuration must reference the verified plugin directory. The exporter must
not install or fetch the plugin. If the local plugin artifact or verifiable
source identity is unavailable, report `NOT_AVAILABLE` and stop. The generated
config contains only this selected plugin; no other `plugin` entries from the
host's full APM manifest are copied.

The APM declaration records the fixed candidate identity while leaving it
disabled by default: `x-oc2-plugins` has exactly `enabled: false` and
`allowlist: [superpowers]`. The fixed MCP candidate is declared as
`x-oc2-mcp` with exactly `enabled: false` and `servers: [oc2-status]`. Only the
verification-only option may select those declared candidates.

The MCP selection is one repository-owned local stdio server. It exposes only a
bounded `oc2_status` read-only tool returning the OC2 schema/version and
allowlisted component identifiers needed to prove protocol discovery. It has no
filesystem, shell, network, credential, or mutation tools. Its implementation
and launch command are fixed by the exporter; caller-supplied commands,
arguments, environment variables, and paths are rejected.

Both selections are opt-in for a dedicated verification Runtime only. The
explicit preparation command is `oc2 --verification-only --plugin-dir PATH
--prepare-only`; verification mode requires an already-existing compatible
mountless Sandbox with the pinned OpenCode CLI. It does not create a Sandbox,
seed a CLI, install packages, or start the OpenCode TUI/server; it only checks
the existing CLI with `--version`. The ordinary `oc2`/dry-run
path continues to serialize no enabled plugin and no MCP server, and retains
`plugin.use: deny` and `mcp.use: deny`. The verification Runtime has a distinct
configuration, storage path, and Runtime Identity; its configuration permits
only the fixed Superpowers directory and local MCP server, not blanket
Plugin/MCP use. No real OpenAI OAuth or Cloudflare credential is available to
this Runtime.

## Data flow and validation

1. Parse the OC2 plugin/MCP declarations from `apm.yml` with duplicate-key
   detection and exact field/value allowlists.
2. Resolve the plugin only from an existing local Git checkout supplied as a
   locator; verify its repository origin, pinned commit, clean state, and
   required committed files, then hash the exported bytes. Never resolve an
   npm/git URL at export or Guest runtime.
3. Export the selected plugin and fixed local MCP server in the asset bundle.
   Include both in the deterministic manifest, per-file hashes, aggregate SHA,
   and runtime identity.
4. Generate the OpenCode v2 configuration from the same validated selection.
   Validate exact agreement between the configuration, manifest, and selected
   component IDs before Guest runtime preparation.
5. Preserve existing Guest checks: verified bundle hash, fixed destination
   paths, no symlinks, no unknown files, and no overwrite of an existing
   Runtime.
6. Offline tests exercise parsing, artifact identity failure, manifest and
   configuration agreement, default-disabled behavior, and `oc2_status` logic
   with an in-process test harness.
7. A separate offline subprocess test launches the MCP server over stdio and
   verifies JSON-RPC `initialize`, `notifications/initialized`, `tools/list`,
   and `tools/call`, checks that stdout contains protocol messages only, and
   checks safe termination on malformed input.

## Failure behavior

Any unknown selection, duplicate declaration, unsupported field, plugin pin or
hash mismatch, unapproved MCP command/tool, malformed protocol request, bundle
mismatch, or existing Runtime stops the operation without fallback. Errors must
not include environment values, credential contents, or plugin source contents.

## Acceptance boundaries

Offline acceptance requires the existing sandbox regression suite, focused
plugin/MCP tests, Python syntax checks, and `git diff --check` to pass. Tests
must verify that the normal configuration remains disabled and that no network,
Sandbox CLI, external API, or model is invoked.

Offline acceptance does not establish that OpenCode loads the plugin, exposes
the MCP tool in its runtime, or safely handles an actual invocation. Those
checks remain `NOT_VERIFIED` and require separate authorization and a bounded
live acceptance procedure. The initial acceptance uses Superpowers as the sole
external Plugin candidate, `oc2_status` as the sole MCP tool, and does not add
an independent review stage.
