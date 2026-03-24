#!/usr/bin/env bash
# scripts/sync-mcp-configs.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ESCAPED_HOME=$(echo "$HOME" | sed 's/[&/\|]/\\&/g')

# 認証トークンの設定
if [ -f "$REPO_ROOT/.env" ]; then
    # Safer .env loading using a loop to avoid word splitting issues
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comments
        [[ -z "$line" ]] || [[ "$line" =~ ^# ]] && continue
        # Handle lines that start with export
        if [[ "$line" =~ ^export\  ]]; then
            eval "$line"
        else
            export "$line"
        fi
    done < "$REPO_ROOT/.env"
fi
AUTH_TOKEN="${MCP_GATEWAY_AUTH_TOKEN:-mcp_auth_token}"
SSE_URL="http://127.0.0.1:10888/sse"

# .gitignore の更新
if ! grep -q "ide/cursor/mcp.json" "$REPO_ROOT/.gitignore"; then
    echo "ide/cursor/mcp.json" >> "$REPO_ROOT/.gitignore"
    echo "==> Added ide/cursor/mcp.json to .gitignore"
fi

# すでにコミットされている場合は追跡を解除
if git ls-files --error-unmatch "ide/cursor/mcp.json" > /dev/null 2>&1; then
    git rm --cached "ide/cursor/mcp.json" > /dev/null 2>&1
    echo "==> Removed ide/cursor/mcp.json from git tracking"
fi

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
echo "==> Updating Cursor configuration via proxy..."
# Cursor must connect via the proxy script to handle authentication headers correctly
cat <<EOF > "$REPO_ROOT/ide/cursor/mcp.json"
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "command": "node",
      "args": [
        "$REPO_ROOT/scripts/mcp-sse-proxy.js",
        "$SSE_URL"
      ],
      "env": {
        "MCP_GATEWAY_AUTH_TOKEN": "$AUTH_TOKEN"
      }
    }
  }
}
EOF

echo "✅ MCP configurations synchronized (Strictly using Bearer token)."
