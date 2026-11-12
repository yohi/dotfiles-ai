# OC2 One-Command Launcher and Cloudflare Acceptance History

This record documents OC2 One-Command Launcher development from the initial
OpenAI OAuth failure through Cloudflare Credential provisioning and the reported
OpenAI and Cloudflare model acceptance. It supplements the earlier
[implementation and acceptance record](2026-11-07-one-command-launcher-implementation-acceptance-record.md),
which contains the Phase 1 workspace-transfer and TUI history.

## Executive Summary

Phase 1 established the mountless One-Command Launcher, safe workspace transfer,
pinned OpenCode v2.2.5 kit, OAuth bootstrap, and TUI acceptance. That acceptance
did not include a real model request.

Phase 2 addressed an OpenAI OAuth failure by moving Proxy environment acquisition
into a Guest Python wrapper and allowing the observed `gateway.docker.internal`
as an exact `NO_PROXY` entry. A later integration added sandbox-scoped Cloudflare
Credential provisioning and JSON Secret-list parsing. The Human Owner reported
that a new One-Command run authenticated to both OpenAI and Cloudflare Custom,
received successful model responses, observed `forward` traffic, and stopped the
Sandbox.

The Human Owner-reported final outcome is
`OC2_CLOUDFLARE_ONE_COMMAND_ACCEPTANCE_PASS`. The earlier OpenAI R2 Policy Log
did not report blocked counts; the final Cloudflare run separately reported an
empty blocked list.

## Evidence Provenance

- Phase 1 events, earlier OAuth failures, prior live runs, and the 206/207/209/232
  offline test totals are recorded from their corresponding task reports. The
  232-test suite was run for the JSON parser change; tests were not rerun during
  this documentation and Git task.
- The `oc2-v2-new4` Credential and TTY history and final `oc2-cf-accept-r1`
  acceptance results below are Human Owner-reported live evidence. No Sandbox or
  Credential operation was repeated for this document.
- The target Worktree, branch, starting HEAD `741dff2355c1af7c593f1cafd1751164d447df52`,
  changed-file list, and initial remote branch SHA were checked read-only during
  this documentation task.

## Project Goal and Scope

OC2 provides a one-command path to prepare an isolated Docker Sandbox, transfer a
verified workspace snapshot, prepare the pinned OpenCode v2 runtime, bootstrap
OAuth credentials inside the Guest, and start the standalone TUI. The Host's
credentials and workspace mounts remain outside the Guest trust boundary.

The implementation history is split into the launcher foundation, OpenAI OAuth
acceptance, and Cloudflare Credential integration:

- **Phase 1:** launcher, mountless workspace transfer, CLI kit, OAuth bootstrap,
  and practical TUI acceptance. No model inference was tested.
- **Phase 2:** Guest-origin Proxy handoff, exact `NO_PROXY` compatibility, and a
  real OpenAI model request.
- **Cloudflare integration:** sandbox-scoped Credential provisioning, JSON Secret
  listing, and a reported One-Command OpenAI plus Cloudflare acceptance.

This record does not claim acceptance for other Providers, Dynamic Routes,
long-running sessions, or Phase 3 agent features.

## Development Timeline

### Phase 1 — One-Command Launcher

The launcher was developed to create a mountless shell Sandbox, stage a verified
workspace snapshot, install the pinned official OpenCode v2.2.5 executable, use
an isolated Runtime HOME/XDG layout, execute the OAuth helper, and start the
standalone TUI. The `dotfiles-ai/workspace-safe-transfer/r1` profile excludes
`.git`, credentials, and configured local-only files; `apm.yml` is not transferred
or modifiable by the Guest.

Phase 1's transfer, kit, OAuth bootstrap, and TUI evidence is described in the
[earlier acceptance record](2026-11-07-one-command-launcher-implementation-acceptance-record.md).
Its TUI acceptance and this Phase 2 model acceptance are distinct results.

### Phase 2 — Initial OpenAI OAuth Failure

The `oc2-v2-new` and `oc2-v2-new2` Sandboxes returned:

```text
Could not parse your authentication token.
Please try signing in again.
```

OAuth Sentinel registration and readback had passed, while the real model request
failed. Policy Log showed `transparent` traffic to `chatgpt.com:443`. This
established that successful credential registration alone did not establish
successful OpenAI authentication or the desired Proxy route.

### Phase 2 — Active Launcher Identity

The `oc2` executable resolved through `~/.local/bin/oc2` to the script in the
specified target Worktree:

```text
.worktrees/feature-oc2-host-launcher-apm-ssot-20261103/sandbox/scripts/oc2.py
```

