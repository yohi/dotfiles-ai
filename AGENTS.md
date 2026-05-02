# Agent Instructions for dotfiles-ai

## 1. Hierarchy & Authority
- **Global Rules (`global-rules/AGENTS.global.md`)**: The **Global Foundation**. It contains universal instructions shared across *all* projects, such as Identity, Language Policy (Japanese output), Security protocols, and cross-project SkillPort workflows.
- **Project Rules (`AGENTS.md`)**: The **Local Constitution** (This file). It contains project-specific mandates, architectural decisions, and directory structures unique to this repository. Local project rules take precedence over global rules if a conflict occurs.
- **Sub-directory Rules**: Highly specific overrides for individual agents or components (e.g., `opencode/AGENTS.md`).

## 2. Project Purpose
This repository is the Central Authority for AI Agent configurations, specialized skills, and AI-enabled development environments. It ensures a consistent "AI persona" across all tools and machines.

### 💡 Core Design Philosophy: Separation of Concerns
We strictly separate **"AI Rules & Behavior"** (`dotfiles-ai`) from **"IDE Infrastructure & UI"** (`dotfiles-ide`).
- **`dotfiles-ide`** manages the physical editor settings (`settings.json`, `keybindings.json`, visual themes) for both Cursor and VSCode.
- **`dotfiles-ai`** (this repository) manages the mind and tools of the AI (`mcp.json`, Agent instructions, SkillPort).
Never mix IDE styling configurations here, and never put AI instructions or MCP configs in `dotfiles-ide`.

## 3. Directory Mandates
- `claude/`, `gemini/`, `opencode/`, `codex/`: High-level configuration for specific AI CLI tools.
- `ide/`: AI-specific configurations (MCP) for Cursor and VSCode. (UI settings are moved to `dotfiles-ide`).
- `global-rules/`: Source of Truth for cross-project AI instructions.
- `agent-skills/`: The master repository for SkillPort skills.
- `mcp/`: Management of the Docker MCP Gateway and associated catalogs.

## 4. Development Workflow
- **SSOT Enforcement**: Never edit symlinked files in home directories (e.g., `~/.gemini/GEMINI.md`). Always edit the Source of Truth within this repository.
- **Unified Manifest**: **`apm.yml`** is the master manifest and Single Source of Truth (SSOT) for the entire project, managing AI skills, MCP server definitions, and agent environment configurations.
- **MCP Gateway**: Use the **Unified SSE Gateway (`http://localhost:10888/sse`)** as the standard connection method for all tools.
  - **Benefits of SSE Integration**:
    - **Zero-second Startup**: Eliminates initialization delays (typically 7-10s) and timeouts common with stdio.
    - **Resource Stability**: Prevents "too many open files" errors and DB lock conflicts.
    - **APM Integration**: `apm install` automatically injects the Gateway SSE endpoint and re-renders the backend `mcp/config.yaml`.
- **Skill Management**: New AI capabilities MUST be implemented as SkillPort skills in `agent-skills/` and managed via MCP. External skills are managed via `apm.yml`.

## 5. Tooling & Automation
- `make setup`: Bootstrap the environment and run `apm install`. (Triggers `sync-agents` and executes APM's `post_install` hooks).
- `make setup-docker-mcp`: Bootstrap Docker MCP Gateway service files and runtime environment.
- `make sync-mcp`: Re-render Gateway backend configuration from `apm.yml` and restart the service. (Executed automatically by `apm install`).

## 6. Superpowers Workflow: Project Level
As the central authority for AI configurations, **Level 1 (High Intensity)** is the default for most tasks in this repository.
- **Level 2 (Medium Intensity)**: Refactoring, improvements, or moderate logic changes.
- **Level 3 (Low Intensity)**: Minor documentation or trivial configuration changes.
- **Level 0 (Zero Intensity)**: Greetings, chitchat, or direct inquiries.

## 7. Component Layout Convention (Polyrepo)
This repository relies on symbolic links to `common-mk` from [dotfiles-core](https://github.com/yohi/dotfiles-core). **NEVER** replace these links with physical files.
- `DOTFILES_COMMON_RULES.md` -> `../../common-mk/DOTFILES_COMMON_RULES.md`
- `_mk/core.mk` -> `../../../common-mk/core.mk`
- `_mk/help.mk` -> `../../../common-mk/help.mk`
