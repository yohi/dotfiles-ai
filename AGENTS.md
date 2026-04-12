# Agent Instructions for dotfiles-ai


## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** managed by [dotfiles-core](https://github.com/yohi/dotfiles-core).

### ⚠️ CRITICAL: SYMBOLIC LINK & STANDALONE USAGE
- **Standalone usage is NOT supported.** 公式にはサポートされていませんが、自己責任での単体使用は可能であり、使用する場合は symbolic links と ARCHITECTURE.md に従い、共通ライブラリ（dotfiles-core）を上書きしないことを前提としてください.
- **Symbolic Links:** This repository relies on symbolic links to `common-mk`. **NEVER** suggest or perform a replacement of these symbolic links with physical files/directories. 
- **SSOT:** Always respect the "Single Source of Truth" principle. Shared logic resides in `dotfiles-core`, and components must remain thin wrappers or specific configurations.
- **Architectural Compliance:** All modifications must adhere to the layout defined in the central [ARCHITECTURE.md](https://github.com/yohi/dotfiles-core/blob/master/docs/ARCHITECTURE.md).

> [!IMPORTANT]
> Please refer to [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) for common base rules.
> 
> **Note on Symbolic Links:**
> Several files are symbolic links to an external `common-mk` directory:
> - `DOTFILES_COMMON_RULES.md` -> `../../common-mk/DOTFILES_COMMON_RULES.md`
> - `_mk/core.mk` -> `../../../common-mk/core.mk`
> - `_mk/help.mk` -> `../../../common-mk/help.mk`
>
> If these links appear broken, ensure the `common-mk` repository is placed at the correct relative path as specified in [README.md](./README.md#-単体使用時の注意点).

## 1. Hierarchy & Authority
- **Global Rules (`global-rules/AGENTS.global.md`)**: The **Global Foundation**. It contains universal instructions shared across *all* projects, such as Identity, Language Policy (Japanese output), Security protocols, and cross-project SkillPort workflows.
- **Project Rules (`AGENTS.md`)**: The **Local Constitution** (This file). It contains project-specific mandates, architectural decisions, and directory structures unique to this repository. Local project rules take precedence over global rules if a conflict occurs.
- **Sub-directory Rules**: Highly specific overrides for individual agents or components (e.g., `opencode/AGENTS.md`).

## 2. Project Purpose
This repository is the Central Authority for AI Agent configurations, specialized skills, and AI-enabled development environments. It ensures a consistent "AI persona" across all tools and machines.

### 💡 Core Design Philosophy: Separation of Concerns
We strictly separate **"AI Rules & Behavior"** (`dotfiles-ai`) from **"IDE Infrastructure & UI"** (`dotfiles-ide`).
- **`dotfiles-ide`** manages the physical editor settings (`settings.json`, `keybindings.json`, visual themes) for both Cursor and VSCode.
- **`dotfiles-ai`** (this repository) manages the mind and tools of the AI (`mcp.json`, `supercursor`/`supercopilot` framework, Agent instructions, SkillPort).
Never mix IDE styling configurations here, and never put AI instructions or MCP configs in `dotfiles-ide`.

## 3. Directory Mandates
- `claude/`, `gemini/`, `opencode/`, `codex/`: High-level configuration for specific AI CLI tools.
- `ide/`: AI-specific configurations (MCP, SuperCursor/SuperCopilot) for Cursor and VSCode. (UI settings are moved to `dotfiles-ide`).
- `global-rules/`: Source of Truth for cross-project AI instructions.
- `agent-skills/`: The master repository for SkillPort skills.
- `mcp/`: Management of the Docker MCP Gateway and associated catalogs.

## 4. Development Workflow
- **SSOT Enforcement**: Never edit symlinked files in home directories (e.g., `~/.gemini/GEMINI.md`). Always edit the Source of Truth within this repository.
- **MCP Gateway**: Use the Unified SSE Gateway (`http://localhost:10888/sse`) for all tools. New MCP servers MUST be defined in `mcp/catalogs/custom.yaml.template`, and the gateway-enabled server set MUST be managed in `mcp/config.yaml`.
- **Skill Management**: New AI capabilities MUST be implemented as SkillPort skills in `agent-skills/` and managed via MCP.
- **External Skills (Lock-file)**: High-quality external skills (like `superpowers/`) are managed via `agent-skills/EXTERNAL_SKILLS.md`. These files are ignored by Git and synchronized across environments using `make setup-superpowers` or `make sync-agents`. This prevents duplicating external code while maintaining version consistency.

## 5. Tooling & Automation
- `make setup`: Bootstrap the environment and create initial symlinks.
- `make setup-docker-mcp`: Bootstrap Docker MCP Gateway service files and runtime environment.
- `make sync-agents`: Refresh skill listings from `agent-skills/`, then propagate shared agent assets to each agent context.

## 6. MCP Gateway Advanced Configuration

When managing custom command-based MCP servers (e.g., `uv tool run`) using `docker-mcp-gateway`, please note the following technical requirements and workarounds.

### ⚠️ Constraints and Workarounds for Custom Servers
1.  **Mandatory `image` Field (No Host Execution)**: 
    The Docker MCP Gateway **always** executes servers within isolated Docker containers; it cannot execute commands directly on the host machine. When defining a command-based server (e.g., `uvx` or `npx`) in the catalog, you MUST specify a valid Docker image that contains the required execution environment (e.g., `ghcr.io/astral-sh/uv:python3.12-bookworm` for Python/uv, or `node:lts-slim` for Node/npx). Do NOT use a dummy placeholder image, as the command will fail if the dependencies (like `uv` or `git`) are missing inside the container.
2.  **Manual Registration in `registry.yaml`**:
    If a custom server in the catalog is not automatically detected, force its recognition by manually adding an entry to `~/.docker/mcp/registry.yaml`:
    ```yaml
    registry:
      your-server-name:
        ref: ""
    ```
3.  **Environment Variables & Volume Mounts**:
    Host-side tools often require specific environment variables and filesystem access. Explicitly map these using the `env` and `volumes` sections in `mcp/catalogs/custom.yaml.template`.

### 🛠️ Troubleshooting: "too many open files"
A `too many open files` error in the gateway logs usually indicates resource exhaustion from orphaned MCP containers. Cleanup all managed containers using:
```bash
docker ps -q --filter "label=docker-mcp=true" | xargs -r docker stop
docker container prune -f --filter "label=docker-mcp=true"
```

### 📚 References
- [Docker MCP Gateway: Getting Started](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
- [Docker MCP Gateway: FAQs & Troubleshooting](https://docs.docker.com/ai/mcp-catalog-and-toolkit/faqs/)
- [GitHub: docker/mcp-gateway (Lifecycle Management)](https://github.com/docker/mcp-gateway#overview)
- [Community Guide: Advanced Docker MCP Gateway Usage](https://qiita.com/moritalous/items/8789a37b7db451cc1dba)

<!-- SKILLPORT_START -->
<!--
  NOTE: Global skills are maintained in global-rules/AGENTS.global.md.
  To avoid context bloating, common skills are not listed in this project's local AGENTS.md.
  Refer to the global rules for the full available skill list.
-->
<!-- SKILLPORT_END -->

## Superpowers Workflow
This project adheres to the **Superpowers Workflow** as defined in [`global-rules/AGENTS.global.md`](global-rules/AGENTS.global.md). All Skill Integration rules, mandatory MCP tool usage, and workflow principles defined in the global reference apply here to balance rigor and efficiency based on task complexity.

### Project Application Level
As the central authority for AI agent configurations, **Level 1 (High Intensity)** is the default for most tasks.
- **Level 2 (Medium Intensity)** may be applied for refactoring, improvements, or moderate logic changes.
- **Level 3 (Low Intensity)** is reserved for minor documentation edits or trivial configuration changes to ensure a rapid response without sacrificing essential validation.

## 単体使用時の注意点

公式にはサポートされていませんが、自己責任での単体使用は可能であり、使用する場合は symbolic links と ARCHITECTURE.md に従い、共通ライブラリ（dotfiles-core）を上書きしないことを前提としてください.
