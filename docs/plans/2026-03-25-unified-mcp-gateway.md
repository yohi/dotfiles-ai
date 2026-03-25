# Unified MCP Gateway Implementation Plan (Legacy/Historical)

> **Note:** This plan assumes a direct `docker mcp gateway run` (stdio) approach, which has been superseded by the **SSE-resident Gateway** approach detailed in `docs/plans/2026-03-25-unified-mcp-gateway-sse.md`. This document is kept for historical reference.

**Goal:** 各ツールの個別の設定を廃止し、全てのMCPサーバーを Docker MCP Gateway 経由で利用するように一元化する。

**Architecture (Legacy):**
- `mcp/catalogs/custom.yaml` を Source of Truth とし、不足しているサーバー定義（Skillport等）を追加する。
- `scripts/sync-mcp-configs.sh` を作成し、各ツール（Gemini CLI, Antigravity, Cursor）の設定ファイルを一括更新する。
- 各ツールは `docker mcp gateway run` (stdio) のみを参照するように設定される。

**Tech Stack:** Bash, JSON/YAML processing (jq/yq or sed/awk)

---

## Task 1: サーバー定義の統合 (Source of Truth の作成)

**Files:**
- Modify: `mcp/catalogs/custom.yaml`

**Step 1: 既存の Cursor/Antigravity テンプレートからサーバー定義を抽出して追加する**
特に `skillport` などの独自サーバーの定義を追加。

```yaml
  skillport:
    description: Professional development and AI skill management.
    title: Skillport
    type: server
    image: python:3.11-slim
    command:
      - uvx
      - skillport-mcp@1.1.0
    env:
      SKILLPORT_SKILLS_DIR: /home/y_ohi/.skillport/skills
```

**Step 2: Commit**

```bash
git add mcp/catalogs/custom.yaml
git commit -m "feat(mcp): add skillport server definition to custom catalog"
```

### Task 2: 同期スクリプトの作成

**Files:**
- Create: `scripts/sync-mcp-configs.sh`
- Modify: `Makefile`

**Step 1: 同期スクリプトの実装**

```bash
#!/usr/bin/env bash
# scripts/sync-mcp-configs.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ESCAPED_HOME=$(echo "$HOME" | sed 's/[&/\|]/\\&/g')

# 1. カタログの配置
echo "==> Deploying MCP catalogs..."
mkdir -p "$HOME/.docker/mcp/catalogs"
cp "$REPO_ROOT/mcp/catalogs/custom.yaml" "$HOME/.docker/mcp/catalogs/custom.yaml"
# パスの展開
sed -i "s|__HOME__|$ESCAPED_HOME|g" "$HOME/.docker/mcp/catalogs/custom.yaml"

# 2. Gemini CLI 設定の更新 (~/.gemini/settings.json)
echo "==> Updating Gemini CLI configuration..."
# jq を使用して mcpServers を Gateway 1つだけに書き換える
if [[ -f "$HOME/.gemini/settings.json" ]]; then
    jq '.mcpServers = {
        "docker-mcp-gateway": {
            "command": "docker",
            "args": [
                "mcp", "gateway", "run",
                "--catalog", "'"$HOME"'/.docker/mcp/catalogs/bootstrap.yaml",
                "--catalog", "'"$HOME"'/.docker/mcp/catalogs/custom.yaml"
            ]
        }
    }' "$HOME/.gemini/settings.json" > "$HOME/.gemini/settings.json.tmp" && mv "$HOME/.gemini/settings.json.tmp" "$HOME/.gemini/settings.json"
fi

# 3. Antigravity 設定の更新 (antigravity/mcp_config.json)
echo "==> Updating Antigravity configuration..."
cat <<EOF > "$REPO_ROOT/antigravity/mcp_config.json"
{
  "mcpServers": {
    "gateway": {
      "command": "docker",
      "args": [
        "mcp", "gateway", "run",
        "--catalog", "$HOME/.docker/mcp/catalogs/bootstrap.yaml",
        "--catalog", "$HOME/.docker/mcp/catalogs/custom.yaml"
      ]
    }
  }
}
EOF

# 4. Cursor 設定の更新 (ide/cursor/mcp.json)
echo "==> Updating Cursor configuration..."
# Cursor は ${HOME} 変数などが使える場合があるが、まずは絶対パスでシンプルに
cat <<EOF > "$REPO_ROOT/ide/cursor/mcp.json"
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "command": "docker",
      "args": [
        "mcp", "gateway", "run",
        "--catalog", "$HOME/.docker/mcp/catalogs/bootstrap.yaml",
        "--catalog", "$HOME/.docker/mcp/catalogs/custom.yaml"
      ]
    }
  }
}
EOF

echo "✅ MCP configurations synchronized."
```

**Step 2: 実行権限の付与と Makefile への統合**

```bash
chmod +x scripts/sync-mcp-configs.sh
```

`Makefile` の `setup-agents` ターゲットなどに `scripts/sync-mcp-configs.sh` を追加。

**Step 3: Commit**

```bash
git add scripts/sync-mcp-configs.sh Makefile
git commit -m "feat(mcp): add config synchronization script"
```

### Task 3: 適用と検証

**Step 1: 同期スクリプトの実行**

Run: `./scripts/sync-mcp-configs.sh`

**Step 2: Gemini CLI での確認**

Run: `/mcp list` (Gemini 内で実行) または
Run: `gemini mcp list`

Expected: `docker-mcp-gateway` がリストされ、配下に複数のツール（Skillport, GitHub, Sequential Thinking等）が表示されること。

**Step 3: Commit**

```bash
# 生成されたファイルを必要に応じてコミット（テンプレート以外）
git add antigravity/mcp_config.json ide/cursor/mcp.json
git commit -m "chore(mcp): synchronized configurations for all agents"
```
