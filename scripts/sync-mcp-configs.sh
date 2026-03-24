#!/usr/bin/env bash
# scripts/sync-mcp-configs.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ESCAPED_HOME=$(echo "$HOME" | sed 's/[&/\|]/\\&/g')

# 認証トークンの設定
if [ -f "$REPO_ROOT/.env" ]; then
    # Load environment variables from .env
    # Use grep to remove comments and export
    export $(grep -v '^#' "$REPO_ROOT/.env" | xargs)
fi
AUTH_TOKEN="${MCP_GATEWAY_AUTH_TOKEN:-mcp_auth_token}"
SSE_URL="http://127.0.0.1:10888/sse"

# 1. カタログの配置
echo "==> Deploying MCP catalogs..."
mkdir -p "$HOME/.docker/mcp/catalogs"
sed "s|__HOME__|$ESCAPED_HOME|g" "$REPO_ROOT/mcp/catalogs/custom.yaml.template" > "$HOME/.docker/mcp/catalogs/custom.yaml"

# 2. Gemini CLI 設定の更新 (~/.gemini/settings.json)
# OAuth をバイパスするため authProviderType は含めず、ヘッダーのみを指定
echo "==> Updating Gemini CLI configuration..."
if [[ -f "$HOME/.gemini/settings.json" ]]; then
    jq '.mcpServers = {
        "docker-mcp-gateway": {
            "url": "'"$SSE_URL"'",
            "type": "sse",
            "headers": {
                "Authorization": "Bearer '"$AUTH_TOKEN"'"
            },
            "timeout": 30000
        }
    }' "$HOME/.gemini/settings.json" > "$HOME/.gemini/settings.json.tmp" && mv "$HOME/.gemini/settings.json.tmp" "$HOME/.gemini/settings.json"
fi

# 3. Antigravity 設定の更新 (antigravity/mcp_config.json)
echo "==> Updating Antigravity configuration..."
cat <<EOF > "$REPO_ROOT/antigravity/mcp_config.json"
{
  "mcpServers": {
    "gateway": {
      "serverUrl": "$SSE_URL",
      "type": "sse",
      "headers": {
        "Authorization": "Bearer $AUTH_TOKEN"
      }
    }
  }
}
EOF

# 4. Cursor 設定の更新 (ide/cursor/mcp.json)
echo "==> Updating Cursor configuration..."
cat <<EOF > "$REPO_ROOT/ide/cursor/mcp.json"
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "url": "$SSE_URL",
      "headers": {
        "Authorization": "Bearer $AUTH_TOKEN"
      }
    }
  }
}
EOF

echo "✅ MCP configurations synchronized (Strictly using Bearer token)."