The active branch was `feature/oc2-one-command-e2e-acceptance-20261107` at
`3db76a99c54f3bbcc774ff7b21e74080c24d30db`. Inspecting another Worktree's
launcher would not have established the behavior of the executable actually
invoked.

### Phase 2 — Proxy Handoff R1 and Preflight Block

The first handoff change used an allowlist for `HTTP_PROXY`, `HTTPS_PROXY`, and
`NO_PROXY`, while preserving the `env -i` isolation model. Its 206 offline tests,
Python compilation, and diff check passed.

Preflight then identified that `launch()` runs on the Host and called
`proxy_environment(os.environ)`. The apparent allowlist therefore read Host
environment values rather than the Guest-provided Proxy environment. The live
acceptance stopped at `PREFLIGHT_BLOCKED`; no Sandbox was launched in that
attempt.

### Phase 2 — Guest-Origin Proxy Handoff R2

The Host-side Proxy lookup was removed. A shared `GUEST_EXEC_WRAPPER` now runs in
the Guest, reads the Guest's `os.environ`, validates the Proxy values, constructs
a child environment from fixed Runtime settings plus only validated Proxy
variables, and replaces itself with the OAuth helper or TUI process.

The wrapper preserves these fail-closed conditions:

- HTTPS Proxy must be present.
- Only the uppercase and lowercase forms of the three approved variable names
  are considered; conflicting case variants are rejected.
- Invalid Proxy URLs and URLs containing credentials are rejected.
- Unapproved `NO_PROXY` entries are rejected.
- Arbitrary Guest variables and Host Proxy values are not inherited by the child.
- OAuth Helper and TUI use the same wrapper.

The reported R2 offline suite result was 207 tests passing, with Python
compilation and `git diff --check` passing. No Sandbox or model inference was run
as part of that source-fix task.

### Phase 2 — `NO_PROXY` Exact-Match Compatibility

The `oc2-v2-new3` Sandbox stopped with `OC2_PROXY_STOP: unsafe NO_PROXY entries`.
The Guest's `NO_PROXY` was reported to contain three loopback entries and the
exact hostname `gateway.docker.internal`; the existing allowlist did not include
that hostname.

The wrapper now allows `gateway.docker.internal` by exact match and no longer
strips leading dots. It continues to reject `.gateway.docker.internal`,
subdomains, wildcard entries, `*`, `chatgpt.com`, and `openai.com`. The reported
offline suite result was 209 tests passing; `py_compile` and
`git diff --check` passed. Ruff was not run because it was not installed.

### OpenAI OAuth Live Acceptance R2

The following runtime results were observed in the authorized OpenAI run:

| Check | Result |
| --- | --- |
| Sandbox | `oc2-v2-proxy-verify-r2` |
| Docker Sandboxes | v0.51.0 |
| OpenCode | v2.2.5 |
| Sandbox configuration | Mountless shell Sandbox; no workspace bind mount |
| CLI kit | Built once from the verified pinned artifact |
| Workspace | Safe-transfer profile selected; launcher reached `OC2_READY` after the transfer path completed |
| Guest Proxy variables | `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` were present in the inspected OpenCode process; values were not displayed |
| `NO_PROXY` validation | Guest wrapper passed validation |
| OAuth Import / Readback | PASS in the reported acceptance; helper returned successfully before TUI launch |
| Model | `openai/gpt-6-luna` |
| Manual model requests | One |
| Model response | `OK` |
| Policy Log for `chatgpt.com:443` | `forward`, aggregate connection count 2 |
| Sandbox shutdown | `sbx stop` succeeded; read-only inspection reported `stopped` |

The OAuth helper's initial database, Sentinel, and database-path checks were
visible as PASS. Its later stage output was not retained in the final terminal
capture after the TUI switched screens. The helper call was synchronous; the
launcher proceeded to the TUI only after the helper process returned success.
The model response and `forward` Policy Log record independently establish a
successful OpenAI request on the accepted route.

The read-only process check found two processes matching the pinned OpenCode
executable. It reported the three uppercase Proxy variable names present for the
first matching process; it did not expose Proxy values or verify each matching
process independently. The successful model request and the shared wrapper path
provide the end-to-end evidence for this run.

### Cloudflare Stage A — Authentication Failure on `oc2-v2-new4`

The Human Owner reported that Cloudflare Custom requests from `oc2-v2-new4`
returned `Unauthorized`, while the existing OpenAI route remained successful.
Before the Cloudflare Credential was registered, Policy Log showed:

| Destination | Proxy type | Count |
| --- | --- | ---: |
| `gateway.ai.cloudflare.com:443` | `forward-bypass` | 1 |
| `chatgpt.com:443` | `forward` | 2 |

