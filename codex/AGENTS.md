# OpenAI Codex CLI Knowledge Base

## OVERVIEW
Configuration and rules for the `codex` command-line tool.
Codex is used for direct file manipulations, code generation, and project-wide reasoning.

## CONFIGURATION
- `config.toml`: Primary settings for model selection, approval policies, and project trust levels.
- `rules/`: Directory for context-specific rules and instructions.
- `skills/`: Local skills for the Codex engine.

## CORE PRINCIPLES
1. **Trust Levels**: Ensure the current project is marked as `trusted` in `config.toml` to allow file writes.
2. **Model Selection**: Default is `gpt-5.4` with `high` reasoning effort.
3. **Skill Integration**: Leverages skills from `../agent-skills/` as defined in the meta-prompt.

## ANTI-PATTERNS
- **Over-reliance on Auto-edit**: Always verify changes made with `approval_policy = "full-auto"`.
- **Large Context Spills**: Be mindful of context window limits when passing multiple large files.
