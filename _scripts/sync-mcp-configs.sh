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

echo "==> Preparing config files from templates..."
# Template to actual file mapping (only if actual file doesn't exist)
declare -A TEMPLATES=(
    ["gemini/settings.json.template"]="gemini/settings.json"
    ["opencode/opencode.jsonc.template"]="opencode/opencode.jsonc"
    ["opencode/oh-my-opencode.jsonc.template"]="opencode/oh-my-opencode.jsonc"
    ["ide/vscode/settings.json.template"]="ide/vscode/settings.json"
    ["claude/claude-settings.json.template"]="claude/claude-settings.json"
)

for src in "${!TEMPLATES[@]}"; do
    dst="${TEMPLATES[$src]}"
    if [ -f "$REPO_ROOT/$src" ] && [ ! -f "$REPO_ROOT/$dst" ]; then
        cp "$REPO_ROOT/$src" "$REPO_ROOT/$dst"
        echo "✅ Created $dst from template."
    fi
done

echo "==> Rendering MCP catalogs..."
mkdir -p "$REPO_ROOT/mcp/catalogs"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/catalogs/custom.yaml.template" > "$REPO_ROOT/mcp/catalogs/custom.yaml"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/catalog.json" > "$REPO_ROOT/mcp/catalog.json.rendered"
sed -e "s|__HOME__|$ESCAPED_HOME|g" -e "s|__REPO_ROOT__|$ESCAPED_REPO_ROOT|g" "$REPO_ROOT/mcp/config.yaml" > "$REPO_ROOT/mcp/config.yaml.rendered"

echo "==> Rendering centralized MCP configs..."
if [ -f "$REPO_ROOT/.env" ]; then
    # .env ファイルの内容を環境変数として安全にロード
    set -o allexport
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.env"
    set +o allexport
fi
uv run --with-requirements "$REPO_ROOT/requirements.txt" "$REPO_ROOT/_scripts/render-mcp-configs.py"

echo "==> Deploying Docker MCP catalog files..."
DOCKER_MCP_DIR="$HOME/.docker/mcp"
mkdir -p "$DOCKER_MCP_DIR/catalogs"

# Verify rendered files exist before copying
for f in "catalog.json.rendered" "config.yaml.rendered"; do
    if [ ! -f "$REPO_ROOT/mcp/$f" ]; then
        echo "Error: Rendered file $REPO_ROOT/mcp/$f not found. Rendering failed." >&2
        exit 1
    fi
done

cp "$REPO_ROOT/mcp/catalog.json.rendered" "$DOCKER_MCP_DIR/catalog.json"
cp "$REPO_ROOT/mcp/config.yaml.rendered" "$DOCKER_MCP_DIR/config.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/bootstrap.yaml" "$DOCKER_MCP_DIR/catalogs/bootstrap.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/custom.yaml" "$DOCKER_MCP_DIR/catalogs/custom.yaml"

echo "==> Deploying Gemini CLI settings..."
mkdir -p "$HOME/.gemini/shared"
ln -sfn "$REPO_ROOT/gemini/settings.json" "$HOME/.gemini/settings.json"
ln -sfn "$REPO_ROOT/gemini/settings.json" "$HOME/.gemini/shared/settings.json"

echo "✅ MCP configurations synchronized from mcp/servers.yaml and mcp/config.yaml"

SERVICE_FILE="$HOME/.config/systemd/user/docker-mcp-gateway.service"
mkdir -p "$(dirname "$SERVICE_FILE")"
ENABLED_SERVERS=$(
    uv run --with-requirements "$REPO_ROOT/requirements.txt" python3 - <<'PY'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("mcp/config.yaml").read_text(encoding="utf-8")) or {}
servers = config.get("gateway", {}).get("enabled_servers", [])
if not isinstance(servers, list) or not all(isinstance(item, str) for item in servers):
    raise SystemExit("Invalid mcp/config.yaml: gateway.enabled_servers must be a list of strings")
print(",".join(servers))
PY
)
ESCAPED_ENABLED_SERVERS=$(printf '%s' "$ENABLED_SERVERS" | sed 's/[&/|]/\\&/g')
sed \
    -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
    -e "s|__ENABLED_SERVERS__|$ESCAPED_ENABLED_SERVERS|g" \
    "$REPO_ROOT/mcp/docker-mcp-gateway.service" > "$SERVICE_FILE"

# Update systemd service with current token if it exists
if [ -f "$REPO_ROOT/.env" ] && [ -f "$SERVICE_FILE" ]; then
    # トークンを抽出 (grep がマッチしなくても pipefail で落ちないように || true を追加)
    TOKEN=$(grep -E "^[[:space:]]*MCP_GATEWAY_TOKEN=" "$REPO_ROOT/.env" | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | xargs || true)
    if [ -z "$TOKEN" ]; then
        TOKEN=$(grep -E "^[[:space:]]*MCP_AUTH_TOKEN=" "$REPO_ROOT/.env" | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | xargs || true)
    fi
    if [ -n "$TOKEN" ]; then
        echo "🔄 Updating systemd service with current token..."
        # sed 用にトークンをエスケープ (バックスラッシュ, アンパサンド, スラッシュ)
        ESCAPED_TOKEN=$(printf '%s' "$TOKEN" | sed 's/[&/|]/\\&/g')
        sed -i "/Environment=\"MCP_GATEWAY_AUTH_TOKEN=/d" "$SERVICE_FILE"
        sed -i "/Environment=\"MCP_GATEWAY_TOKEN=/d" "$SERVICE_FILE"
        sed -i "/\[Service\]/a Environment=\"MCP_GATEWAY_TOKEN=$ESCAPED_TOKEN\"" "$SERVICE_FILE"
        sed -i "/\[Service\]/a Environment=\"MCP_GATEWAY_AUTH_TOKEN=$ESCAPED_TOKEN\"" "$SERVICE_FILE"
        systemctl --user daemon-reload
    fi
fi
