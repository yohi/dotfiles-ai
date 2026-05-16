# Cursor IDE AI Knowledge Base

## OVERVIEW
Configuration and rules for AI agents operating within the Cursor IDE environment.
This includes MCP server management and custom slash commands.

## DIRECTORY STRUCTURE
- `commands/`: Custom slash commands (e.g., CodeRabbit, Agent workflows).
- `settings.json.template`: Template for Cursor editor settings.
- `mcp.json`: (Generated) Model Context Protocol server configurations.

## KEY WORKFLOWS
1. **MCP Synchronization**: Always use `make sync-mcp` to update `mcp.json` from the central `apm.yml`. Do not edit `mcp.json` directly.
2. **Slash Commands**:
   - `/coderabbit-review`: Comprehensive code review using CodeRabbit CLI.
   - `/build-skill`: Interactive skill generation.
   - `/git-pr-flow`: Automated Git workflow management.
3. **Kiro Spec-Driven Development**: Follow the phased workflow: Steering -> Requirements -> Design -> Tasks -> Implementation.

## AGENT BEHAVIOR
- **Personas**: Use specific personas like `@architect`, `@developer`, or `@tester` when appropriate.
- **Verification**: After implementation, use automated tests to verify changes.
- **Context**: Be aware of the `CLAUDE.md` in this directory for detailed technical guidance.

## ANTI-PATTERNS
- **Manual MCP Editing**: Leads to sync conflicts with the master `apm.yml`.
- **Bypassing Approval Gates**: Do not proceed to the Implementation phase without an approved Design and Tasks list.
