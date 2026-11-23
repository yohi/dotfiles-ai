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
- CodeGraph uses its official installed CLI entrypoint `codegraph serve --mcp`
  (not `_scripts/codegraph-bootstrap.sh`). The MCP process runs in the
  active project directory; it never performs an implicit `codegraph init`.
  The CLI must already be installed on the Host and any per-project index
  must be initialized explicitly with `codegraph init`.
  For an existing Host V2 snapshot whose CodeGraph command still points
  at the old wrapper, use the targeted, no-network update:
  `uv run --no-project --with PyYAML python host/opencode2/sync_apm.py --refresh-codegraph`.
  It validates APM ownership, updates only CodeGraph's native command,
  preserves all current MCP enabled/disabled flags and the other Host V2
  settings, and refreshes the APM receipt. Do not rerun full `--apply` just
  to repair CodeGraph: a full APM sync may replace MCP enablement choices.
- APM v0.37.0 real dependency-resolution and Host V2 live MCP/skill
  recognition have not been verified by the offline mock tests. Treat the
  first `--apply` as live acceptance. The actual APM manifest may require
  explicit trust/approval for some MCP and package dependencies.

APM release: https://github.com/microsoft/apm/releases/tag/v0.37.0

## Host V2 model settings (V1 provider parity, APM SSOT)

Model configuration is an explicit, independent step from `sync_apm.py`.
Its source is the unchanged `apm.yml`: V1's `enabled_providers` for the Host
provider set, V1's `provider` catalogs/whitelists for models, and
`opencode_v2.default_model` for the default. The Sandbox-only
`opencode_v2.providers` and `opencode_v2.allowed_models` remain unchanged
and continue to constrain the separate OC2 Sandbox runtime.

Run from the dotfiles-ai checkout, after the Host V2 binary is installed:

```bash
uv run --no-project --with PyYAML python \
  -m unittest discover -s tests -p 'test_host_v2_models.py' -v
uv run --no-project --with PyYAML python \
  host/opencode2/sync_models.py --check       # no writes
uv run --no-project --with PyYAML python \
  host/opencode2/sync_models.py --apply       # Host V2 only

~/.local/bin/opencode2 debug config | jq '{model, providers: (.providers | keys), policies}'
~/.local/bin/opencode2 models
```

The default remains `openai/gpt-6-luna`. The Host V2 projection admits the
following **nine** SSOT-enabled providers:

| Provider | Source and Host V2 treatment |
| --- | --- |
| openai | Native catalog; V1 whitelist entries are included |
| opencode | Native Console catalog; V1 curated Free entries |
| opencode-go | Native Go catalog; V1 selected entries |
| ollama-cloud | Native provider catalog (no V1 whitelist declared) |
| amazon-bedrock | Native provider catalog; V1 whitelist entries |
| google | Native catalog; V1 whitelist entries |
| cloudflare-ai-gateway | V1 ai-gateway-provider replaced by V2 openai-compatible `/compat` endpoint |
| cloudflare-ai-gateway-custom | All V1 custom-model entries, translated to V2 openai-compatible |
| cloudflare-ai-gateway-octg | All V1 OCTG models; native OpenAI Responses provider |

`cloudflare-ai-gateway-dynamic` remains **disabled**. The existing
default model and Host V2's per-provider policies remain in place, but
the policies now allow the nine providers listed above and deny
others. A provider policy is **not** a per-model allowlist: OpenCode can
show additional built-in models and may fall back if a selected model is
unavailable. Do not treat the model list alone as proof of authorization,
billing restrictions, endpoint compatibility, or successful inference.

V1 named reasoning variants are translated to V2 model `settings`,
`body`, and `variants` entries where the known SSOT shape is supported.
OpenCode V2's native catalog and different provider packages may interpret
those fields differently. The converter stops for unexpected SSOT
provider IDs, source endpoint changes, or unsupported variant structures.

Credentials must be provisioned **separately** for this Host V2 profile:
OpenAI ChatGPT sign-in, the OpenCode Go/Console accounts, Ollama Cloud,
Google and AWS Bedrock when used. The three Cloudflare provider routes use
`OC_CF_ACCOUNT_ID`, `OC_CF_GATEWAY_ID`, `OC_CF_API_TOKEN`, or the
corresponding `OCTG_CF_*` variables in the environment. No secret or
existing V1 login is copied; the output stores only `{env:...}` references
and non-secret placeholders. Provider availability depends on separate
authentication and entitlement.

