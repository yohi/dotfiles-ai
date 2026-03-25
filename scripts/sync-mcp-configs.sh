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
        
        # Remove 'export ' prefix if exists
        line_no_prefix="${line#export }"
        
        # Extract key and value safely to avoid SC2163 and eval
        if [[ "$line_no_prefix" == *"="* ]]; then
            key="${line_no_prefix%%=*}"
            val="${line_no_prefix#*=}"
            # Strip surrounding quotes from value
            val="${val%\"}"
            val="${val#\"}"
            val="${val%\'}"
            val="${val#\'}"
            export "$key=$val"
        fi
    done < "$REPO_ROOT/.env"
fi

AUTH_TOKEN="${MCP_GATEWAY_AUTH_TOKEN:-}"
if [ -z "$AUTH_TOKEN" ]; then
    echo "❌ Error: MCP_GATEWAY_AUTH_TOKEN is not set in .env or environment." >&2
    exit 1
fi
SSE_URL="http://127.0.0.1:10888/sse"

# .gitignore の更新
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    if ! grep -q "ide/cursor/mcp.json" "$REPO_ROOT/.gitignore"; then
        echo "ide/cursor/mcp.json" >> "$REPO_ROOT/.gitignore"
        echo "==> Added ide/cursor/mcp.json to .gitignore"
    fi

    # すでにコミットされている場合は追跡を解除
    if git ls-files --error-unmatch "ide/cursor/mcp.json" > /dev/null 2>&1; then
        git rm --cached "ide/cursor/mcp.json" > /dev/null 2>&1
        echo "==> Removed ide/cursor/mcp.json from git tracking"
    fi
else
    echo "==> Not inside a git repository, skipping .gitignore updates and tracking removal"
fi

# 1. カタログの配置
echo "==> Deploying MCP catalogs..."
TARGET_CUSTOM_YAML="$HOME/.docker/mcp/catalogs/custom.yaml"
mkdir -p "$(dirname "$TARGET_CUSTOM_YAML")"

# If the target is a symlink, resolve it to avoid clobbering the link itself or its source
if [ -L "$TARGET_CUSTOM_YAML" ]; then
    # Portable path resolution: use realpath if available, fallback to Python
    if command -v realpath > /dev/null 2>&1; then
        RESOLVED_TARGET=$(realpath "$TARGET_CUSTOM_YAML")
    else
        RESOLVED_TARGET=$(python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$TARGET_CUSTOM_YAML")
    fi
    echo "==> Target is a symlink, writing to resolved path: $RESOLVED_TARGET"
    mkdir -p "$(dirname "$RESOLVED_TARGET")"
    sed "s|__HOME__|$ESCAPED_HOME|g" "$REPO_ROOT/mcp/catalogs/custom.yaml.template" > "$RESOLVED_TARGET"
else
    sed "s|__HOME__|$ESCAPED_HOME|g" "$REPO_ROOT/mcp/catalogs/custom.yaml.template" > "$TARGET_CUSTOM_YAML"
fi

# 2. Gemini CLI 設定の更新 (~/.gemini/settings.json)
# OAuth をバイパスするため authProviderType は含めず、ヘッダーのみを指定
echo "==> Updating Gemini CLI configuration..."
if [[ -f "$HOME/.gemini/settings.json" ]]; then
    jq --arg sseUrl "$SSE_URL" --arg auth "Bearer $AUTH_TOKEN" \
        '.mcpServers["docker-mcp-gateway"] = {
            "url": $sseUrl,
            "type": "sse",
            "headers": {
                "Authorization": $auth
            },
            "timeout": 30000
        }' "$HOME/.gemini/settings.json" > "$HOME/.gemini/settings.json.tmp" && mv "$HOME/.gemini/settings.json.tmp" "$HOME/.gemini/settings.json"
fi

# 3. Antigravity 設定の更新 (antigravity/mcp_config.json)
echo "==> Updating Antigravity configuration from template..."
sed -e "s|__MCP_AUTH_TOKEN__|$AUTH_TOKEN|g" \
    -e "s|__SSE_URL__|$SSE_URL|g" \
    "$REPO_ROOT/antigravity/mcp_config.json.template" > "$REPO_ROOT/antigravity/mcp_config.json"

# 4. Cursor 設定の更新 (ide/cursor/mcp.json)
echo "==> Updating Cursor configuration via proxy from template..."
sed -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
    -e "s|__MCP_AUTH_TOKEN__|$AUTH_TOKEN|g" \
    -e "s|__SSE_URL__|$SSE_URL|g" \
    "$REPO_ROOT/ide/cursor/mcp.json.template" > "$REPO_ROOT/ide/cursor/mcp.json"

echo "✅ MCP configurations synchronized (Strictly using Bearer token)."
