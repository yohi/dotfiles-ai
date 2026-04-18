# OpenCode (oh-my-openagent) Knowledge Base

## OVERVIEW
Configuration and profile management for the OpenCode AI agent harness (aka `oh-my-opencode`).
This component manages the "intelligence" and "personas" of the agents.

## DIRECTORY STRUCTURE
- `patterns/`: JSONC templates for different agent configuration patterns.
- `commands/`: Custom slash command definitions (`.md`).
- `skills/`: Specialized agent skills (`SKILL.md` or directories).
- `omo-profiles.sh`: Shell script for managing environment-based profiles.
- `opencode.jsonc.template`: Base template for `oh-my-opencode.jsonc`.

## AGENT ROLES (The 11 Specialists)
Agents operating within this context should understand the hierarchy:
- **Orchestration**: Sisyphus (Director), Prometheus (Planner), Metis (Reviewer), Momus (Auditor)
- **Implementation**: Hephaestus (Craftsman), Sisyphus-Junior (Worker)
- **Research**: Oracle (Sage), Librarian (Librarian), Explore (Explorer), Atlas (Mapper)
- **Vision**: Multimodal-Looker (Eyes)

## CONVENTIONS & RULES
1. **Configuration Files**:
   - `opencode.jsonc`: Core configuration for the **OpenCode** platform itself.
   - `oh-my-opencode.jsonc`: Configuration for the **oh-my-openagent** harness (wrapper). This file is generated from `opencode.jsonc.template` via `omo-profiles.sh` and manages intelligence levels.
2. **Never Edit Generated Files**: Do not directly modify `oh-my-opencode.jsonc`. Edit `opencode.jsonc.template` or files in `patterns/` instead.
3. **Profile Management**: Use `omo-profiles.sh` to switch between intelligence profiles (e.g., `hybrid`, `reasoning`).
4. **Command Logic**: New commands must be added to `commands/` as procedural Markdown files.
5. **Skill Injection**: Use the `skills/` directory for OpenCode-specific capabilities.

## ANTI-PATTERNS
- **Hardcoding API Keys**: Never put secrets in `.jsonc` files. Use environment variables.
- **Direct JSONC Edits**: Modifying the active config without updating the template leads to sync issues.
