#!/bin/bash
# _scripts/test-opencode-wrapper.sh: Test suite for opencode-wrapper.sh profile switching

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_PATH="$SCRIPT_DIR/../opencode"
TEMPLATE="$SCRIPT_DIR/../opencode/oh-my-openagent.jsonc.template"

echo "🧪 Running opencode-wrapper.sh tests..."

TMP_CONFIG_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_CONFIG_DIR"' EXIT

echo "  - Testing personal profile env substitution..."
(
    set -a
    source "$BASE_PATH/personal.env" 2>/dev/null || true
    set +a
    envsubst '${SISYPHUS_MODEL} ${ULTRA_WORK_MODEL}' < "$TEMPLATE" > "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"
)

if grep -q "cloudflare-ai-gateway-custom/dynamic/kimi-k2.7-code" "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"; then
    echo "  ✅ Personal profile model (Kimi-K2.7) verified in template output"
else
    echo "  ❌ Failed: Personal profile model not found in template output"
    exit 1
fi

echo "  - Testing work profile env substitution..."
(
    set -a
    source "$BASE_PATH/work.env" 2>/dev/null || true
    set +a
    envsubst '${SISYPHUS_MODEL} ${ULTRA_WORK_MODEL}' < "$TEMPLATE" > "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"
)

if grep -q "amazon-bedrock/global.anthropic.claude-sonnet-5" "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"; then
    echo "  ✅ Work profile model (Bedrock Claude Sonnet 5) verified in template output"
else
    echo "  ❌ Failed: Work profile model not found in template output"
    exit 1
fi

echo "🎉 All opencode-wrapper tests passed successfully!"
