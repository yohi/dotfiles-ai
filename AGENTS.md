# PROJECT KNOWLEDGE BASE

**Repository:** dotfiles-ai
**Role:** AI agent configuration — Claude Code, OpenAI Codex, Gemini CLI, Opencode, MCP servers, and agent skill definitions

## STRUCTURE

```text
dotfiles-ai/
├── mk/                         # Makefile sub-targets
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
└── Makefile                    # Setup entry point (includes mk/*.mk)
```

## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** orchestrated by `dotfiles-core`.
All changes MUST comply with the following layout rules.

### Required Files

Every component repository MUST have:

| File | Purpose |
| :--- | :--- |
| `Makefile` | Exposes a `setup` target; called by `dotfiles-core` via delegation |
| `.stow-local-ignore` | Lists files/dirs excluded from Stow symlink creation |
| `README.md` | Component overview (written in Japanese) |
| `LICENSE` | MIT license |
| `.gitignore` | Git exclusion rules |

### Stow Symlink Rules

GNU Stow creates symlinks from this repo's root into `~/`.
**Only dotfiles and directories intended for the user's `$HOME` should be Stow targets.**

- Files/dirs listed in `.stow-local-ignore` are **excluded** from Stow.
- When `.stow-local-ignore` exists, Stow's default exclusions (README.*, LICENSE, etc.) are **disabled** — you must list them explicitly.
- `.stow-local-ignore` patterns are interpreted as **regex** — escape dots: `README\.md`, not `README.md`.

### Makefile Rules

```makefile
.DEFAULT_GOAL := setup
# include mk/<feature>.mk    # if using mk/ subdirectory

.PHONY: setup
setup:
 @echo "==> Setting up dotfiles-<name>"
```

1. `setup` target is **mandatory** (interface for dotfiles-core delegation).
2. Set `.DEFAULT_GOAL := setup` when using `include` directives.
3. Declare all non-file targets with `.PHONY`.
4. Use `mk/` subdirectory to split complex Makefiles.
5. Print progress with `@echo "==> ..."`.

### `bin/` vs `scripts/`

| Directory | Purpose | On `$PATH` | Stow target |
| :--- | :--- | :--- | :--- |
| `bin/` | Public commands callable by users or other components | ✅ Added dynamically by dotfiles-zsh | ❌ Excluded |
| `scripts/` | Internal helpers for this component only | ❌ | ❌ Excluded |

### Path Resolution (MANDATORY)

All scripts must resolve paths dynamically. Hardcoded absolute paths are **forbidden**.

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
```

**Forbidden:**

- Hardcoded paths like `~/dotfiles/components/dotfiles-ai/...`
- Legacy `$DOTFILES_DIR` references from monorepo era

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
