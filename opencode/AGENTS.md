# OpenCode (oh-my-openagent) Knowledge Base

## OVERVIEW
Configuration and management for the OpenCode AI agent harness (aka `oh-my-opencode`).
This component manages the "intelligence" and "personas" of the agents.

## DIRECTORY STRUCTURE
- `commands/`: Custom slash command definitions (`.md`).
- `skills/`: Specialized agent skills (`SKILL.md` or directories).
- `opencode.jsonc`: Core configuration for the **OpenCode** platform itself.
- `oh-my-openagent.jsonc`: Configuration for the **oh-my-openagent** harness (wrapper).

## AGENT ROLES (The 11 Specialists)
Agents operating within this context should understand the hierarchy:
- **Orchestration**: Sisyphus (Director), Prometheus (Planner), Metis (Reviewer), Momus (Auditor)
- **Implementation**: Hephaestus (Craftsman), Sisyphus-Junior (Worker)
- **Research**: Oracle (Sage), Librarian (Librarian), Explore (Explorer), Atlas (Mapper)
- **Vision**: Multimodal-Looker (Eyes)

## CONVENTIONS & RULES
1. **Configuration Files**:
   - `opencode.jsonc`: Core configuration for the **OpenCode** platform itself.
   - `oh-my-openagent.jsonc`: Configuration for the **oh-my-openagent** harness (wrapper).
2. **Edit Directly**: Modify `opencode.jsonc` and `oh-my-openagent.jsonc` directly to change settings. These files are now tracked in Git.
3. **No Dynamic Profiles**: The previous pattern-based profile switching system has been removed in favor of a static configuration.
4. **Command Logic**: New commands must be added to `commands/` as procedural Markdown files.
5. **Skill Injection**: Use the `skills/` directory for OpenCode-specific capabilities.

## ANTI-PATTERNS
- **Hardcoding API Keys**: Never put secrets in `.jsonc` files. Use environment variables.
- **Complexity**: Avoid introducing template systems for core configurations unless strictly necessary.
