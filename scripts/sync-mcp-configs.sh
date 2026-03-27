#!/usr/bin/env bash
# scripts/sync-mcp-configs.sh
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
uv run --with-requirements "$REPO_ROOT/requirements.txt" "$REPO_ROOT/scripts/render-mcp-configs.py"

echo "==> Deploying Docker MCP catalog files..."
mkdir -p "$HOME/.docker/mcp/catalogs"
cp "$REPO_ROOT/mcp/catalog.json" "$HOME/.docker/mcp/catalog.json"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/config.yaml" > "$HOME/.docker/mcp/config.yaml"
cp "$REPO_ROOT/mcp/catalogs/bootstrap.yaml" "$HOME/.docker/mcp/catalogs/bootstrap.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/custom.yaml" "$HOME/.docker/mcp/catalogs/custom.yaml"

echo "✅ MCP configurations synchronized from mcp/servers.yaml"
