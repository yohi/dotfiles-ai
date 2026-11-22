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

apm.yml remains the SSOT for **existing V1/OC2** flows; Host V2 uses a
separate minimal config. It does not compile or import APM MCP/Provider
configuration. sandbox/ remains untouched and pinned to its own version.
No credentials are copied from V1 to V2.

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
