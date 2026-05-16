# Agent Instructions for dotfiles-ai

This repository is the central authority for AI agent instructions, skills,
MCP configuration, and reproducible agent runtime setup across Claude Code,
Gemini CLI, OpenCode, Codex, Cursor, VSCode, and Antigravity.

## Authority

- `AGENTS.md` defines repository-wide rules for `dotfiles-ai`.
- Subdirectory `AGENTS.md` files add narrower rules and take precedence in
  their directory scope.
- `global-rules/AGENTS.global.md` contains cross-project user rules and is
  independent from this file.
- Keep this file concise and universally applicable. Put detailed guidance in
  focused docs and link to it instead of copying it here.

## Core Boundaries

- `dotfiles-ai` owns AI behavior: instructions, skills, MCP configuration,
  APM manifests, and agent-facing automation.
- `dotfiles-ide` owns editor infrastructure and UI: editor settings,
  keybindings, themes, and non-AI IDE customization.
- Do not mix IDE styling settings into this repository.
- Do not place AI rules, MCP definitions, or skills in `dotfiles-ide`.

## Source Of Truth

- Manage AI agent configuration through APM. `apm.yml` is the SSOT for
  external skills, custom MCP servers, agent targets, and defaults.
- Commit `apm.lock.yaml` when dependency resolution changes so agent context
  is reproducible.
- Do not hand-edit generated agent MCP files when an APM or Make target owns them.
- Do not edit symlinked files in home directories such as
  `~/.gemini/GEMINI.md`; edit the source file in this repository.
- Never commit machine-specific absolute paths, credentials, API keys,
  personal tokens, or populated `.env` files.

## MCP Architecture

- Use Docker MCP Gateway as the unified MCP entry point, normally via
  `http://127.0.0.1:10888/sse` or `http://localhost:10888/sse`.
- Use Docker MCP Catalog entries when a server exists in the catalog, such as
  GitHub, SQLite, or sequentialthinking.
- Define only non-catalog custom MCP servers in APM, such as Skillport, Nexus,
  or Chronos Graph.
- Use direct MCP configuration only when the server is not in Docker MCP
  Catalog and cannot be represented through the APM-managed flow.
- Keep Gateway backend rendering deterministic through repository Make targets
  rather than ad hoc local edits.

## Environment Variables

- Follow the 3-tier model from `apm-environment.md`.
- Tier 1: OS, shell, keychain, or CI secrets for API keys and personal access tokens.
- Tier 2: project `.env` for environment-specific values; `.env` must stay Git-ignored.
- Tier 3: safe defaults in `apm.yml` for non-secret values.
- Use `${env:VAR}` placeholders in managed configuration instead of embedding
  resolved secret values.
- Keep `.env.example` safe and complete enough to document required variables
  without exposing real values.

## Skills

- Use the APM and Skillport hybrid model from `agent-skills.md`.
- APM is the static management layer for installing, versioning, locking, and
  syncing skills.
- Skillport is the dynamic runtime layer for discovering and loading skills
  during agent work.
- `agent-skills/` is the source location for custom and managed skill definitions.
- `.agents/skills/` is the cross-platform runtime layout consumed by agents
  and Skillport.
- Add external skills through `apm.yml`; add local custom skills under
  `agent-skills/` and sync them into `.agents/skills/`.

## Key Directories

- `apm.yml`: master APM manifest for AI agent dependencies and targets.
- `global-rules/`: cross-project AI instructions.
- `agent-skills/`: source skill definitions.
- `.agents/skills/`: cross-platform skill runtime layout.
- `claude/`, `gemini/`, `opencode/`, `codex/`: agent-specific configuration.
- `ide/`: AI-specific IDE integration, especially MCP configuration for Cursor
  and VSCode.
- `mcp/`: Docker MCP Gateway configuration, catalogs, and render outputs.
- `docs/superpowers/`: design and planning documents for larger repository changes.

## Standard Commands

- `make setup`: bootstrap the full environment and run APM installation hooks.
- `make apm-install`: run `apm install` and post-install synchronization.
- `make setup-apm-env`: create local `.env` from `.env.example` when needed.
- `make sync-agents` or `make sync-skills-to-agents`: sync skills into `.agents/skills/`.
- `make sync-mcp`: render Gateway configuration and refresh the MCP service.
- `make setup-docker-mcp`: set up Docker MCP Gateway.

## Working Guidance

- Read `README.md` and the relevant focused docs before non-trivial changes.
- For APM and environment changes, consult `apm-environment.md` and `docs/superpowers/specs/2026-05-16-dotfiles-ai-reconstruction-design.md`.
- For skill changes, consult `agent-skills.md`.
- For broad implementation plans, consult `docs/superpowers/` and keep root
  instructions lightweight.
- Prefer deterministic verification commands over asking an LLM to manually
  enforce formatting or style.

## Superpowers Intensity

- Level 1: new architecture, major APM/MCP changes, or broad repository reconstruction.
- Level 2: moderate refactoring, workflow changes, or configuration improvements.
- Level 3: small documentation updates, typos, or trivial config corrections.
- Level 0: greetings, chitchat, or direct factual inquiries.

## Polyrepo Layout

- This repository relies on symlinks to `common-mk` from `dotfiles-core`.
- Do not replace these symlinks with physical files unless the user explicitly
  requests environment-specific troubleshooting.
- `DOTFILES_COMMON_RULES.md` points to `../../common-mk/DOTFILES_COMMON_RULES.md`.
- `_mk/core.mk` points to `../../../common-mk/core.mk`.
- `_mk/help.mk` points to `../../../common-mk/help.mk`.

<!-- SKILLPORT_START -->
<!-- Skills are centrally managed through APM and exposed through Skillport.
     Refer to global-rules/AGENTS.global.md for the full shared skill list.
     Unified runtime skills directory: .agents/skills/ -->
<!-- SKILLPORT_END -->
