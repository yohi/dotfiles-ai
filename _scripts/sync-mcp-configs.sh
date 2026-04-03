#!/usr/bin/env bash
# _scripts/sync-mcp-configs.sh
set -euo pipefail

# Preflight check for uv
if ! command -v uv > /dev/null 2>&1; then
    echo "Error: 'uv' is not installed. Please install it to proceed." >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ESCAPED_HOME=$(printf '%s' "$HOME" | sed 's/[&/|]/\\&/g')
ESCAPED_REPO_ROOT=$(printf '%s' "$REPO_ROOT" | sed 's/[&/|]/\\&/g')

echo "==> Rendering MCP catalogs..."
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/catalogs/custom.yaml.template" > "$REPO_ROOT/mcp/catalogs/custom.yaml"

echo "==> Rendering centralized MCP client configs..."
if [ -f "$REPO_ROOT/.env" ]; then
    # .env ファイルの内容を環境変数として安全にロード
    while IFS= read -r line || [[ -n "$line" ]]; do
        # 空行とコメントをスキップ
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        export "$line"
    done < "$REPO_ROOT/.env"
fi
uv run --with-requirements "$REPO_ROOT/requirements.txt" "$REPO_ROOT/_scripts/render-mcp-configs.py"

echo "==> Deploying Docker MCP catalog files..."
mkdir -p "$HOME/.docker/mcp/catalogs"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/catalog.json" > "$HOME/.docker/mcp/catalog.json"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/config.yaml" > "$HOME/.docker/mcp/config.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/bootstrap.yaml" "$HOME/.docker/mcp/catalogs/bootstrap.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/custom.yaml" "$HOME/.docker/mcp/catalogs/custom.yaml"

echo "==> Deploying Gemini CLI settings..."
mkdir -p "$HOME/.gemini/shared"
ln -sfn "$REPO_ROOT/gemini/settings.json" "$HOME/.gemini/settings.json"
ln -sfn "$REPO_ROOT/gemini/settings.json" "$HOME/.gemini/shared/settings.json"

echo "✅ MCP configurations synchronized from mcp/servers.yaml"

# Update systemd service with current token if it exists
SERVICE_FILE="$HOME/.config/systemd/user/docker-mcp-gateway.service"
if [ -f "$REPO_ROOT/.env" ] && [ -f "$SERVICE_FILE" ]; then
    # トークンを厳密に抽出 (行頭アンカー、引用符の除去)
    TOKEN=$(grep -E "^MCP_AUTH_TOKEN=" "$REPO_ROOT/.env" | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | xargs)
    if [ -n "$TOKEN" ]; then
        echo "🔄 Updating systemd service with current token..."
        # sed 用にトークンをエスケープ (バックスラッシュ, アンパサンド, スラッシュ)
        ESCAPED_TOKEN=$(printf '%s' "$TOKEN" | sed 's/[&/|]/\\&/g')
        sed -i "/Environment=\"MCP_GATEWAY_AUTH_TOKEN=/d" "$SERVICE_FILE"
        sed -i "/\[Service\]/a Environment=\"MCP_GATEWAY_AUTH_TOKEN=$ESCAPED_TOKEN\"" "$SERVICE_FILE"
        systemctl --user daemon-reload
    fi
fi
