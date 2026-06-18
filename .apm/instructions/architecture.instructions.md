---
applyTo: ["**"]
description: Hybrid MCP Architecture guidelines and tool placement rules.
---

# Hybrid MCP Architecture

This project employs a hybrid MCP architecture that delegates responsibilities between APM and Docker MCP Gateway to maximize security and performance.

## 1. APM (Direct Host Execution)
APM manages **Core Infrastructure** and **External APIs**. These are run as direct host processes to allow fast, unimpeded access to local resources.
- **Local Context Tools**: `nexus`, `chronos-graph`, and `skillport` MUST be managed by APM. They require direct read/write access to the host's filesystem and project context.
- **Remote APIs**: Tools like `coderabbit` and `greptile` that primarily communicate with remote SaaS endpoints are managed via APM for simplicity.

## 2. Docker MCP Gateway (Sandbox & Dynamic MCP)
Docker MCP Gateway provides a **secure sandbox** for tools that should not have unrestricted access to the host machine.
- **Isolated Tools**: Tools like `SQLite`, `filesystem` (with strict volume mounts), and `sequentialthinking` MUST be run via Docker MCP to contain their execution scope.
- **Dynamic MCP**: The gateway provides dynamic tools (`mcp-add`, `mcp-find`) allowing AI agents to install and run third-party catalog tools on-the-fly without permanently altering the host environment.

## Architectural Mandate
Do NOT merge all MCP servers into Docker MCP Gateway. Maintain this strict separation: if a tool needs unrestricted local project access, it belongs in APM (`apm.yml`). If a tool needs to be sandboxed or is fetched dynamically from a catalog, it belongs in Docker MCP.