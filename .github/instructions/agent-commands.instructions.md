---
applyTo: "(global)"
description: "Information about Agent Commands & Plugins managed by APM"
---

# Agent Commands & Plugins

Custom slash commands (e.g., `/code-review`) located in `agent-commands/` are managed via APM and synced across agent environments. 

These files are often customized versions of official plugins (such as the Claude Code `code-review` plugin) optimized for this specific project environment. For example, they may utilize specific MCP tools like `mcp__github_inline_comment__create_inline_comment` or implement advanced multi-agent workflows with Opus and Sonnet models.

**Always treat files in `agent-commands/` as highly-tailored, project-specific executable tools rather than generic templates.** They have been explicitly modified from their upstream sources to work optimally within the `dotfiles-ai` architecture.
