# Unified MCP Gateway (SSE Mode) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 各AIエージェントの個別の設定を廃止し、バックグラウンドで動作する Docker MCP Gateway (SSE) を経由して全てのMCPサーバーを一元利用できるようにする。

**Architecture:**
- `mcp/catalogs/custom.yaml.template` を Source of Truth とする。
- `docker-mcp-gateway.service` (systemd) を作成し、SSE モードで起動する。
- 全てのツール（Gemini, Antigravity, Cursor）を SSE URL (`http://localhost:10888/sse`) に向ける。
- Cursor 用の SSE -> stdio プロキシスクリプト (`scripts/mcp-sse-proxy.js`) を作成する。

**Tech Stack:** Bash, systemd, Node.js (for proxy script), JSON/YAML processing (jq/sed)

---

## Task 1: systemd サービスユニットの作成

**Files:**
- Create: `~/.config/systemd/user/docker-mcp-gateway.service`
- Modify: `scripts/setup-docker-mcp.sh`

**Step 1: systemd ユニットファイルの作成**

```ini
[Unit]
Description=Docker MCP Gateway
After=network.target docker.service

[Service]
Type=simple
EnvironmentFile=%h/dotfiles/components/dotfiles-ai/.env
WorkingDirectory=%h/dotfiles/components/dotfiles-ai
ExecStartPre=/usr/bin/make mcp-render
ExecStart=/usr/bin/docker mcp gateway run \
  --transport sse \
  --port 10888 \
  --catalog %h/.docker/mcp/catalogs/bootstrap.yaml \
  --catalog %h/.docker/mcp/catalogs/custom.yaml \
  --secrets .env \
  --quiet
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

**Step 2: セットアップスクリプトにサービス有効化ロジックを追加**

```bash
# _scripts/setup-docker-mcp.sh
echo "==> Setting up systemd service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO_ROOT/mcp/docker-mcp-gateway.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service
```

**Step 3: Commit**

```bash
git add mcp/docker-mcp-gateway.service _scripts/setup-docker-mcp.sh
git commit -m "feat(mcp): add systemd service for sse gateway"
```

## Task 2: Cursor 用 SSE プロキシスクリプトの作成

**Files:**
- Create: `scripts/mcp-sse-proxy.js`

**Step 1: プロキシスクリプトの実装**

```javascript
#!/usr/bin/env node
// _scripts/mcp-sse-proxy.js
// Proxies stdio to an MCP SSE server.

const { EventSource } = require('eventsource');
const axios = require('axios');

const sseUrl = process.argv[2] || 'http://localhost:10888/sse';
const token = process.env.MCP_GATEWAY_AUTH_TOKEN;

const eventSource = new EventSource(sseUrl, {
  headers: token ? { Authorization: `Bearer ${token}` } : {}
});

let postUrl = sseUrl; // fallback
eventSource.addEventListener('endpoint', (event) => {
  postUrl = event.data; // MCP仕様に従い endpoint URL を取得
});

eventSource.addEventListener('message', (event) => {
  try {
    const message = JSON.parse(event.data);
    process.stdout.write(JSON.stringify(message) + '\n');
  } catch (e) {
    console.error('Error parsing SSE message:', e.message);
  }
});

eventSource.onerror = (err) => {
  console.error('SSE Connection Error:', err);
  eventSource.close();
  process.exit(1);
};

let stdinBuffer = '';
process.stdin.on('data', async (data) => {
  stdinBuffer += data.toString();
  const lines = stdinBuffer.split('\n');
  stdinBuffer = lines.pop(); // keep partial line

  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const payload = JSON.parse(line);
      // Ensure we have a valid postUrl (might need to wait for 'endpoint' event if not fixed sseUrl)
      await axios.post(postUrl, payload, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
    } catch (e) {
      console.error('Error posting message to SSE:', e.message);
    }
  }
});
```

**Step 2: Commit**

```bash
git add _scripts/mcp-sse-proxy.js
git commit -m "feat(mcp): add sse-to-stdio proxy script for Cursor"
```

## Task 3: クライアント設定の一斉更新

**Files:**
- Modify: `~/.gemini/settings.json`
- Modify: `antigravity/mcp_config.json.template`
- Modify: `ide/cursor/mcp.json.template`

**Step 1: 全クライアントを SSE URL に更新**

```json
// Example: Gemini CLI
"mcpServers": {
  "docker-mcp-gateway": {
    "url": "http://localhost:10888/sse"
  }
}
```

**Step 2: 同期スクリプトの適用**

Run: `make setup-docker-mcp`

**Step 3: 検証**

Run: `gemini mcp list`
Expected: `docker-mcp-gateway` が `Connected` と表示されること。

**Step 4: Commit**

```bash
git add .
git commit -m "feat(mcp): switch all clients to sse gateway"
```
