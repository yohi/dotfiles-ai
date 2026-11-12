# OC2 One-Command Launcher — Implementation History & Acceptance Record

This is a historical acceptance record, not a replacement for the current
[Sandbox guide](../../sandbox/README.md) or the implementation. The objective
was to prepare a safe workspace snapshot, build a pinned CLI kit, create a
mountless Sandbox, transfer and verify the snapshot, bootstrap OAuth, and launch
the OpenCode V2 TUI while protecting host credentials and isolation.

## Implementation at acceptance

- The host launcher builds a snapshot and manifest before creating a mountless
  Sandbox. It copies the snapshot into a random Guest destination and checks
  each transferred file against its manifest SHA-256.
- The `dotfiles-ai/workspace-safe-transfer/r1` profile is selected only for the
  explicitly matched repository origin. It excludes root `apm.yml`, specific
  sensitive or local files, generated artifacts, and specified symlink adapter
  trees. General exclusions also cover `.git`, credentials and local agent
  configuration. See `sandbox/scripts/oc2_workspace.py` for the exact rules.
  The Guest cannot edit or return `apm.yml`, including a newly created one.
- The CLI mixin contains the verified official OpenCode v2.2.5 Linux x64 release
  executable at `/opt/oc2/bin/opencode`, outside Guest HOME. The Host verifies
  the release asset's pinned size and SHA-256 before staging it. The kit build
  does not install from npm. The launcher verifies the Guest CLI version.
- The credential mixin retains the existing proxy-managed handoff. The isolated
  Runtime uses per-session HOME, XDG paths and database identity. The existing
  OAuth helper checks identity, controls import, verifies readback, and cleans
  up the temporary bootstrap policy before the standalone TUI starts.
- Project configuration auto-loading is disabled for the Guest TUI. The
  launcher requires the explicit external-inference acknowledgement when the
  generated configuration selects an external provider.
- Destination validation runs a Guest Python check through `sbx exec` before
  transfer. Sandbox shutdown during acceptance was an operator action; the
  normal launcher does not imply automatic deletion of a Sandbox.

## Implementation and acceptance history

### Workspace transfer

Clone-mode experiments exposed a mismatch between the intended safety boundary
and the files or project configuration visible to the Guest. The launcher was
changed to transfer a checked snapshot into a mountless Sandbox instead.
Snapshot exclusions, content checks, a deterministic manifest, and Guest-side
SHA-256 readback were exercised in offline and live acceptance. The repository
profile's precise exclusions and its `apm.yml` limitation are implementation
choices, not assertions that excluded contents are safe.

### CLI kit and HOME permissions

The shell workload lacked `npm`; a first runtime install failed. A subsequent
Node-based kit build could not resolve the npm registry from BuildKit. The
implementation moved to a locally staged, verified official release asset.
An early kit copied the CLI beneath Guest HOME. Live diagnostics observed
`mkdir /home/agent/.cache: permission denied`: HOME was owned by root and was
not writable by UID 1000. The precise layer that set that ownership was not
established. Relocating the CLI to `/opt/oc2/bin/opencode` was followed by a
live kit acceptance: Guest UID/GID was 1000:1000, HOME was writable and the
v2.2.5 version probe succeeded. Kit build and runtime validation were separate
from the later one-command run.

### Destination check and exit-code change

An initial one-command run stopped with `workspace destination already exists
or could not be checked`. The launcher had received a successful command result
whose stripped stdout was not `missing`; the original stdout was not retained.
A separate equivalent probe returned `MISSING_EXACT`, but did not inspect the
original random destination. A later run stopped with
`DESTINATION_CHECK_UNEXPECTED_OUTPUT`. Distinguishing fixed error messages alone
did not establish or solve the cause of the anomalous stdout.

The implementation then replaced stdout comparison with a direct Guest Python
check. Parent components are opened with `O_DIRECTORY | O_NOFOLLOW`; the final
component is checked without following a symlink. The status contract is:

| Status | Interpretation |
| --- | --- |
| 0 | Missing confirmed by the Guest check |
| 10 | Destination exists, including a symlink |
| 11 | Check indeterminate |
| 125, 127 or other | Command execution failure |

