# Fix Antigravity SSE Session Proxy (Deprecated)

> [!CAUTION]
> **本ドキュメントはアーカイブ済みです。**
> Proxy サービスを利用したフローは `revert-to-stdio` 構成に置き換えられ、現在は使用されていません。
- Create a lightweight Node.js proxy (`scripts/mcp-sse-proxy.js`).
- The proxy maintains a single persistent connection to the Gateway's SSE endpoint and extracts the `sessionid`.
- Antigravity connects to the proxy at `http://localhost:10889/sse`.
- The proxy automatically appends the `sessionid` to all POST requests sent by Antigravity.

**Tech Stack:** Node.js (Standard library).

---

### Task 1: Create the SSE Session Proxy

**Files:**
- Create: `scripts/mcp-sse-proxy.js`

**Step 1: Write the proxy implementation**

```javascript
const http = require('http');

const GATEWAY_URL = 'http://localhost:10888/sse';
const PROXY_PORT = 10889;

let currentSessionId = null;

// Function to fetch session ID from Gateway
function updateSessionId() {
    const options = {
        headers: { 'Authorization': process.env.MCP_GATEWAY_AUTH_TOKEN ? `Bearer ${process.env.MCP_GATEWAY_AUTH_TOKEN}` : '' }
    };
    http.get(GATEWAY_URL, options, (res) => {
        res.on('data', (chunk) => {
            const str = chunk.toString();
            const match = str.match(/sessionid=([A-Z0-9]+)/);
            if (match) {
                currentSessionId = match[1];
                console.log(`[Proxy] Updated Session ID: ${currentSessionId}`);
            }
        });
    }).on('error', (e) => {
        console.error(`[Proxy] Failed to get session ID: ${e.message}`);
    });
}

// Start Proxy Server
http.createServer((req, res) => {
    if (!currentSessionId) updateSessionId();
    
    const targetUrl = new URL(GATEWAY_URL);
    if (currentSessionId) targetUrl.searchParams.set('sessionid', currentSessionId);
    
    const proxyReq = http.request(targetUrl, {
        method: req.method,
        headers: { ...req.headers, host: targetUrl.host }
    }, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
    });
    
    req.pipe(proxyReq);
    proxyReq.on('error', (e) => {
        res.writeHead(500);
        res.end(e.message);
    });
}).listen(PROXY_PORT, () => {
    console.log(`[Proxy] Listening on http://localhost:${PROXY_PORT}`);
    updateSessionId();
});
```

**Step 2: Commit**

```bash
git add scripts/mcp-sse-proxy.js
git commit -m "feat(mcp): add SSE session proxy to handle dynamic sessionids"
```

### Task 2: Update Setup Script to start Proxy

**Files:**
- Modify: `scripts/setup-docker-mcp.sh`

**Step 1: Add logic to start/restart the proxy as a background process or service**

For simplicity, update the systemd service to include the proxy or create a second service. Let's update `scripts/setup-docker-mcp.sh` to generate a `docker-mcp-proxy.service`.

**Step 2: Commit**

```bash
git add scripts/setup-docker-mcp.sh
git commit -m "feat(mcp): integrate proxy service into setup script"
```

### Task 3: Update Antigravity Config to point to Proxy

**Files:**
- Modify: `antigravity/mcp_config.json.template`

**Step 1: Point serverUrl to the proxy port (10889)**

```json
{
  "mcpServers": {
    "gateway": {
      "serverUrl": "http://localhost:10889/sse",
      "headers": {
        "Authorization": "Bearer __MCP_GATEWAY_AUTH_TOKEN__",
        "Content-Type": "application/json"
      }
    }
  }
}
```

**Step 2: Regenerate config and test**

Run: `./scripts/setup-docker-mcp.sh && make setup-antigravity`

**Step 3: Commit**

```bash
git add antigravity/mcp_config.json.template
git commit -m "fix(antigravity): point to proxy to resolve sessionid issue"
```
