# Revert to Stdio & Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean up all SSE-related changes and switch Antigravity configuration to use `stdio` (command-based).

**Architecture:**
- Restore `antigravity/mcp_config.json.template` to use `command` and `args`.
- Clean up `scripts/setup-docker-mcp.sh` to remove proxy and auth management.
- Remove `scripts/mcp-sse-proxy.js`.
- Keep `.gitignore` for safety.

---

### Task 1: Revert Antigravity Template to Stdio

**Files:**
- Modify: `antigravity/mcp_config.json.template`

**Step 1: Update the template to use 'command' and 'args'**

```json
{
  "mcpServers": {
    "gateway": {
      "command": "docker",
      "args": [
        "mcp",
        "gateway",
        "run",
        "--enable-all-servers",
        "--port",
        "10888",
        "--catalog", "__HOME__/.docker/mcp/catalogs/bootstrap.yaml",
        "--catalog", "__HOME__/.docker/mcp/catalogs/custom.yaml"
      ]
    }
  }
}
```

**Step 2: Commit**

```bash
git add antigravity/mcp_config.json.template
git commit -m "feat(antigravity): switch to stdio-based gateway execution"
```

### Task 2: Clean up Setup Script and Proxy

**Files:**
- Modify: `scripts/setup-docker-mcp.sh`
- Delete: `scripts/mcp-sse-proxy.js`

**Step 1: Remove proxy logic from setup script**

Remove all code related to generating/managing `docker-mcp-proxy.service` and the authentication token.

**Step 2: Remove the proxy script**

Run: `rm _scripts/mcp-sse-proxy.js`

**Step 3: Run the updated setup and make**

Run: `./_scripts/setup-docker-mcp.sh && make setup-antigravity`

**Step 4: Stop and remove unused services**

Run: `systemctl --user stop docker-mcp-proxy.service docker-mcp-gateway.service || true`
Run: `systemctl --user disable docker-mcp-proxy.service docker-mcp-gateway.service || true`

**Step 5: Commit**

```bash
git add _scripts/setup-docker-mcp.sh
git commit -m "chore(mcp): remove SSE proxy and gateway services"
```

### Task 3: Verify

**Step 1: Check generated config**

Run: `cat antigravity/mcp_config.json`
Expected: Shows `command: "docker", args: [...]`.
