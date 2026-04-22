#!/usr/bin/env bash
# _scripts/test-mcp-configs-sync.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running MCP Config Sync Verification Tests..."

# 1. Run the sync script
bash "$REPO_ROOT/_scripts/sync-mcp-configs.sh"

# 2. Verify Rendering
echo "==> Verifying Rendering..."
for f in "mcp/catalog.json" "mcp/config.yaml" "mcp/catalogs/custom.yaml"; do
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
    if ! diff "$REPO_ROOT/mcp/$f" "$DOCKER_MCP_DIR/$f" > /dev/null; then
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
if grep -q "__REPO_ROOT__" "$SERVICE_FILE"; then
    echo "FAIL: Placeholder __REPO_ROOT__ found in $SERVICE_FILE"
    exit 1
fi

ENABLED_SERVERS=$(
    if command -v uv > /dev/null 2>&1; then
        DOTFILES_AI_REPO_ROOT="$REPO_ROOT" uv run --with-requirements "$REPO_ROOT/requirements.txt" python3 - <<'PY'
import os, yaml, sys
from pathlib import Path
config_path = Path(os.environ["DOTFILES_AI_REPO_ROOT"]).joinpath("mcp/config.yaml")
config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
enabled = config.get("gateway", {}).get("enabled_servers")
if enabled is not None and (not isinstance(enabled, list) or not all(isinstance(i, str) for i in enabled)):
    print(f"Error: gateway.enabled_servers in {config_path} must be a list of strings", file=sys.stderr)
    sys.exit(1)
print(",".join(enabled or []))
PY
    else
        DOTFILES_AI_REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import os, yaml, sys
from pathlib import Path
config_path = Path(os.environ["DOTFILES_AI_REPO_ROOT"]).joinpath("mcp/config.yaml")
config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
enabled = config.get("gateway", {}).get("enabled_servers")
if enabled is not None and (not isinstance(enabled, list) or not all(isinstance(i, str) for i in enabled)):
    print(f"Error: gateway.enabled_servers in {config_path} must be a list of strings", file=sys.stderr)
    sys.exit(1)
print(",".join(enabled or []))
PY
    fi
)
if ! grep -Fq -e "--servers $ENABLED_SERVERS" "$SERVICE_FILE"; then
    echo "FAIL: Service file does not contain expected enabled servers: $ENABLED_SERVERS"
    exit 1
fi
echo "PASS: Systemd service verified."

echo "🎉 All MCP config sync tests passed successfully!"
