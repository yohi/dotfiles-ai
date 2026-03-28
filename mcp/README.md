# MCP (Model Context Protocol) Configuration

This directory contains the configuration and management scripts for MCP servers used across various AI agents in this repository.

## Configured MCP Servers

### 1. Docker MCP Gateway (SSE)
A centralized gateway that runs multiple MCP servers inside Docker containers.
- **Status**: Enabled
- **Gateway URL**: `http://localhost:10888/sse`
- **Reference**: [docker/mcp-registry](https://github.com/docker/mcp-registry)
- **Included Tools (Managed via `mcp/config.yaml`):**
  - **GitHub Official**: [Reference](https://github.com/docker/mcp-registry/blob/main/servers/github.yaml)
  - **Filesystem**: [Reference](https://github.com/docker/mcp-registry/blob/main/servers/filesystem.yaml)
  - **SQLite**: [Reference](https://github.com/docker/mcp-registry/blob/main/servers/sqlite.yaml)
  - **Sequential Thinking**: [Reference](https://github.com/docker/mcp-registry/blob/main/servers/sequentialthinking.yaml)
  - **Playwright**, **Tavily**, **Chrome DevTools**, etc.

### 2. Atlassian MCP (Direct SSE)
Official MCP server for Atlassian products (Jira, Confluence).
- **Status**: Enabled (Connected directly via SSE to handle browser-based OAuth natively in Gemini CLI)
- **Repository**: [atlassian/atlassian-mcp-server](https://github.com/atlassian/atlassian-mcp-server)
- **Endpoint**: `https://mcp.atlassian.com/v1/mcp`

### 3. Skillport (Custom Docker Image)
Professional development and AI skill management tool.
- **Status**: Enabled (Running via Docker MCP Gateway)
- **Repository**: [gotalab/skillport](https://github.com/gotalab/skillport)
- **Image**: `ghcr.io/yohi/skillport:latest`
- **Features**: Indexed search and loading of agent skills.

## Configuration Files
- `servers.yaml`: Master configuration for all AI agents (Gemini, Claude, etc.).
- `config.yaml`: Defines which servers are enabled within the Docker MCP Gateway.
- `catalogs/custom.yaml.template`: Template for custom server definitions (like Skillport).

## Maintenance Scripts
- `make sync-mcp`: Synchronizes configurations from `servers.yaml` to all agent-specific settings.
- `make setup-docker-mcp`: Sets up the Docker MCP Gateway systemd service and environment.
- `scripts/check-skillport-version.sh`: Checks if the Skillport image is up to date with PyPI.
