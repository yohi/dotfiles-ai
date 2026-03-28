# Docker MCP Gateway Configuration

## MCP Catalog Registry
The official source of MCP server information used by the Docker MCP Gateway is managed in the following repository:
- [docker/mcp-registry](https://github.com/docker/mcp-registry)

### 1. Purpose and Goals
This registry serves as a centralized platform for managing MCP server metadata. It facilitates the secure distribution and execution of MCP servers through Docker infrastructure, including Docker Hub and the Docker Desktop MCP Toolkit.

### 2. Repository Structure
The project is built with Go and follows a standard structure:
- `/servers/`: **Core Catalog**. Contains definition files for each registered MCP server.
- `/cmd/`, `/pkg/`, `/internal/`: Logic for registry management and validation.
- `/agents/security-reviewer/`: Automated agents that verify the security of submitted servers.
- `Taskfile.yml`: Definition for development and testing tasks.

### 3. Guidelines for Adding Servers
When adding a new MCP server to the Docker MCP Gateway, adhere to the following priority and standards:
- **Priority Use of MCP Registry**: Always prioritize using Docker Hub images that are registered in the [MCP Registry](https://github.com/docker/mcp-registry).
- **Official Images**: Ensure that **Official Docker Hub images** are used. Prefer images maintained by Docker or the original tool authors to ensure security and stability.

### 4. Special Handling: Browser-based Authentication
In Linux environments (without Docker Desktop), servers requiring browser-based OAuth authentication should be kept **outside** the Docker MCP Gateway.
- **Reason**: The Docker MCP Gateway relies on Docker Desktop's proprietary notification channel (`backend.sock`) to handle OAuth flows. Native Linux environments lack this mechanism, causing authentication to fail inside the Gateway container.
- **Best Practice**: Use a local `stdio` proxy or a standalone installation for these servers to ensure the browser can be launched and tokens can be managed within the user's host session.

### 5. Atlassian MCP Server
The Atlassian MCP server is a primary example of a server kept outside the Gateway for authentication stability.
- **Repository**: [atlassian/atlassian-mcp-server](https://github.com/atlassian/atlassian-mcp-server)
- **Endpoint**: `https://mcp.atlassian.com/v1/mcp`
- **Transport**:
  - The hosted backend uses **SSE**.
  - It is integrated into Gemini CLI using a **direct SSE connection**. Gemini CLI handles the OAuth 2.0 authentication flow and token management natively.

### 6. Server Registration Process
Contributions to the registry follow this workflow:
1. **Fork the Repository**: Start work on your own branch.
2. **Add Definition**: Create a YAML metadata file in `/servers/` including the name, description, image reference, and maintenance info.
3. **Select Delivery Option**:
   - **Docker-managed Build (Recommended)**: Docker handles the build, signing, and SBOM attachment for maximum trust.
   - **External Image**: Register an image you have already built.
4. **Submit Pull Request**: After passing code review and automated security checks by the Docker team, the server is added to the official catalog.

### 7. Technical Highlights
- **High Security**: Docker-provided images include SBOMs (Software Bill of Materials) and provenance tracking to prevent tampering.
- **Container Isolation**: All MCP servers run within Docker containers, ensuring safe execution isolated from the host environment.
- **Seamless Updates**: New additions to the catalog are automatically reflected in users' environments via Docker Desktop or the `docker mcp` CLI.
