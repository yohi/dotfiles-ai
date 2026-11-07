# OC2 Phase 3 Task A — APM Native Assets Acceptance

- **Repository:** `yohi/dotfiles-ai`
- **Branch:** `feature/oc2-phase3-apm-native-integration-20261107`
- **Base:** `05428551a242a65bf39a58921a14743a7bebcfaa`

## Outcome

Phase 3 Task A integrates the explicitly selected APM-native Rules, Command,
Skills, and theme into an isolated OpenCode v2.2.5 runtime. Offline regression
tests and the limited live acceptance both passed. This result does not certify
the remaining Phase 3 work.

## Implementation

- `apm.yml` declares the OC2 asset candidates. `oc2_assets.py` exports only the
  intersection of that declaration and the fixed source-path allowlist; malformed,
  duplicate, unknown, or traversing paths fail closed. Symlinked sources and
  detected credential signatures are rejected.
- The host transfers only the selected asset bundle and Guest verifier. The
  Guest verifies the bundle SHA-256, per-file hashes, schema, and fixed target
  paths before placing assets in a dedicated runtime. The runtime identity
  includes the asset SHA-256; an existing runtime is not overwritten.
- OpenCode receives seven instruction paths, one native command, two native
  skills, and the selected CLI theme. No APM manifest, MCP configuration,
  provider credential, custom agent, or plugin is copied.
- OpenAI OAuth, Cloudflare credential provisioning, Guest Proxy, and mountless
  isolation remain on their existing paths.

## Acceptance history

### Initial live attempt — `oc2-p3-assets-accept-r1`

The first attempt used the development `dotfiles-ai` tree as the Workspace and
was stopped by the existing credential scan:

```text
OC2_STOP: workspace file appears to contain credential material
```

The scan was not disabled. The attempt was changed to use a minimal test Git
Workspace. That run then stopped before TUI startup with:

```text
OC2_STOP: cannot establish guest asset bundle state
```

The precise cause of this specific stop was not established. In particular, the
reported `missing` stdout and zero exit status alone do not reproduce the failure
in the checked-in string comparison.

### Asset State Probe Fix R1

Asset Bundle and Verifier file-state checks use `Runner.destination_status()`
instead of stdout labels:

| Exit code | State | Action |
| --- | --- | --- |
| `0` | Absent | Transfer the file |
| `10` | Regular file | Reuse only after SHA-256 matches |
| `12` | Unsafe (including symlink, directory, or special file) | Stop |
| Other | Unknown or failed probe | Stop |

Timeouts and command execution failures also stop. The check uses no stdout or
stderr text as a state signal. The adjacent Asset SHA-256 and Guest manifest
checks remain enabled. The same probe is used for asset files in the staging
path; the separate directory probe for the configuration bundle is unchanged.

### Offline verification

- `python3 -m unittest discover -s sandbox/tests -p 'test_*.py'` — **248 tests passed**.
- `python3 -m py_compile sandbox/scripts/oc2.py` — **passed**.
- `git diff --check` — **passed**.

Coverage includes absent and reusable files, SHA mismatch, unsafe file types,
unknown exit codes, timeout/command errors, stdout/stderr notification
independence, Guest asset installation, and the existing runtime verification
path.

### Final live acceptance — `oc2-p3-assets-accept-r2`

- **Docker Sandboxes:** `v0.51.0`
- **OpenCode:** `v2.2.5`
- **Runtime identity:** `6bd7a5dabe4bf0e2`

| Check | Result |
| --- | --- |
| New mountless Sandbox and OpenCode artifact verification | PASS |
| Asset Bundle and Verifier transfer; Guest asset verification | PASS |
| Dedicated Runtime preparation | PASS |
| Seven Rules placed and seven `instructions` entries read back | PASS |
| `/build-skill` recognized in TUI (Owner observation) | PASS |
| Two Skills and theme configuration placed | PASS |
| OpenAI OAuth readback | PASS |
| Sandbox stopped | PASS |
| Network policy log (`allowed`, `blocked`) | Empty |

Guest output:

```text
OC2_ASSETS_VERIFIED: rules=7 commands=1 skills=2 theme=1 custom_agents=0 routing=none
OC2_RUNTIME_PREPARED: /home/agent/workspace/oc2/runtime/6bd7a5dabe4bf0e2
OC2_RUNTIME_VERSION: 2.2.5
```

Guest readback reported `INSTRUCTIONS_COUNT: 7`,
`THEME_CONFIG_PRESENT: True`, and `OC2_PHASE3_ASSET_READBACK_PASS`.
No model inference was run during this acceptance.

## Remaining risks and unverified scope

- The two Skills were placed but not loaded or invoked in the live runtime.
- Visual theme application was not checked.
- Acceptance of the OC2-only declaration by the APM CLI was not tested.
- Native Agent integration and MCP loading or invocation were not tested and are
  outside Task A.
- The file-state probe and `sbx cp` are separate operations. A TOCTOU race
  remains between the absent-state check and transfer; post-transfer SHA-256
  verification detects content mismatch but does not make those operations
  atomic.

The limited Task A acceptance must not be interpreted as a Phase 3-wide pass.