**Live acceptance remains NOT_VERIFIED** for Cloudflare Unified's migration
from the V1-specific adapter to `/compat`, Cloudflare Custom/OCTG HTTP
headers, and model calls to any provider. Cross-provider subscription
pricing and quotas are not enforced by this sync; some catalog entries may
consume separate paid balances. Check credentials and billing policy before
selecting a paid model.

Existing `mcp.servers`, skills, commands and instructions are preserved.
`sync_models.py` manages only `model`, `providers`, and `policies` and records
a digest in `model-host-sync-state.json`. It supports upgrading a previously
synchronized two-provider Host V2 configuration, while refusing to overwrite
subsequent manual changes to managed fields. `--check` performs no writes;
`--apply` does not make inference calls, authenticate, or modify V1, Sandbox,
or the source `apm.yml`.

Official docs:
- https://opencode.ai/docs/providers/
- https://opencode.ai/docs/models/
- https://opencode.ai/docs/policies/

## Claude Agent (Host V2 native integration)

OpenCode V2.2.3+ includes the built-in **Claude Agent** provider
(`claude-agent`). This is not an MCP server and does not require installing
a third-party OpenCode plugin. The Host model sync adds one
`provider.use` allow statement for `claude-agent`, after the existing
nine V1-enabled provider policies. The default remains
`openai/gpt-6-luna`; the `providers` catalog remains at nine entries.
Claude Agent models appear only after connecting a local Claude Code login.

```bash
# Update the Host V2 generated policies (not the V1/Sandbox settings).
uv run --no-project --with PyYAML python host/opencode2/sync_models.py --check
uv run --no-project --with PyYAML python host/opencode2/sync_models.py --apply

# Inspect whether the Claude Code CLI exists and is signed in on this host.
command -v claude
claude auth status

# If not signed in, run separately and complete the Claude login flow:
# claude auth login
# Launch Host V2 and select "Claude Agent" from /connect:
~/.local/bin/opencode2
```

The native provider launches the installed `claude` CLI from `PATH` or
`OPENCODE_CLAUDE_PATH`. OpenCode does not copy Claude Code login tokens.
Authentication and availability are not proven by configuration alone; the
Owner must select **Claude Agent** in `/connect` and confirm that its
models appear and work. CLI accounts backed by API keys or AWS/Vertex
may incur usage charges independent of a Claude subscription.

The launcher intentionally keeps `OPENCODE_DISABLE_CLAUDE_CODE=1`.
This flag disables automatic loading of `CLAUDE.md` and `.claude`
skills; it does **not** disable the native `claude-agent` provider.
Keeping it set prevents the Host V2 launcher from implicitly importing
V1's project-specific Claude instructions and skills.

The model sync preserves existing MCP enablement and the separately
managed APM state. No Claude executable is installed automatically and
no login, model inference, PR, or other external action is performed by
the sync script.

Official reference: https://opencode.ai/changelog/v2.2.3

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

## Explicit all-environment SSOT sync

Use one command from the repository root after editing `apm.yml`.
Nothing runs on a timer or at OpenCode startup:

```bash
make check-apm-all  # read-only plan, manifest validation and Host V2 checks
make sync-apm-all   # explicit apply to enabled/existing environments
```

The runner reuses existing Make/APM generators instead of introducing
independent platform configs. Its current routing:

- Root APM `targets` (`opencode`, `codex`): install/compile, skill adapters,
  generated instructions and commands, then V1 and Codex host bindings
- Existing Claude Code profile: Claude user-scope APM MCP/settings sync
- Existing Antigravity profile: explicit Antigravity APM target sync
- Gemini CLI: only if explicitly included in root `targets` and already
  configured; the current disabled Gemini integration stays off
- Existing Host OpenCode V2: model/provider sync and APM MCP/skill/command
  snapshot sync, with Owner-selected MCP `disabled` flags preserved
- OC2 Sandboxes: live runtime explicitly excluded; require separate Owner
  approval and runtime-specific acceptance for any changed Sandbox

New MCP names remain **disabled by default**. The shared `cf-mcp-portal`
remains disabled by policy. The sync does not copy credentials, install
binaries, pull Git, toggle disabled features, or modify running Sandboxes.
If a generated tracked file has local edits, the preflight stops before any
apply steps. Existing user changes in unrelated working-tree paths are
not reset or stashed.

This is **per-step safe stopping**, not a transaction across all agents.
On a failure, it prints the failed step and how many subsequent steps were
not run; previously completed steps remain applied. A `CHECK_PASS` does
not prove remote APM resolution, authentication, MCP connection, model
inference, or real Sandbox acceptance. Review any `SKIPPED` entries:
a command cannot silently claim that an unavailable or disabled
environment was synchronized. If required tools or dependencies are
missing, the command stops instead of installing them implicitly.
