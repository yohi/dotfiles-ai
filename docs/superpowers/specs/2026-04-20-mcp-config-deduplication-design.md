# MCP Config Deduplication Design

## Objective
To automatically prevent MCP tool duplication in client agent configurations (like Gemini CLI, Claude Code) when they connect to the Docker MCP Gateway.

## Context
Currently, the SSOT for all MCP configurations is `mcp/servers.yaml`. The script `_scripts/render-mcp-configs.py` generates the Gateway's `mcp/config.yaml` and the individual client configs (e.g., `gemini/settings.json`). If a user mistakenly inherits both the `docker-mcp` Gateway and a specific server (like `filesystem`) that is already hosted by the Gateway, the client receives the tools twice: once via the Gateway SSE connection and once via a direct connection. This results in an `MCP ERROR` due to tool name collisions.

## Design

### 1. Gateway Server Identification
During the execution of `render-mcp-configs.py`, the script first determines which servers are hosted by the Gateway. These are servers with `type: server`. The list of these server names is stored as the "Gateway-enabled servers list".

### 2. Client Configuration Deduplication
When processing the `servers` block for each agent (defined in `mcp/servers.yaml`):
1. **Detect Gateway Usage:** The script checks if the agent's configuration includes the `docker-mcp` (or `docker-mcp-local`) server.
2. **Filter Duplicates:** If the Gateway is in use, the script will filter out any other servers from the agent's configuration that are present in the "Gateway-enabled servers list".
3. **Preserve Direct Connections:** Servers that are *not* hosted by the Gateway (e.g., `type: local` like `chronos-graph`, or `type: sse` like `atlassian`) will remain in the client's configuration.

### 3. Error Handling and Logging
- If a duplicate server is detected and removed, the script will print a helpful informational message to the console: `Skipping <server_name> for <agent_name> because it is provided by the Gateway.`
- This ensures visibility into the automatic deduplication process without causing the build to fail.

## Testing Strategy
- Add a test case or manually verify by temporarily adding a Gateway-hosted server (e.g., `filesystem`) to the `gemini` agent in `mcp/servers.yaml`.
- Run `make sync-mcp`.
- Verify that `gemini/settings.json` contains `docker-mcp` but *does not* contain `filesystem`.
- Verify the console output shows the skip message.
