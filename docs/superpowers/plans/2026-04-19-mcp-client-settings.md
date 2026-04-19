# MCP Client Configuration Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a comprehensive guide for configuring various AI tools to use the Unified SSE MCP Gateway and link it from the project's main AGENTS.md.

**Architecture:** Add a new Markdown documentation file and update existing project metadata to ensure discoverability.

**Tech Stack:** Markdown

---

### Task 1: Create MCP Settings Guide

**Files:**
- Create: `_docs/mcp-settings.md`

- [ ] **Step 1: Write the content for `_docs/mcp-settings.md`**

```markdown
# MCP Client 設定ガイド (Unified SSE Gateway)

このプロジェクトでは、Docker MCP Gateway を使用した **Unified SSE Gateway** (`http://localhost:10888/sse`) を通じて、すべての AI ツールで共通の MCP サーバーを利用します。

各ツールでの設定方法は以下の通りです。

## 1. Gemini CLI (SuperGemini)
Gemini CLI は `gemini/settings.json` を通じて MCP サーバーを管理します。

- **設定ファイルの場所**: `~/.gemini/settings.json` (プロジェクト内の `gemini/settings.json` から生成されます)
- **設定方法**:
  `mcpServers` オブジェクト内にサーバーを追加します。SSE 経由の場合は `url` プロパティを指定します。
  ```json
  {
    "mcpServers": {
      "my-server": {
        "url": "http://localhost:10888/sse?server=my-server"
      }
    }
  }
  ```

## 2. Claude Code
Claude Code は CLI コマンドまたは設定ファイルで SSE サーバーを追加できます。

- **CLIコマンド**:
  ```bash
  claude mcp add --transport sse <name> http://localhost:10888/sse?server=<name>
  ```
- **設定ファイルの場所**: `~/.claude/config.json`

## 3. Codex CLI
Codex CLI は TOML 形式の設定ファイルを使用します。

- **設定ファイルの場所**: `~/.codex/config.toml`
- **設定方法**:
  `[mcp_servers.<name>]` セクションを追加します。
  ```toml
  [mcp_servers.my-server]
  command = "curl"
  args = ["-s", "http://localhost:10888/sse?server=my-server"]
  ```
  *(注: Codex の SSE ネイティブ対応状況により、ブリッジコマンドが必要な場合があります)*

## 4. OpenCode (oh-my-opencode)
OpenCode は JSONC 形式の設定ファイルを使用します。

- **設定ファイルの場所**: `~/.config/opencode/opencode.jsonc`
- **設定方法**:
  `"mcp"` セクションに設定を追加します。
  ```jsonc
  "mcp": {
    "docker-mcp-gateway": {
      "type": "remote",
      "url": "http://127.0.0.1:10888/sse",
      "enabled": true
    }
  }
  ```

## 5. Cursor IDE
Cursor は設定 UI または JSON ファイルで設定できます。

- **GUI**: `Settings > Features > MCP Servers > Add New MCP Server`
  - **Type**: `SSE`
  - **URL**: `http://localhost:10888/sse?server=<name>`
- **設定ファイルの場所**: `~/.cursor/mcp.json`

## 6. Antigravity IDE
Antigravity は `mcp_config.json` を使用します。

- **設定ファイルの場所**: `~/.gemini/antigravity/mcp_config.json`
- **設定方法**:
  `serverUrl` プロパティを使用します。
  ```json
  {
    "mcpServers": {
      "my-server": {
        "serverUrl": "http://localhost:10888/sse?server=my-server"
      }
    }
  }
  ```
```

- [ ] **Step 2: Commit the new documentation**

```bash
git add _docs/mcp-settings.md
git commit -m "docs: add MCP client configuration guide for various tools"
```

### Task 2: Update AGENTS.md with Link to Guide

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add reference to `_docs/mcp-settings.md` in `AGENTS.md`**

```markdown
<<<<
### 📚 References
- [Docker MCP Gateway: Getting Started](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
====
### 📚 References
- [MCP Client 設定ガイド (Unified SSE Gateway)](./_docs/mcp-settings.md)
- [Docker MCP Gateway: Getting Started](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
>>>>
```

- [ ] **Step 2: Commit the change**

```bash
git add AGENTS.md
git commit -m "docs: link MCP client settings guide in AGENTS.md"
```
