# Fix MCP Review Comments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** コードレビューでの指摘事項（セキュリティ、移植性、仕様準拠）を全て修正し、信頼性の高い MCP 環境を構築する。

**Architecture:**
- 認証トークンを動的生成し `.env` で一元管理する。
- SSE プロキシを MCP 仕様に準拠させ、`endpoint` イベントを正しく扱うようにする。
- シンボリックリンクやテンプレートの不整合を解消し、ポータビリティを向上させる。

**Tech Stack:** Bash, Node.js, systemd, git

---

## Task 1: トークンの動的生成とセキュリティ強化

**Files:**
- Modify: `scripts/setup-docker-mcp.sh`
- Modify: `mcp/docker-mcp-gateway.service`
- Modify: `scripts/sync-mcp-configs.sh`

**Step 1: setup スクリプトでトークンを自動生成するロジックを追加**

```bash
# scripts/setup-docker-mcp.sh 内
if ! grep -q "MCP_GATEWAY_AUTH_TOKEN" "$REPO_ROOT/.env" 2>/dev/null; then
    TOKEN=$(openssl rand -hex 32)
    echo "MCP_GATEWAY_AUTH_TOKEN=$TOKEN" >> "$REPO_ROOT/.env"
fi
```

**Step 2: systemd サービスで EnvironmentFile を使用するように修正**

```ini
# mcp/docker-mcp-gateway.service
[Service]
EnvironmentFile=%h/dotfiles/components/dotfiles-ai/.env
ExecStart=/usr/bin/docker mcp gateway run ... (トークンのハードコードを削除)
```

**Step 3: 同期スクリプトで .env からトークンを読み込むように修正**

```bash
# scripts/sync-mcp-configs.sh
# Extract MCP_GATEWAY_AUTH_TOKEN from .env safely
MCP_GATEWAY_AUTH_TOKEN=$(grep -m1 '^MCP_GATEWAY_AUTH_TOKEN=' "$REPO_ROOT/.env" | cut -d'=' -f2- | tr -d '"'\''')
AUTH_TOKEN="$MCP_GATEWAY_AUTH_TOKEN"
```

**Step 4: Commit**

```bash
git add scripts/setup-docker-mcp.sh mcp/docker-mcp-gateway.service scripts/sync-mcp-configs.sh
git commit -m "chore(mcp): dynamic auth token generation and security hardening"
```

## Task 2: SSE プロキシの仕様準拠 (endpoint対応)

**Files:**
- Modify: `scripts/mcp-sse-proxy.js`

**Step 1: endpoint イベントを待機して POST 先を決定するロジックを実装**

```javascript
let postUrl = sseUrl; // fallback
eventSource.addEventListener('endpoint', (event) => {
    postUrl = event.data; // MCP仕様に従い endpoint URL を取得
});
```

**Step 2: エラーハンドリングの追加**

```javascript
eventSource.onerror = (err) => {
    console.error('SSE Connection Error:', err);
    process.exit(1);
};
```

**Step 3: Commit**

```bash
git add scripts/mcp-sse-proxy.js
git commit -m "fix(mcp): comply with SSE transport spec for endpoint discovery"
```

## Task 3: ポータビリティと一貫性の向上

**Files:**
- Modify: `antigravity/mcp_config.json.template`
- Modify: `gemini/supergemini/supergemini`
- Run: `git rm --cached mcp/catalogs/custom.yaml`

**Step 1: Antigravity テンプレートのキー名を修正**

```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "serverUrl": "http://127.0.0.1:10888/sse",
      "type": "sse",
      "headers": {
        "Authorization": "Bearer __MCP_AUTH_TOKEN__"
      }
    }
  }
}
```

**Step 2: 絶対パスのシンボリックリンクを相対パスに修正**

```bash
# gemini/supergemini/supergemini がリンクなら、相対パスで作り直す
ln -sf ./__main__.py gemini/supergemini/supergemini
```

**Step 3: gitignore 対象ファイルのキャッシュ削除**

Run: `git rm --cached mcp/catalogs/custom.yaml`

**Step 4: Commit**

```bash
git add antigravity/mcp_config.json.template gemini/supergemini/supergemini
git commit -m "chore(mcp): improve portability and fix configuration consistency"
```

## Task 4: 全体の検証

**Step 1: 再セットアップの実行**

Run: `make setup-docker-mcp`

**Step 2: 接続確認**

Run: `gemini mcp list`
Expected: `✓ Connected`

**Step 3: Commit (Final)**

```bash
git add .
git commit -m "chore(mcp): finalize all review fixes"
```