Timeout is handled separately. The updated offline suite reported 199 tests
passing. The subsequent live run passed this check and reached workspace
transfer. The underlying cause of the earlier anomalous stdout remains unknown.

### One-command run and TUI follow-up

The post-change one-command run passed workspace safety, kit build, mountless
creation, destination check, snapshot transfer and Guest SHA-256 readback.
OAuth bootstrap, import, readback and temporary policy cleanup recorded PASS;
the `oc2` process exited 0 and the Sandbox was stopped. It used OpenCode v2.2.5.
That run was classified `ONE_COMMAND_E2E_INCOMPLETE` because TUI screen
interaction had not been reliably observed.

An automated TUI follow-up captured identical initial, Ctrl+P and Escape screen
hashes, which did not prove screen transitions. The previous random Guest
workspace path was absent from the original terminal evidence. One Guest
candidate subsequently matched the current Host's non-secret README and Makefile
hashes, with `.git` and `apm.yml` absent. The Human Owner approved adopting it
only for the TUI test; historical snapshot identity was not established.

Host tmux connection and input were confirmed, but an automated launch-command
send failed. The workflow changed to a Human Owner manually launching the TUI.
Because the stopped Sandbox's current Guest policy could not be checked before
starting it, the owner approved starting it for a read-only policy check first.
Guest configuration then matched the verified Host export's SHA-256 and the
normal policy was checked. The owner launched the TUI manually in a separate
session and directly reported the following results:

| Human-observed item | Result |
| --- | --- |
| Normal initial screen | PASS |
| Model display | PASS |
| Ctrl+P command palette | PASS |
| Escape restores normal screen | PASS |
| TUI exit | PASS |

The final TUI acceptance was `TUI_ACCEPTANCE_PASS`; the Sandbox was stopped
with its identity unchanged. The TUI-specific exit code was not observed.

## Scope of proof and limitations

| Status | Evidence and boundary |
| --- | --- |
| PROVEN | One-command run reached verified workspace transfer and OAuth readback; `oc2` exited 0. |
| PROVEN | The owner observed TUI display, model, palette, Escape and exit in a separate session. |
| NOT_OBSERVED | TUI-specific exit code and background inference activity. |
| NOT_TESTED | Actual LLM inference; no LLM prompt was intentionally sent. |
| KNOWN_LIMITATION | The check-to-`sbx cp` TOCTOU race is not eliminated. |
| KNOWN_LIMITATION | Guest workspace historical snapshot identity was not established. |
| KNOWN_LIMITATION | All TUI interactions were not observed in the same one-command session. |

Taken together, the live evidence and Human Owner observation met the practical
acceptance conditions through the normal TUI. They do not establish inference
correctness, eliminate the transfer race, or prove uninterrupted observation of
all stages in a single session.

## Protected local evidence inventory

The following local evidence directory names were present at inventory time;
their directories were mode `0700` and the listed files were mode `0600`.
These are local, temporary artifacts, not repository files or portable links.
Terminal recordings may contain sensitive data and must not be committed.

| Local evidence directory basename | Recorded file | SHA-256 |
| --- | --- | --- |
| `oc2-onecmd-r3-evidence-s3kso8kn` | `metadata.json` | `57c24eed08969c1413d6654fe40fac3a92f99ae6d016d8fdc03e6714fb142897` |
| `oc2-destination-probe-oy_2ahyz` | `metadata.json` | `1b8df3c16323f902042782d870fbc769d369b4635e5c62393d44fb18229d471a` |
| `oc2-onecmd-r4-evidence-4in5_l8h` | `metadata.json` | `834dac16b180f47e9e62ac6134af1fc0877fd626f2de7e6c89a42b219dd6e90f` |
| `oc2-onecmd-r5-evidence-e76bgghh` | `metadata.json` | `8085e24e87b724f52dab8616992b718bdcb580944bb6901fdf9a551ccea9233e` |
| `oc2-tui-bounded-r2-3krtss5a` | `human-acceptance-da75ae35107d.json` | `b8807d3d60f967c5e4898940f4763710be327747f1bc53f67302526d64e61822` |

The TUI acceptance recorded Sandbox `oc2-v2-onecmd-e2e-r3`, ID
`8798cc20-46ff-47fe-8af0-7ab62ba6b539`, with final state `stopped`.
