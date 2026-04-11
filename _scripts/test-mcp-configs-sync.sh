#!/usr/bin/env bash
# _scripts/test-mcp-configs-sync.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running MCP Config Sync Verification Tests..."

# 1. Run the sync script
bash "$REPO_ROOT/_scripts/sync-mcp-configs.sh"

# 2. Verify Rendering
echo "==> Verifying Rendering..."
for f in "mcp/catalog.json.rendered" "mcp/config.yaml.rendered" "mcp/catalogs/custom.yaml"; do
    if [ ! -f "$REPO_ROOT/$f" ]; then
        echo "FAIL: Rendered file $f does not exist."
        exit 1
    fi

    # Check for placeholder substitution
    if grep -q "__HOME__" "$REPO_ROOT/$f"; then
        echo "FAIL: Placeholder __HOME__ found in $f"
        exit 1
    fi
    if grep -q "__REPO_ROOT__" "$REPO_ROOT/$f"; then
        echo "FAIL: Placeholder __REPO_ROOT__ found in $f"
        exit 1
    fi
    echo "PASS: $f rendered correctly."
done

# 3. Verify Deployment (Local User Directory)
echo "==> Verifying Deployment to ~/.docker/mcp/..."
DOCKER_MCP_DIR="$HOME/.docker/mcp"
for f in "catalog.json" "config.yaml"; do
    if [ ! -f "$DOCKER_MCP_DIR/$f" ]; then
        echo "FAIL: Deployed file $DOCKER_MCP_DIR/$f does not exist."
        exit 1
    fi
    # Compare with rendered source
    if ! diff "$REPO_ROOT/mcp/$f.rendered" "$DOCKER_MCP_DIR/$f" > /dev/null; then
        echo "FAIL: Deployed file $f does not match rendered source."
        exit 1
    fi
    echo "PASS: $f deployed correctly."
done

for f in "catalogs/bootstrap.yaml" "catalogs/custom.yaml"; do
    if [ ! -L "$DOCKER_MCP_DIR/$f" ]; then
        echo "FAIL: Symlink $DOCKER_MCP_DIR/$f does not exist."
        exit 1
    fi
    echo "PASS: Symlink $f verified."
done

# 4. Verify Systemd Service Rendering
echo "==> Verifying Systemd Service..."
SERVICE_FILE="$HOME/.config/systemd/user/docker-mcp-gateway.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo "FAIL: Service file $SERVICE_FILE does not exist."
    exit 1
fi
if grep -q "__ENABLED_SERVERS__" "$SERVICE_FILE"; then
    echo "FAIL: Placeholder __ENABLED_SERVERS__ found in $SERVICE_FILE"
    exit 1
fi

ENABLED_SERVERS=$(
    DOTFILES_AI_REPO_ROOT="$REPO_ROOT" uv run --with-requirements "$REPO_ROOT/requirements.txt" python3 - <<'PY'
import os, yaml
from pathlib import Path
config = yaml.safe_load(Path(os.environ["DOTFILES_AI_REPO_ROOT"]).joinpath("mcp/config.yaml").read_text(encoding="utf-8")) or {}
print(",".join(config.get("gateway", {}).get("enabled_servers", [])))
PY
)
if ! grep -q -e "--servers $ENABLED_SERVERS" "$SERVICE_FILE"; then
    echo "FAIL: Service file does not contain expected enabled servers: $ENABLED_SERVERS"
    exit 1
fi
echo "PASS: Systemd service verified."

echo "🎉 All MCP config sync tests passed successfully!"
