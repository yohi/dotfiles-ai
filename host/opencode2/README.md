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
uv run --no-project --with PyYAML python -m unittest discover -s tests -p 'test_host_v2_apm.py' -v
uv run --no-project --with PyYAML python host/opencode2/sync_apm.py --check
uv run --no-project --with PyYAML python host/opencode2/sync_apm.py --apply
opencode2 mcp list
```

- `--apply` parses the existing `apm.yml` (including YAML
  anchors) but writes only `dependencies.apm`, `dependencies.mcp`,
  package identity, and the OpenCode target to a temporary **anchor-free**
  manifest. It also copies regular `.apm/instructions/*.instructions.md`
  sources without following symlinks. The original SSOT remains unchanged.
  The Host V2 projection corrects the two known Greptile skill paths
  (`greptileai/skills/skills/check-pr` and
  `greptileai/skills/skills/greploop`) and omits the non-existent
  Claude Code-only `anthropics/claude-code//plugins/code-review`
  dependency. All three explicit adaptations are logged on both
  `--check` and `--apply`. All other APM package and MCP entries remain
  unchanged. This does **not** fix the source manifest's legacy references.
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

## Host V2 model settings (APM SSOT, independent of APM install)

Model configuration is deliberately a **separate explicit step** from
`sync_apm.py`. It works even if APM package fetching is blocked. The source
is the existing `apm.yml` `opencode_v2` selection and the two corresponding
provider catalog entries. It never edits the SSOT, V1 settings, sandbox
configuration, or credential stores.

```bash
# From the dotfiles-ai checkout; Host V2 installation already exists.
uv run --no-project --with PyYAML python -m unittest discover -s tests -p 'test_host_v2_models.py' -v
uv run --no-project --with PyYAML python host/opencode2/sync_models.py --check
uv run --no-project --with PyYAML python host/opencode2/sync_models.py --apply

# Confirm available model IDs, then authorize the Host V2 profile separately.
~/.local/bin/opencode2 models openai
~/.local/bin/opencode2 auth login
```

On the current SSOT, the default is `openai/gpt-6-luna`. The optional
Cloudflare AI Gateway Custom entry exposes only
`cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code`
from the selected catalog. The V2-native `providers` format is used;
do not copy the V1 `provider` or its `npm` keys unchanged. Provider policy
denies all other providers and allows OpenAI and Cloudflare Custom only.
**Provider policy does not enforce an individual model allowlist or guarantee
that OpenCode will never select a different model from an allowed provider**;
the SSOT `allowed_models` is validated for the generated default and the
custom-model entry, not installed as a strict runtime per-model gate.

OpenAI uses an independently authorized Host V2 ChatGPT sign-in; no V1 or
Sandbox authentication is imported. Cloudflare requires the server process
environment variables `OC_CF_ACCOUNT_ID`, `OC_CF_GATEWAY_ID`, and
`OC_CF_API_TOKEN` (supply them securely outside the repository).
The generated configuration keeps references such as
`{env:OC_CF_API_TOKEN}`, not plaintext tokens. It uses a non-secret dummy
API key with the dedicated `cf-aig-authorization` header and explicitly
blank `Authorization`. **Cloudflare live requests and actual header merging
remain NOT_VERIFIED**. Do not assume subscription billing is restricted solely
by the two selected model IDs.

Existing APM-managed `mcp.servers`, skills, commands and instructions are
preserved. This sync manages only `model`, `providers`, and `policies`,
records their digest in `model-host-sync-state.json`, and rejects a later
overwrite if those settings were manually changed. `--check` performs no
writes. It does not authenticate, send prompts, or launch a provider process.
For a manual model switch, choose an available model in `/models` or specify
`--model` for one run. No API calls are made by this setup script.

Official config and provider references:
- https://dev.opencode.ai/docs/config/
- https://dev.opencode.ai/docs/providers/
- https://dev.opencode.ai/docs/policies/

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
