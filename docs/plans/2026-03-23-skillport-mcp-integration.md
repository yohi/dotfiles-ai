# SkillPort & MCP Integration Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** SkillPort を MCP サーバーとして `docker-mcp-gateway` に統合し、各種エージェントからスキルを利用可能にする。

**Architecture:** `skillport-mcp` を `docker-mcp-gateway` の一つのサーバーとして設定し、`~/.docker/mcp/config.yaml` を介して動かします。

**Tech Stack:** SkillPort, skillport-mcp, Docker MCP Gateway, Bash, Make

---

### Task 1: SkillPort Tools Installation

**Files:**
- Run: `make skillport`

**Step 1: Execute installation**
Run: `make skillport`
Expected: `skillport` と `skillport-mcp` がインストールされ、シンボリックリンクが設定される。

**Step 2: Verify installation**
Run: `skillport --version && skillport-mcp --help`
Expected: 両コマンドが正常に応答する。

**Step 3: Commit (Marker update)**
Run: `git status`
Note: 冪等性マーカーが作成されるが、Git管理外。必要に応じてMakefileの変更があればコミット。

---

### Task 2: Update MCP Configuration Template

**Files:**
- Modify: `mcp/config.yaml`

**Step 1: Add skillport-mcp server definition**
`mcp/config.yaml` に以下を追加：
```yaml
  skillport:
    enabled: true
    command: skillport-mcp
    args: []
```

**Step 2: Verify YAML syntax**
Run: `python3 -c 'import yaml, sys; yaml.safe_load(sys.stdin)' < mcp/config.yaml`
Expected: 正常終了。

**Step 3: Commit**
Run: `git add mcp/config.yaml && git commit -m "feat(mcp): add skillport-mcp to config template"`

---

### Task 3: Sync Configuration to Docker MCP

**Files:**
- Run: `make setup-docker-mcp`

**Step 1: Run sync script**
Run: `make setup-docker-mcp`
Expected: `mcp/config.yaml` が `~/.docker/mcp/config.yaml` にコピーされる。

**Step 2: Verify target file**
Run: `cat ~/.docker/mcp/config.yaml | grep skillport -A 3`
Expected: 追加した設定が反映されている。

---

### Task 4: Restart Docker MCP Gateway Service

**Files:**
- Run: `systemctl --user restart docker-mcp-gateway.service`

**Step 1: Restart service**
Run: `systemctl --user restart docker-mcp-gateway.service`
Expected: サービスが正常に再起動する。

**Step 2: Check service logs**
Run: `journalctl --user -u docker-mcp-gateway -n 20`
Expected: `skillport-mcp` が正常に起動しているログを確認（またはエラーがないこと）。

---

### Task 5: Final Validation with Agents

**Step 1: List tools via official CLI or protocol**
Docker MCP Gateway が提供する公式コマンドでツールリストを確認。
Run: `docker mcp tools ls`
Expected: `skillport_search`, `skillport_read` などのツールが表示される。

または、`skillport-mcp` に対して直接 JSON-RPC リクエストを送り、ツール一覧を取得。
Run: `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | skillport-mcp`

**Step 2: Verify with current agent (if possible)**
エージェントに「利用可能なツールをリストして」と依頼し、`skillport` 関連のツールが含まれているか確認。
注: SSE ゲートウェイ経由の直接的な HTTP アクセス（curl 等）は環境に依存するため、上記の CLI またはプロトコルレベルのチェックを推奨。
