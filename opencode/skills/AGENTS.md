# SKILLS KNOWLEDGE BASE

## OVERVIEW
Agent skill definitions and architectural patterns.
Skills define specialized capabilities injected into agents via `load_skills`.

## STRUCTURE
```text
skills/
├── agent-skill-architect/ # Complex skill with multiple files
└── config-modernizer.md   # Single-file skill definition
```

## CONVENTIONS
- **Granularity**: One skill per domain (e.g., "git-master", "frontend").
- **Format**: `.md` or directory with `SKILL.md`.

## ANTI-PATTERNS
- **Overloading**: Don't pack too many unrelated tools into one skill.