The initial evidence established that an egress route existed but did not apply
the Cloudflare Credential. The precise authentication failure layer was not
initially known.

### Cloudflare Stage B — Credential Scope Diagnosis

Read-only Secret listings showed Cloudflare credentials scoped to
`oc2-phase2-cloudflare-live-r1` and `oc2-phase2-mixin-probe-r1`, but none scoped
to `oc2-v2-new4` and none at Global scope. The Global OpenAI OAuth Credential
was already present. This indicated that the target Sandbox lacked the
Cloudflare service Secret required by the optional Mixin binding.

### Cloudflare Stage C — Existing Sandbox Credential Registration

The Human Owner registered the service Credential only for the affected Sandbox:

```bash
sbx secret set cloudflare-ai-gateway --sandbox oc2-v2-new4
```

Secret listing confirmed the Sandbox-scoped registration. No Global Secret was
created or changed. A subsequent normal OC2 invocation correctly refused to
reuse the existing Sandbox:

```text
OC2_STOP: Sandbox name already exists; refusing to reuse or rebuild it
```

That stop was existing-Sandbox protection, not a Credential failure.

### Cloudflare Stage D — TTY Reattach and Existing Sandbox Acceptance

An earlier Python heredoc test reached `error: inspect exec: context deadline
exceeded`. The working hypothesis was that Host Python consumed stdin for the
heredoc rather than the controlling terminal. A TTY test explicitly opened
`/dev/tty` and passed it to `sbx exec -it`:

```text
OC2_TTY_STDIN_OK True True
TTY_TEST_EXIT= 0
```

The Human Owner then reported successful Guest Wrapper TUI reattachment, exit
code 0, Cloudflare `forward` traffic with count 2, and an `OK` response from
DeepSeek V4.1 Flash (Ollama Cloud). The Sandbox was stopped. The previous
`forward-bypass` event remained in the historical log as a pre-registration
record.

This verified Cloudflare Credential Injection on an existing Sandbox. It still
required a separate Secret-registration operation and did not satisfy the
One-Command provisioning goal.

### Cloudflare Stage E — Credential Provisioning Integration R1

The OC2 launch path was extended to check Cloudflare Credential availability
after creating a new Mountless Sandbox and before workspace transfer or TUI
launch. When neither a Sandbox-scoped nor Global Secret was available, OC2
required an interactive Host terminal and delegated value entry to:

```bash
sbx secret set cloudflare-ai-gateway --sandbox NAME
```

The flow verifies the Sandbox scope after registration. Existing Global Secrets
are checked read-only; OC2 never creates or changes a Global Secret. Secret
values are not read by OC2, included in command arguments, or written to logs.

The default OpenAI mode hides the Cloudflare Provider from the temporary Runtime
configuration. `--use-cloudflare-ai-gateway` explicitly exposes the Provider and
requires its Credential; a Cloudflare default model also requires it. A failed
TTY check, Secret operation, or readback stops before workspace transfer and TUI
startup.

The reported offline suite result for this integration was 229 tests passing.
No Sandbox operation or live Secret registration was performed for the source
integration task.

### Cloudflare Stage F — JSON Secret Listing Compatibility Failure

The Human Owner reported that the One-Command attempt on `oc2-cf-next` passed the
OpenCode v2.2.5 artifact verification, built its kit, and created a Mountless
Sandbox, then stopped with:

```text
OC2_STOP: Cloudflare credential listing format is unsupported
```

Both Sandbox and Global Secret list commands had returned a successful empty
JSON object:

```json
{"secrets": []}
```

This was a valid unregistered state, but the R1 parser expected a text-table
header. The Credential prompt, OAuth Bootstrap, TUI, and inference did not run
after this parser failure.

### Cloudflare Stage G — JSON Parser Compatibility Fix R1

Secret enumeration now uses Docker Sandboxes v0.51.0 JSON listing commands for
the target Sandbox and Global scopes, filtered to the `cloudflare-ai-gateway`
service. A valid empty `secrets` array is treated as unregistered; command
failure, malformed JSON, missing or incorrectly typed fields, unknown entry
structures, unexpected Secret type, and Scope mismatch fail closed.

The registered entry schema was verified through a read-only JSON listing of
`oc2-v2-new4`:

```text
root: object; key: secrets; type: array
entry keys: name, scope, secret, type
entry field types: string
name: cloudflare-ai-gateway
scope: oc2-v2-new4
type: service
```

The `secret` field value was not printed or stored. Docker documentation states
that service Secret listings redact values. The parser uses only the field's
presence/type and the non-secret name, scope, and type metadata.

