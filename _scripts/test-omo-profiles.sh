#!/usr/bin/env bash
# _scripts/test-omo-profiles.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure envsubst is available
if ! command -v envsubst >/dev/null 2>&1; then
    echo "❌ Error: envsubst command not found. Please install gettext package." >&2
    exit 1
fi

echo "Running oh-my-opencode profiles Tests..."

# We will test substitution by creating a temporary directory to act as the opencode directory
# so we don't mess up actual files or if they don't exist
TMP_PARENT=$(mktemp -d)
trap 'rm -rf "$TMP_PARENT"' EXIT

# Create an isolated repo structure so ../.env resolution is safe
TMP_REPO="$TMP_PARENT/repo"
TMP_DIR="$TMP_REPO/opencode"
mkdir -p "$TMP_DIR"

# Copy the script to the temporary directory
cp "$REPO_ROOT/opencode/omo-profiles.sh" "$TMP_DIR/"

# Create minimal test templates
echo '{"token": "${MCP_GATEWAY_TOKEN}", "package": "${FLIXA_NPM_PACKAGE}"}' > "$TMP_DIR/opencode.jsonc.template"
echo '{"token": "${MCP_GATEWAY_TOKEN}", "package": "${FLIXA_NPM_PACKAGE}"}' > "$TMP_DIR/oh-my-opencode.jsonc.template"

# Export dummy token and package
export MCP_GATEWAY_TOKEN="test_token_123"
export FLIXA_NPM_PACKAGE="test_package_123"

# Run profile setter
cd "$TMP_DIR"
source "omo-profiles.sh"
omo-set-profile speed >/dev/null

# Verify substitution
if [ ! -f "opencode.jsonc" ]; then
    echo "FAIL: opencode.jsonc not generated"
    exit 1
fi

if ! grep -q "test_token_123" "opencode.jsonc"; then
    echo "FAIL: Token substitution failed in opencode.jsonc"
    exit 1
fi
if ! grep -q "test_package_123" "opencode.jsonc"; then
    echo "FAIL: Package substitution failed in opencode.jsonc"
    exit 1
fi
if grep -q "\${" "opencode.jsonc"; then
    echo "FAIL: Unresolved variable found in opencode.jsonc"
    exit 1
fi
echo "PASS: Variable substitution verified in opencode.jsonc"

if [ -f "oh-my-opencode.jsonc" ]; then
    if ! grep -q "test_package_123" "oh-my-opencode.jsonc"; then
        echo "FAIL: Package substitution failed in oh-my-opencode.jsonc"
        exit 1
    fi
    # Verify token is not empty
    token_val=$(sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "oh-my-opencode.jsonc" || true)
    if [ -z "$token_val" ]; then
        echo "FAIL: MCP_GATEWAY_TOKEN resolved to empty string"
        exit 1
    fi
    if grep -q "\${" "oh-my-opencode.jsonc"; then
        echo "FAIL: Unresolved variable found in oh-my-opencode.jsonc"
        exit 1
    fi
    echo "PASS: Variable substitution verified in oh-my-opencode.jsonc"
else
    echo "FAIL: oh-my-opencode.jsonc not generated"
    exit 1
fi

echo "🎉 All oh-my-opencode profiles tests passed successfully!"
