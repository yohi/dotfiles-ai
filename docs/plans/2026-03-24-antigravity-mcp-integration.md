# Antigravity MCP Integration Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Google Antigravity 本来の設定ディレクトリ `~/.gemini/antigravity/` に対して、Docker MCP Gateway への接続設定を含む `mcp_config.json` を配備し、OpenCode から切り離して管理する。

**Architecture:** `antigravity/` ディレクトリを新設し、`_mk/antigravity.mk` を介して `~/.gemini/antigravity/mcp_config.json` へのシンボリックリンクを管理します。

**Tech Stack:** Antigravity, MCP, Docker MCP Gateway, Makefile, Bash

---

## Task 1: Create Antigravity Configuration Directory and Files

**Files:**
- Create: `antigravity/mcp_config.json`

**Step 1: Create directory**
Run: `mkdir -p antigravity`

**Step 2: Write configuration file**
`antigravity/mcp_config.json` に以下を記述：
```json
{
  "mcpServers": {
    "gateway": {
      "url": "http://localhost:10888/sse"
    }
  }
}
```

**Step 3: Commit**
Run: `git add antigravity/ && git commit -m "feat(antigravity): add standalone mcp_config.json"`

---

## Task 2: Create Antigravity Makefile

**Files:**
- Create: `_mk/antigravity.mk`

**Step 1: Write Makefile contents**
`_mk/antigravity.mk` に `~/.gemini/antigravity/mcp_config.json` へのリンクターゲットを定義（既存の `opencode.mk` を参考）。

**Step 2: Commit**
Run: `git add _mk/antigravity.mk && git commit -m "feat(makefile): add antigravity management"`

---

## Task 3: Integrate with Root Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Include new Makefile**
`include _mk/antigravity.mk` を追加。

**Step 2: Add setup-antigravity dependency to setup-agents**
`setup-agents` ターゲットに `setup-antigravity` を追加。

**Step 3: Commit**
Run: `git add Makefile && git commit -m "feat(makefile): integrate antigravity into agent setup"`

---

## Task 4: Execute Setup and Verify Symlink

**Files:**
- Run: `make setup-antigravity`

**Step 1: Run setup**
Run: `make setup-antigravity`
Expected: `~/.gemini/antigravity/mcp_config.json` が作成され、シンボリックリンクが張られる。

**Step 2: Verify link**
Run: `ls -l ~/.gemini/antigravity/mcp_config.json`
Expected: リポジトリの `antigravity/mcp_config.json` を指している。

---

## Task 5: Final Validation in Antigravity

**Step 1: Check server availability**
Antigravity 本体の「Manage MCP Servers」で `gateway` が認識されているか確認。
(CLI検証が難しい場合は、設定ファイルの存在確認まで)

**Step 2: Cleanup Opencode Antigravity Config (Optionally)**
`opencode/antigravity.json` を削除、またはリネームして整理。
