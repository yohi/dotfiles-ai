# Fix Antigravity MCP Auth (Deprecated)

> [!CAUTION]
> **本ドキュメントはアーカイブ済みです。**
> この計画（MCP_GATEWAY_AUTH_TOKEN の設定、docker-mcp-gateway.service への環境変数追加、Authorization/Bearer ヘッダーの使用など）は、`stdio` ベースの構成への移行に伴い廃止されました。
> 現在の推奨される手順については、[_docs/plans/2026-03-24-revert-to-stdio.md](2026-03-24-revert-to-stdio.md) を参照してください。

## Implementation Plan (Superseded by stdio configuration)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the "unauthenticated" error when Antigravity connects to Docker MCP Gateway by setting up a Bearer token.

**Architecture:**
- Set `MCP_GATEWAY_AUTH_TOKEN` in the `docker-mcp-gateway` systemd service.
- Update `antigravity/mcp_config.json` to include the `Authorization` header with the same token.

**Tech Stack:** Bash, systemd, JSON.

---

### Task 1: Update setup script to support MCP_GATEWAY_AUTH_TOKEN

**Files:**
- Modify: `scripts/setup-docker-mcp.sh`

**Step 1: Add default token and environment variable to systemd service**

Update `scripts/setup-docker-mcp.sh` to define `MCP_GATEWAY_AUTH_TOKEN` (defaulting to a local-only token) and include it in the `[Service]` section of the generated `.service` file.

**Step 2: Verify the change in the script**

Check the `cat <<EOF > "$SERVICE_FILE"` block.

**Step 3: Commit**

```bash
git add _scripts/setup-docker-mcp.sh
git commit -m "fix(mcp): add auth token support to docker-mcp-gateway service"
```

### Task 2: Apply the updated service configuration

**Files:**
- Run: `scripts/setup-docker-mcp.sh`

**Step 1: Run the setup script**

Run: `./_scripts/setup-docker-mcp.sh`

**Step 2: Verify the service is running with the token**

Run: `systemctl --user show docker-mcp-gateway.service --property=Environment`
Expected: Should contain `MCP_GATEWAY_AUTH_TOKEN=...`

**Step 3: Test with curl**

Run: `curl -v -H "Authorization: Bearer <your-token>" http://localhost:10888/sse`
Expected: `200 OK` (with event-stream headers)

### Task 3: Update Antigravity configuration

**Files:**
- Modify: `antigravity/mcp_config.json`

**Step 1: Add Authorization header to the gateway server**

```json
{
  "mcpServers": {
    "gateway": {
      "url": "http://localhost:10888/sse",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```
*Note: Using 'url' instead of 'serverUrl' if 'url' is preferred by Antigravity.*

**Step 2: Commit**

```bash
git add antigravity/mcp_config.json
git commit -m "fix(antigravity): add authorization header to mcp_config.json"
```

### Task 4: Re-apply Antigravity setup

**Files:**
- Run: `make setup-antigravity`

**Step 1: Run the make command**

Run: `make setup-antigravity`
Expected: Symlink `~/.gemini/antigravity/mcp_config.json` is updated.

**Step 2: Verify symlink**

Run: `ls -l ~/.gemini/antigravity/mcp_config.json`
