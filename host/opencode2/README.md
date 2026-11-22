# Host OpenCode V1/V2 coexistence

Ubuntu/Linux **Host** installation of OpenCode V2, separate from the existing
V1 opencode command and the sandbox/ OC2 runtime. This is an opt-in setup.
None of make setup, make sync-mcp, apm install or the default OpenCode setup
changes are required or invoked.

## Coexistence contract

| Item | Existing V1 | Host V2 |
| --- | --- | --- |
| CLI | opencode (unchanged) | ~/.local/bin/opencode2 |
| Installed package | existing V1 | @opencode/cli@2.3.2 (pinned local npm prefix) |
| Config | ~/.config/opencode | ~/.config/opencode-v2/opencode |
| Data and auth DB | existing XDG data home | ~/.local/share/opencode-v2/opencode |
| Cache and state | existing XDG directories | ~/.cache/opencode-v2 and ~/.local/state/opencode-v2 |
| Service | existing | --standalone private server per invocation |
| Project config | existing | disabled by default, explicit opt-in |

apm.yml remains the SSOT for **existing V1/OC2** flows; Host V2 starts
with a separate minimal config. The optional APM Host sync below creates
a separate APM deployment snapshot, links selected asset directories into
Host V2, and adds **disabled-by-default** APM MCP declarations. Neither V1
nor sandbox/ is updated. No credentials are copied from V1 to V2.


## Microsoft APM (Host V2 only, opt-in)

Microsoft APM **v0.37.0 or newer** is required. The lockfile's
`apm_version: 0.31.0` is a previous generation marker, not necessarily
the installed APM CLI version. Install/upgrade APM separately using its
current package manager, and verify `apm --version`. No APM upgrade is
performed automatically.

```bash
python3 -m unittest discover -s tests -p 'test_host_v2_apm.py' -v
python3 host/opencode2/sync_apm.py --check  # read-only, validates normalized manifest
python3 host/opencode2/sync_apm.py --apply  # explicit APM install/compile + apply
opencode2 mcp list
```

- `--apply` parses the existing `apm.yml` (including YAML
  anchors) but writes only `dependencies.apm`, `dependencies.mcp`,
  package identity, and the OpenCode target to a temporary **anchor-free**
  manifest. It also copies regular `.apm/instructions/*.instructions.md`
  sources without following symlinks. The original SSOT remains unchanged.
- `apm install --root <private stage> --target opencode` and
  `apm compile --root <private stage> --target opencode` run **with cwd
  set to the private stage**, because `--root` redirects writes but does
  not change input manifest discovery. Outputs stay under
  `~/.local/share/opencode-v2/apm-host-snapshots/`.
  APM may use its normal shared cache/receipt infrastructure, but no
  V1 OpenCode files or source `apm.lock.yaml` are deliberately changed.
- The source snapshot's `.agents/skills`, `.opencode/commands`, and
  compiled `AGENTS.md`, where present, are symlinked **only** into
  `~/.config/opencode-v2/opencode/`. Existing unrelated files/links cause
  a stop rather than being overwritten.
- The APM-generated `opencode.json` must contain native V2
  `mcp.servers`. Every imported server has `disabled: true`, even
  if APM enables it in its generated output. No MCP process is launched
  during the sync. Inspect each server and its credential/permission scope
  before any separate manual enablement.
- The private `opencode.json` preserves other keys, including authentication
  and provider settings. Subsequent syncs refuse to overwrite MCP settings
  manually changed since the previous sync.
- Failures in APM installation, compilation or validation stop before the
  V2 active settings are applied. The snapshot stage is discarded on failure;
  no rollback, cleanup or removal of prior snapshots is automatic.
- APM v0.37.0 real dependency-resolution and Host V2 live MCP/skill
  recognition have not been verified by the offline mock tests. Treat the
  first `--apply` as live acceptance. The actual APM manifest may require
  explicit trust/approval for some MCP and package dependencies.

APM release: https://github.com/microsoft/apm/releases/tag/v0.37.0

## Local setup (manual opt-in)

Run from the dotfiles-ai checkout on the target Ubuntu host:

    bash host/opencode2/install.sh --check       # read-only preview
    bash host/opencode2/install.sh --install     # explicit installation
    export PATH="$HOME/.local/bin:$PATH"         # if absent from PATH
    opencode --version                          # V1 should be unchanged
    opencode2 --version                         # pinned V2
    opencode2 debug paths                       # verify private XDG paths
    opencode2 auth login                        # separately authorize V2
    opencode2                                   # runs on Host; no Docker

Requires npm and network access during explicit installation only. The
installer uses npm's local --prefix, never -g, never invokes make, and never
writes ~/.config/opencode or the Host opencode command. It checks the
installed version before exposing the opencode2 command. Existing
nonidentical files are not overwritten; running it again is idempotent.

## Safety and boundaries

- The launcher sets separate XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME
  and XDG_STATE_HOME and clears inherited OpenCode DB/config overrides
  (OPENCODE_DB, OPENCODE_CONFIG, OPENCODE_CONFIG_DIR and others).
- The launcher forces --standalone and rejects --server, service control,
  upgrade and uninstall. Pairing and other shared-service features are
  not part of this setup.
- By default OPENCODE_DISABLE_PROJECT_CONFIG=1 prevents automatic import
  of V1 project opencode.json(c), .opencode/ plugins and project AGENTS.md.
  After inspecting project configuration, opt in for one invocation with:

    OPENCODE2_ALLOW_PROJECT_CONFIG=1 opencode2

  Claude Code instructions remain disabled by default.
- Host system config such as /etc/opencode and shell-inherited provider API
  keys may still influence the V2 process. This is **version coexistence**,
  not a security sandbox or strong secrets isolation. V2 can modify project
  files if an agent is permitted to do so.
- Never use the standard V2 curl installer, global npm install or the
  existing V1 opencode upgrade/uninstall commands for this setup.

## Validation and rollback

Run offline mock tests without modifying host state:

    python3 -m unittest discover -s tests -p 'test_host_opencode2.py' -v

The mock checks do not establish real Host execution, inference or OAuth
acceptance. Rollback is manual: inspect and then remove only the new V2
launcher, prefix and private XDG trees, preserving any user data first.
Do not remove ~/.config/opencode or V1 data. No automatic deletion command
is supplied.

Official docs:
- https://opencode.ai/docs/
- https://opencode.ai/docs/config
- https://opencode.ai/docs/cli
- https://opencode.ai/docs/cli/providers
- https://github.com/anomalyco/opencode/releases/tag/v2.3.2
