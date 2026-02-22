# PROJECT KNOWLEDGE BASE

**Repository:** dotfiles-ai
**Role:** AI agent configuration — Claude Code, OpenAI Codex, Gemini CLI, Opencode, MCP servers, and agent skill definitions

## STRUCTURE

```text
dotfiles-ai/
├── _mk/                         # Makefile sub-targets
│   ├── claude.mk               # Claude Code setup
│   ├── codex.mk                # OpenAI Codex setup
│   ├── gemini.mk               # Gemini CLI setup
│   ├── mcp.mk                  # MCP server setup
│   ├── opencode.mk             # Opencode setup
│   ├── skillport.mk            # Skill port targets
│   └── superclaude.mk          # SuperClaude framework
├── agent-skills/               # AI agent skill definitions
│   ├── agent-skill-architect/  # Skill architect
│   ├── config-modernizer/      # Config modernizer skill
│   ├── dotfiles-guidelines/    # Dotfiles guidelines skill
│   └── makefile-organization/  # Makefile organization skill
├── claude/                     # Claude Code configuration
│   ├── CLAUDE.md               # Claude context file
│   └── claude-settings.json    # Claude settings
├── codex/                      # OpenAI Codex configuration
│   └── config.toml             # Codex config
├── gemini/                     # Gemini CLI configuration
│   ├── Core/                   # Core settings (personas, etc.)
│   └── supergemini/            # SuperGemini framework
├── opencode/                   # Opencode configuration
│   ├── AGENTS.md               # Opencode-specific agent context
│   ├── commands/               # Custom slash commands
│   ├── skills/                 # Opencode skills
│   └── DOCUMENT/               # Reference documents
└── Makefile                    # Setup entry point (includes _mk/*.mk)
```

## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** orchestrated by `dotfiles-core`.
All changes MUST comply with the central layout rules. Please refer to [`dotfiles-core/docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) for the full, authoritative rules and constraints.

## THIS COMPONENT — SPECIAL NOTES

- **All tool directories** (`claude/`, `codex/`, `gemini/`, `opencode/`) are **excluded from Stow**.
  AI tool configs are deployed to `~/.config/<tool>/` via Makefile targets, NOT via Stow symlinks.
- Per SPEC.md: AI agent config files referencing absolute paths (e.g., `~/.config/opencode/...`)
  must NOT be rewritten. Stow symlink formation is the assumed prerequisite.
- `opencode/AGENTS.md` is a **subdirectory-level** agent context — distinct from this root-level AGENTS.md.
- `mk/` splits Makefile targets by AI tool (one `.mk` file per tool).
- `agent-skills/` contains reusable skill definitions with `SKILL.md` in each subdirectory.

## CODE STYLE

- **Documentation / README**: Japanese (日本語)
- **AGENTS.md**: English
- **Commit Messages**: Japanese, Conventional Commits (e.g., `feat: 新機能追加`, `fix: バグ修正`)
- **Shell**: `set -euo pipefail`, dynamic path resolution, idempotent operations

## FORBIDDEN OPERATIONS

Per `opencode.jsonc` (when present), these operations are blocked for agent execution:

- `rm` (destructive file operations)
- `ssh` (remote access)
- `sudo` (privilege escalation)
