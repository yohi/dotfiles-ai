# OC2 One-Command Launcher and OpenAI OAuth Acceptance History

This record documents the OC2 One-Command Launcher development and the bounded
OpenAI OAuth live acceptance through the successful `gpt-6-luna` response. It
supplements the earlier [implementation and acceptance record](2026-11-07-one-command-launcher-implementation-acceptance-record.md),
which contains the Phase 1 workspace-transfer and TUI history.

## Executive Summary

Phase 1 established the mountless One-Command Launcher, safe workspace transfer,
pinned OpenCode v2.2.5 kit, OAuth bootstrap, and TUI acceptance. That acceptance
did not include a real model request.

Phase 2 addressed an OpenAI OAuth failure by moving proxy environment acquisition
from the Host launcher into a Guest Python wrapper, then allowing the observed
`gateway.docker.internal` value as an exact `NO_PROXY` entry. The final bounded
live run used Docker Sandboxes v0.51.0, completed one model request to
`openai/gpt-6-luna`, received `OK`, observed `forward` traffic to
`chatgpt.com:443`, and stopped the new Sandbox.

The Phase 2 live outcome is `PROXY_AND_OAUTH_ACCEPTANCE_PASS`. Policy Log did not
report a blocked-request count; that value remains unknown and is not interpreted
as zero.

## Evidence Provenance

- Phase 1 events, earlier OAuth failures, and the 206/207/209 offline test totals
  are recorded from the corresponding task reports. They were not rerun during
  this documentation and Git task.
- Phase 2 R2 runtime observations are from the preceding authorized live
  acceptance in this work session. Proxy values and credentials were not retained
  in this document.
- The target Worktree, branch, starting HEAD, changed-file list, and remote branch
  SHA were checked read-only during this documentation task.

## Project Goal and Scope

OC2 provides a one-command path to prepare an isolated Docker Sandbox, transfer a
verified workspace snapshot, prepare the pinned OpenCode v2 runtime, bootstrap
OAuth credentials inside the Guest, and start the standalone TUI. The Host's
credentials and workspace mounts remain outside the Guest trust boundary.

The implementation history is split into two acceptance phases:

- **Phase 1:** launcher, mountless workspace transfer, CLI kit, OAuth bootstrap,
  and practical TUI acceptance. No model inference was tested.
- **Phase 2:** Guest-origin Proxy handoff, exact `NO_PROXY` compatibility, and one
  real OpenAI model request.

This record does not claim acceptance for other Providers, Cloudflare AI Gateway
inference, long-running sessions, or Phase 3 agent features.

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

## Final Live Acceptance

The following runtime results were observed in the one authorized live run:

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

## Security and Isolation Constraints

- No OAuth re-login, Host credential update, or manual credential import was
  performed.
- No Proxy URL, OAuth token, Authorization header, or credential value was
  recorded.
- The model request was submitted once with the exact prompt `Reply with
  exactly: OK`; no manual retry or model switch followed.
- The newly created Sandbox was stopped, not deleted. Other Sandboxes were not
  changed.
- No source edit, Commit, Push, or other Git write occurred during the live
  acceptance.

## Evidence Status and Remaining Risks

### Proven for this acceptance

- The reported 209-test offline suite passed before the live acceptance.
- The Guest-origin wrapper accepted the Guest Proxy configuration and the
  standalone TUI started.
- The model returned `OK` for the single OpenAI request.
- Policy Log recorded `forward` traffic for `chatgpt.com:443` with aggregate
  connection count 2.
- The Sandbox ended in `stopped` state.

### Unknown or not verified

- Policy Log exposed no blocked-count field. The blocked-request count is
  **unknown**, not zero.
- The process scan did not independently verify Proxy variables for every
  matching OpenCode process.
- Other Providers, Cloudflare AI Gateway inference, long-running sessions, and
  Phase 3 agent features were not tested.
- Ruff and `markdownlint-cli2` were unavailable and were not installed.
- A Python no-excuse audit reported five existing findings: an `if`/`elif`
  variant chain and a broad exception in `oc2.py`, plus oversized-module
  findings for the launcher and two test files. These findings were not assessed
  or modified in this bounded history-and-commit task.

## Final Verdict and Task Closure

The bounded Phase 2 acceptance verdict is
`PROXY_AND_OAUTH_ACCEPTANCE_PASS`: the selected OpenAI model returned a response
and Policy Log recorded the expected `forward` route. This does not imply a
known-zero blocked count or acceptance of untested Providers and later phases.

This record supplements the Phase 1 acceptance document linked above. No new
Sandbox run, model request, credential change, independent review, or follow-up
task is authorized by this record.
