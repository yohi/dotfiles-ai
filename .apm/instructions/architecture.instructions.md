---
applyTo: ["**"]
description: APM-managed direct MCP architecture guidelines.
---

# MCP Architecture

This project uses **APM-managed direct MCP servers** for all tools.
Every MCP server is defined in `apm.yml` and executed as a host process
(stdio) or a direct remote SSE connection.

## 1. APM (Single Source of Truth)

`apm.yml` defines all MCP servers under `dependencies.mcp`.
Running `make sync-mcp` generates per-agent configuration files (Claude Code, OpenCode, VSCode, Cursor, Antigravity) from this single source.
Note that Gemini CLI and Codex CLI targets are defined in `apm.yml` but excluded from automatic synchronization via `make sync-mcp` due to local config structures, requiring manual or dedicated sync commands as configured.

- **Local context tools** (`nexus`, `chronos-graph`, `skillport`) run directly
  on the host to access project files and local databases.
- **External APIs** (`coderabbit`, `greptile`, `atlassian`, `sentry-remote`)
  connect to their SaaS endpoints directly.
- **Utility servers** (`filesystem`, `sqlite`, `sequentialthinking`,
  `github-official`, AWS servers) run as stdio processes on the host.

The former secondary gateway layer is retired. There is no separate gateway
service, no `mcp-find` / `mcp-add` dynamic tooling, and no container sandbox
for MCP servers.

## Local Skill Development & Verification

When developing or verifying changes in shared skills
(e.g., `yohi/agent-skills`), you can temporarily link local skill directories
to test them directly within the agent environment.

## 1. Setting up Local Symlinks

To bypass remote package retrieval and use local skill directories from
`~/program/agent-skills`, replace the installed skill folders in
`.agents/skills/` with symlinks pointing to your local repository:

```bash
rm -rf .agents/skills/<skill-name>
ln -sfn ~/program/agent-skills/skills/<skill-name> .agents/skills/<skill-name>
```

## 2. Compiling and Syncing Changes

**CAUTION**: Running `make sync-agents` or `apm install` will overwrite the
symlinks by fetching remote versions.
To compile and sync your local skill changes without breaking the symlinks,
run:

```bash
apm compile
python _scripts/sync_antigravity.py
make sync-agents-core
```
