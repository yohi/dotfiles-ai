# Project Constitution: dotfiles-ai

## 1. Hierarchy & Authority
- **Global Rules (`global-rules/AGENTS.global.md`)**: The **Global Foundation**. It contains universal instructions shared across *all* projects, such as Identity, Language Policy (Japanese output), Security protocols, and cross-project SkillPort workflows.
- **Project Rules (`AGENTS.md`)**: The **Local Constitution** (This file). It contains project-specific mandates, architectural decisions, and directory structures unique to this repository. Local project rules take precedence over global rules if a conflict occurs.
- **Sub-directory Rules**: Highly specific overrides for individual agents or components (e.g., `opencode/AGENTS.md`).

## 2. Project Purpose
This repository is the Central Authority for AI Agent configurations, specialized skills, and AI-enabled development environments. It ensures a consistent "AI persona" across all tools and machines.

## 3. Directory Mandates
- `claude/`, `gemini/`, `opencode/`, `codex/`: High-level configuration for specific AI CLI tools.
- `ide/`: Configuration and extension management for Cursor and VSCode.
- `global-rules/`: Source of Truth for cross-project AI instructions.
- `agent-skills/`: The master repository for SkillPort skills.
- `mcp/`: Management of the Docker MCP Gateway and associated catalogs.

## 4. Development Workflow
- **SSOT Enforcement**: Never edit symlinked files in home directories (e.g., `~/.gemini/GEMINI.md`). Always edit the Source of Truth within this repository.
- **MCP Gateway**: Use the Unified SSE Gateway (`http://localhost:10888/sse`) for all tools. New MCP servers MUST be defined in `mcp/catalogs/custom.yaml.template`.
- **Skill Management**: New AI capabilities MUST be implemented as SkillPort skills in `agent-skills/` and managed via MCP.

## 5. Tooling & Automation
- `make setup`: Bootstrap the environment and create initial symlinks.
- `make setup-docker-mcp`: Re-render MCP configurations and synchronize all agents.
- `make sync-agents`: Propagate global rules and skill updates to all agent contexts.
