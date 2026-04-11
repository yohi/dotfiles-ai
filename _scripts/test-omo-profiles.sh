#!/usr/bin/env bash
# _scripts/test-omo-profiles.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running oh-my-opencode profiles Tests..."

# We will test substitution by creating a temporary directory to act as the opencode directory
# so we don't mess up actual files or if they don't exist
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Copy the script and template to the temporary directory
cp "$REPO_ROOT/opencode/omo-profiles.sh" "$TMP_DIR/"
if [ -f "$REPO_ROOT/opencode/opencode.jsonc.template" ]; then
    cp "$REPO_ROOT/opencode/opencode.jsonc.template" "$TMP_DIR/"
else
    echo '{"token": "${MCP_GATEWAY_TOKEN}"}' > "$TMP_DIR/opencode.jsonc.template"
fi

if [ -f "$REPO_ROOT/opencode/oh-my-opencode.jsonc.template" ]; then
    cp "$REPO_ROOT/opencode/oh-my-opencode.jsonc.template" "$TMP_DIR/"
else
    echo '{"token": "${MCP_GATEWAY_TOKEN}"}' > "$TMP_DIR/oh-my-opencode.jsonc.template"
fi

# Export dummy token
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

if [ -f "opencode.jsonc" ]; then
    if ! grep -q "test_token_123" "opencode.jsonc"; then
        echo "FAIL: Token substitution failed in opencode.jsonc"
        cat "opencode.jsonc"
        exit 1
    fi
    if grep -q "\${MCP_GATEWAY_TOKEN}" "opencode.jsonc"; then
        echo "FAIL: Unresolved variable \${MCP_GATEWAY_TOKEN} found in opencode.jsonc"
        exit 1
    fi
    echo "PASS: Token substitution verified in opencode.jsonc"
fi

if [ -f "oh-my-opencode.jsonc" ]; then
    if grep -q "\${MCP_GATEWAY_TOKEN}" "oh-my-opencode.jsonc"; then
        echo "FAIL: Unresolved variable \${MCP_GATEWAY_TOKEN} found in oh-my-opencode.jsonc"
        exit 1
    fi
    echo "PASS: Token substitution verified in oh-my-opencode.jsonc (no unresolved variables)"
fi

echo "🎉 All oh-my-opencode profiles tests passed successfully!"
