# COMMANDS KNOWLEDGE BASE

## OVERVIEW
Definitions for custom OpenCode slash commands.
Each `.md` file represents a command logic executable by agents.

## STRUCTURE
```
commands/
├── build-skill.md         # Logic for /build-skill
├── git-pr-flow.md         # Logic for /git-pr-flow
└── setup-gh-actions...md  # Logic for CI generation
```

## CONVENTIONS
- **Format**: Markdown with clear steps.
- **Trigger**: Filename defines command (e.g., `cmd.md` -> `/cmd`).
- **Language**: Logic in English/Japanese, user output in Japanese.

## ANTI-PATTERNS
- **Complex Logic**: Keep commands strictly procedural.
- **Hardcoded Paths**: Use relative paths or context variables.
