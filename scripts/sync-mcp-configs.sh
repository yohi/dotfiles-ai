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
