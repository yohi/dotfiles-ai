# Fix Antigravity SSE Auth (Deprecated)

> [!CAUTION]
> **本ドキュメントはアーカイブ済みです。**
> この計画（.env ファイルを使用した MCP_GATEWAY_AUTH_TOKEN の管理、scripts/setup-docker-mcp.sh の更新など）は、`stdio` ベースの構成への移行に伴い廃止されました。
> 現在の推奨される手順については、[_docs/plans/2026-03-24-revert-to-stdio.md](2026-03-24-revert-to-stdio.md) を参照してください。

## Implementation Plan (Superseded by stdio configuration)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store the MCP Gateway auth token in `.env`, ignore it via `.gitignore`, and use it for SSE auth.

**Architecture:**
- Use a root `.env` file to store `MCP_GATEWAY_AUTH_TOKEN`.
- Update `scripts/setup-docker-mcp.sh` to generate/read this file.
- Add `.env` to `.gitignore` to prevent accidental commits.
- Generate `antigravity/mcp_config.json` from its template using the token in `.env`.

---

### Task 1: Update .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Add .env to .gitignore**

Ensure `.env` is ignored by git.

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .env file"
```

### Task 2: Update setup script to use .env

**Files:**
- Modify: `scripts/setup-docker-mcp.sh`

**Step 1: Change AUTH_TOKEN_FILE to .env**

Update the script to use `.env` in the repository root instead of `~/.mcp_secrets.env`.

**Step 2: Improve token generation logic**

Ensure it appends to `.env` if it exists, or creates it if it doesn't, specifically managing the `MCP_GATEWAY_AUTH_TOKEN` key.

**Step 3: Update systemd service generation**

Ensure the service still gets the token correctly (either by sourcing `.env` or injecting it).

**Step 4: Commit**

```bash
git add _scripts/setup-docker-mcp.sh
git commit -m "feat(mcp): use root .env for auth token storage"
```

### Task 3: Verify and Test

**Step 1: Run the setup**

Run: `./_scripts/setup-docker-mcp.sh && make setup-antigravity`

**Step 2: Check .env content**

Run: `grep MCP_GATEWAY_AUTH_TOKEN .env`

**Step 3: Test connection**

Run: `export $(grep -v '^#' .env | xargs) && curl -v -H "Authorization: Bearer $MCP_GATEWAY_AUTH_TOKEN" http://localhost:10888/sse --max-time 2`
