# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-16
**Commit:** 116ca4f
**Branch:** master

## OVERVIEW
OpenCode configuration repository for managing AI agent behaviors, model patterns, and skills.
Core mechanism involves dynamic injection of JSONC configurations based on selected "patterns".

## STRUCTURE
```
.
├── commands/                  # Custom slash command definitions (.md)
├── docs/                      # Rule files (symlinked to global config)
├── patterns/                  # Model configuration presets (*.jsonc)
├── skills/                    # Agent skill definitions
├── oh-my-opencode.base.jsonc  # TEMPLATE: Edit this file
├── oh-my-opencode.jsonc       # GENERATED: Do not edit
├── opencode.jsonc             # Core plugin/permission config
└── switch-opencode-pattern.sh # Entry point: Pattern switcher
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Change model | `./switch-opencode-pattern.sh` | Interactive menu |
| Edit config | `oh-my-opencode.base.jsonc` | Edit template, then switch pattern |
| New pattern | `patterns/` | Add new .jsonc file |
| Add command | `commands/` | Create .md file |
| Add skill | `skills/` | Create definition |

## CONVENTIONS
- **Language**: Japanese (日本語) for all output/commits. English for `AGENTS.md`.
- **Commits**: Conventional Commits in Japanese (e.g., `feat: 新パターン追加`).
- **Config**: Edit `base.jsonc`, NOT the generated `.jsonc`.
- **Markdown**: Follow `docs/rules/MARKDOWN.md`.

## ANTI-PATTERNS (THIS PROJECT)
- **Direct Edit**: Editing `oh-my-opencode.jsonc` (will be overwritten).
- **English Commits**: Commits must be in Japanese.
- **Forbidden Ops**: `rm`, `ssh`, `sudo` (blocked by `opencode.jsonc`).

## UNIQUE STYLES
- **Dynamic Injection**: Uses `// @pattern:start` markers in `base.jsonc` to inject `patterns/*.jsonc`.
- **Agent Roles**: Sisyphus (Manager), Hephaestus (Coder), Oracle (Advisor).

## COMMANDS
```bash
./switch-opencode-pattern.sh  # Switch model configuration
```
