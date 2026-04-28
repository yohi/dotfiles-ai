# dotfiles-ai: Microsoft APM Migration Design

## 1. Objective
Migrate the AI agent configuration and skill management system of `dotfiles-ai` to **Microsoft APM (Agent Package Manager)**.
The goal is to eliminate custom Bash/Python sync scripts by leveraging APM's native capabilities for transitive dependency resolution and automatic client configuration (Cursor, Claude Code, Gemini CLI, etc.), while preserving the benefits of the Docker MCP Gateway (SSE aggregation).

## 2. Architecture Strategy
**"APM Native Transition with Gateway Preservation" (Approach A)**

*   **APM as SSOT**: `apm.yml` at the repository root becomes the Single Source of Truth for all external skill dependencies and client-side MCP configurations.
*   **Gateway Retention**: The Docker MCP Gateway (`http://127.0.0.1:10888/sse`) is maintained to manage backend server execution (container lifecycle, etc.).
*   **Division of Labor**:
    *   **APM**: Downloads skills, hashes them for security (`apm.lock.yaml`), and injects the Gateway SSE endpoint into each AI client's native config file.
    *   **Makefile/Hooks**: A scaled-down script handles only the Gateway's backend configuration (e.g., generating `mcp/config.yaml` from `mcp/servers.yaml` and restarting the systemd service) triggered via APM's `post_install` hook.

## 3. File System Changes

### 3.1 Files to Delete (Fully Replaced by APM)
APM natively handles what these files previously did manually:
*   `agent-skills/EXTERNAL_SKILLS.md`
*   `_scripts/install-external-skills.sh`
*   `_mk/superpowers.mk`
*   `_scripts/sync-mcp-configs.sh`
*   `claude/settings.json.template`
*   `gemini/settings.json.template`
*   `ide/cursor/mcp.json.template`
*   `ide/vscode/settings.json.template`

### 3.2 Files to Modify / Refactor
*   `_scripts/render-mcp-configs.py`: Remove all logic related to generating client configs (Cursor, Gemini, etc.). It must strictly generate `mcp/config.yaml` for the Gateway.
*   `Makefile` (and `_mk/setup.mk`): Replace complex `make setup` dependencies with a single call to `apm install`. Remove obsolete `sync-mcp` client targets.

### 3.3 Files to Add
*   `apm.yml`: The main manifest file.

## 4. `apm.yml` Specification

```yaml
name: dotfiles-ai
version: 1.0.0
description: "AI Agent settings, skills, and unified MCP configuration for dotfiles"

dependencies:
  apm:
    - "obra/superpowers#main"
    - "anthropics/skills#main"

  mcp:
    - name: docker-mcp-gateway
      transport: sse
      url: "http://127.0.0.1:10888/sse"

exports:
  skills:
    - "agent-skills/**"

hooks:
  post_install:
    - command: "make sync-mcp"
      description: "Re-rendering Docker MCP Gateway backend configs and restarting service."
```

## 5. Deployment Flow
1. User clones the repository (as part of `dotfiles-core`).
2. User runs `make setup` (which internally calls `apm install`).
3. APM installs external skills (`superpowers`, `anthropics`).
4. APM natively injects the `docker-mcp-gateway` SSE endpoint into all detected AI clients.
5. The `post_install` hook triggers `make sync-mcp` to update the Gateway backend.
6. The user's AI agents are fully configured and ready to use.