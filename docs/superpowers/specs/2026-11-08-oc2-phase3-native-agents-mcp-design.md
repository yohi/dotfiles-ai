# OC2 Phase 3 Native Agents and MCP Design Specification

## Purpose

Define the correctness and security contract for adding explicitly selected
Native Agents, Plugin candidates, and MCP candidates to the OC2 Guest runtime.
This document is the repository-resident design authority for the
implementation plan at
[`../plans/2026-11-08-oc2-phase3-native-agents-mcp.md`](../plans/2026-11-08-oc2-phase3-native-agents-mcp.md).

## Scope and architecture

- `apm.yml` remains the source of truth for OC2 assets and Native declarations.
- `sandbox/scripts/oc2_native.py` parses those declarations into a typed,
  deterministic `NativeConfig`.
- `sandbox/scripts/oc2_agent_native.py` owns the standard-library-only payload
  schema, shared identifiers, and validation contracts used by Host and Guest.
- The asset manifest carries the validated native payload and its source APM
  digest. The OpenCode v2 exporter emits the same validated Agent map.
- The Guest validates the payload and confirms that the configuration Agent
  map matches it. The existing asset SHA-256 remains part of Runtime Identity.

## Normative requirements

### Native Agents

- The only Agent IDs are `hephaestus` and `oracle`.
- `hephaestus` is `primary`; `oracle` is `subagent`.
- Both use only `openai/gpt-6-luna`, which must remain enabled in the OpenAI
  APM whitelist.
- Do not set a default Agent, model fallback, category routing, or automatic
  subagent launch.
- `oracle` is read-only. Deny edit, shell, delegation/task, web, and MCP
  permissions. Preserve the fixed permissions defined by the shared payload
  schema.

### Plugins and MCP

- The APM extension contract declares fixed disabled candidates:
  `x-oc2-plugins: {enabled: false, allowlist: [superpowers]}` and
  `x-oc2-mcp: {enabled: false, servers: [oc2-status]}`.
- Candidate declarations do not activate or select a component. Normal output
  keeps Plugins disabled with an empty allowlist and MCP disabled with an empty
  server set.
- Verification-only selection may enable only the fixed `superpowers` Plugin
  and `oc2-status` MCP candidates. No other IDs or enabled states are allowed.
- Unknown fields, duplicate declarations, incomplete OC2 extension sets, and
  unapproved or enabled components fail closed.

### Assets, identity, and failure behavior

- Asset source paths must be unique, safe, and members of the fixed
  `ASSET_SOURCES` allowlist.
- The APM source digest used by configuration export must match the digest
  recorded in the native asset manifest.
- The Guest rejects a native payload/config mismatch and must not overwrite an
  existing Runtime whose receipt, assets, or identity do not match.
- Preserve OAuth, Cloudflare Gateway, Guest Proxy, mountless isolation,
  credential isolation, manifest/SHA-256 checks, and no-overwrite behavior.
- Runtime verification helpers are transferred to a content-addressed Guest
  directory and individually SHA-256 checked before use.

## Acceptance criteria

1. Valid APM declarations produce exactly the fixed Agent map and disabled
   Plugin/MCP defaults.
2. Verification-only mode selects exactly the approved Plugin and MCP
   candidates; missing, unknown, duplicate, or enabled declarations are
   rejected.
3. Host and Guest validate the same native payload contract, and Guest Agent
   configuration must equal the verified payload.
4. Any source digest mismatch, unsafe asset path, or existing Runtime mismatch
   stops processing without overwriting existing content.
5. Automated tests cover valid, malformed, disallowed, and mismatch cases
   without contacting a Sandbox or external service.