The reported post-fix offline suite result was 232 tests passing, with Python
compilation and `git diff --check` passing. No Secret was changed for this
parser-fix task.

### Cloudflare Stage H — Final One-Command Acceptance

The Human Owner reported a successful run of:

```bash
oc2 --sandbox oc2-cf-accept-r1 \
  --use-cloudflare-ai-gateway \
  --allow-paid-inference
```

The reported observations were:

| Check | Result |
| --- | --- |
| Docker Sandboxes | v0.51.0 |
| OpenCode | v2.2.5 |
| Mountless Sandbox creation and artifact verification | PASS |
| Sandbox-scoped Cloudflare Credential prompt and Readback | PASS |
| OpenAI OAuth Import / Readback | PASS |
| OpenCode TUI | PASS |
| `gateway.ai.cloudflare.com:443` | `forward`, count 1 |
| `chatgpt.com:443` | `forward`, count 2 |
| Policy Log blocked list | `[]` reported |
| OpenAI model response | PASS, Owner-reported |
| Cloudflare Custom model response | PASS, Owner-reported |
| Sandbox stop | PASS |

The final report did not retain exact model identifiers or response bodies for
both model responses. This record therefore records provider-level success from
the Owner report without inferring exact model names or output text.

The Human Owner-reported verdict was
`OC2_CLOUDFLARE_ONE_COMMAND_ACCEPTANCE_PASS`. The live report distinguishes this
empty blocked list from the earlier OpenAI R2 Policy Log, whose blocked count
was unavailable.

## Security and Isolation Constraints

- No OAuth re-login or Host/Global Credential update was performed. Cloudflare
  values were entered through Docker's interactive CLI and scoped to the
  reported Sandbox.
- No Proxy URL, OAuth token, Authorization header, or credential value was
  recorded.
- During the OpenAI R2 acceptance, one model request used the exact prompt
  `Reply with exactly: OK`; no manual retry or model switch followed.
- The newly created Sandbox was stopped, not deleted. Other Sandboxes were not
  changed.
- No source edit, Commit, Push, or other Git write occurred during the live
  acceptance.

## Evidence Status and Remaining Risks

### Offline and Live Evidence

- The final JSON parser task reported 232 offline tests passing, plus Python
  compilation and `git diff --check` passing. That suite was not rerun during this
  documentation and Commit/Push task.
- The OpenAI R2 acceptance recorded Guest Proxy variables in the inspected
  OpenCode process, `forward` traffic for `chatgpt.com:443`, a successful
  `gpt-6-luna` response, and a stopped Sandbox.
- The Human Owner reported the Cloudflare One-Command acceptance with Sandbox
  Secret Readback, OAuth Import / Readback, successful OpenAI and Cloudflare
  Custom responses, `forward` Policy Log entries, an empty blocked list, and a
  stopped Sandbox.
- The Secret JSON entry field names and types were checked using a read-only,
  value-filtered listing. Secret values were not displayed.

### Unknown or not verified

- The OpenAI R2 Policy Log exposed no blocked-count field. That run's
  blocked-request count is **unknown**, not zero. The later Cloudflare run
  separately reported an empty blocked list.
- The process scan did not independently verify Proxy variables for every
  matching OpenCode process.
- Exact model identifiers and response bodies for the final Cloudflare
  One-Command acceptance were not retained and are not inferred here.
- Providers beyond the reported OpenAI and Cloudflare Custom paths, Dynamic
  Routes, long-running sessions, and Phase 3 agent features were not tested.
- Ruff and `markdownlint-cli2` were unavailable and were not installed.
- A Python no-excuse audit on the current Worktree reported five findings:
  existing `if`/`elif` and broad-exception patterns, plus oversized-module
  findings for the launcher and two test files. Their severity was not assessed
  or addressed in this bounded Credential and JSON-parser scope.

## Final Verdict and Task Closure

The Human Owner-reported final verdict is
`OC2_CLOUDFLARE_ONE_COMMAND_ACCEPTANCE_PASS`: the Owner reported successful
OpenAI and Cloudflare Custom responses, `forward` traffic for both Gateway
destinations, an empty blocked list, and successful Sandbox shutdown. Earlier
OpenAI R2 Policy Log evidence with no blocked-count field remains separately
classified as unknown. This verdict does not imply acceptance of untested
Providers or later phases.

## Owner Decision and Task Closure

The One-Command Cloudflare credential flow and JSON Secret-list parsing are
documented as complete based on the reported acceptance and offline results.
The Credential storage fallback on headless Linux, interactive TTY requirement,
and untested Provider scope remain known constraints. No new Sandbox run, model
request, Credential operation, independent review, or follow-up task was
authorized for this documentation and Commit/Push task.
