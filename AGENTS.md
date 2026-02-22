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
│   ├── superclaude.mk          # SuperClaude framework
│   └── sync-agents.mk          # SSOT sync & meta-prompt injection
├── agent-skills/               # [SSOT] AI agent skill definitions
│   ├── agent-skill-architect/  # Skill architect
│   ├── config-modernizer/      # Config modernizer skill
│   ├── dotfiles-guidelines/    # Dotfiles guidelines skill
│   └── makefile-organization/  # Makefile organization skill
├── agent-commands/             # [SSOT] AI agent slash commands
│   ├── build-skill.md          # /build-skill
│   ├── git-pr-flow.md          # /git-pr-flow
│   └── setup-gh-actions-test-ci.md  # /setup-gh-actions-test-ci
├── global-rules/               # [SSOT] Coding rules & standards
│   ├── MARKDOWN.md             # Markdown guidelines
│   ├── SHELL.md                # Shell script guidelines
│   ├── DOCS_STYLE.md           # Documentation style
│   ├── GIT_STANDARDS.md        # Git standards
│   └── META_PROMPT.md          # Common meta-prompt template
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
├── .skillportrc                # SkillPort CLI configuration
└── Makefile                    # Setup entry point (includes _mk/*.mk)
```

## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** orchestrated by `dotfiles-core`.
All changes MUST comply with the central layout rules. Please refer to the central [ARCHITECTURE.md](https://raw.githubusercontent.com/yohi/dotfiles-core/refs/heads/master/docs/ARCHITECTURE.md) for the full, authoritative rules and constraints.

## THIS COMPONENT — SPECIAL NOTES

- **All tool directories** (`claude/`, `codex/`, `gemini/`, `opencode/`) are deployed to their
  respective config locations (e.g., `~/.config/opencode/`) via Makefile targets using `ln -sfn`.
- **SSOT Principle**: All rules and skills MUST be edited in `agent-skills/` or `global-rules/`.
  Run `make sync-agents` to propagate changes to each agent's config.
- `opencode/AGENTS.md` is a **subdirectory-level** agent context — distinct from this root-level AGENTS.md.
- `_mk/` splits Makefile targets by AI tool (one `.mk` file per tool).
- `agent-skills/` contains reusable skill definitions with `SKILL.md` in each subdirectory.
- `global-rules/` contains coding standards shared across all agents.

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

## SSOT REFERENCES

All agent skills and coding rules are centralized in the following directories.
Refer to these before executing any task.

- **Skills**: `agent-skills/` — Each subdirectory contains a `SKILL.md` with task-specific instructions
- **Coding Rules**: `global-rules/` — MARKDOWN.md, SHELL.md, DOCS_STYLE.md, GIT_STANDARDS.md
