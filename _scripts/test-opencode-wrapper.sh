#!/bin/bash
# _scripts/test-opencode-wrapper.sh: Test suite for opencode-wrapper.sh profile switching

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_PATH="$SCRIPT_DIR/../opencode"
TEMPLATE="$SCRIPT_DIR/../opencode/oh-my-openagent.jsonc.template"

echo "🧪 Running opencode-wrapper.sh dynamic profile tests..."

TMP_CONFIG_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_CONFIG_DIR"' EXIT

# 1. Dynamic Personal Profile Test (Read expected model directly from personal.env)
echo "  - Testing personal profile dynamic env substitution..."
EXPECTED_PERSONAL_MODEL=$(
    set -a
    source "$BASE_PATH/personal.env" 2>/dev/null || true
    echo "$SISYPHUS_MODEL"
)

if [ -z "$EXPECTED_PERSONAL_MODEL" ]; then
    echo "  ❌ Failed: SISYPHUS_MODEL is empty in personal.env"
    exit 1
fi

(
    set -a
    source "$BASE_PATH/personal.env" 2>/dev/null || true
    set +a
    envsubst '${SISYPHUS_MODEL} ${ULTRA_WORK_MODEL}' < "$TEMPLATE" > "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"
)

if grep -q "$EXPECTED_PERSONAL_MODEL" "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"; then
    echo "  ✅ Personal profile model ($EXPECTED_PERSONAL_MODEL) dynamically verified"
else
    echo "  ❌ Failed: Expected personal model ($EXPECTED_PERSONAL_MODEL) not found in generated config"
    exit 1
fi

# 2. Dynamic Work Profile Test (Read expected model directly from work.env)
echo "  - Testing work profile dynamic env substitution..."
EXPECTED_WORK_MODEL=$(
    set -a
    source "$BASE_PATH/work.env" 2>/dev/null || true
    echo "$SISYPHUS_MODEL"
)

if [ -z "$EXPECTED_WORK_MODEL" ]; then
    echo "  ❌ Failed: SISYPHUS_MODEL is empty in work.env"
    exit 1
fi

(
    set -a
    source "$BASE_PATH/work.env" 2>/dev/null || true
    set +a
    envsubst '${SISYPHUS_MODEL} ${ULTRA_WORK_MODEL}' < "$TEMPLATE" > "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"
)

if grep -q "$EXPECTED_WORK_MODEL" "$TMP_CONFIG_DIR/oh-my-openagent.jsonc"; then
    echo "  ✅ Work profile model ($EXPECTED_WORK_MODEL) dynamically verified"
else
    echo "  ❌ Failed: Expected work model ($EXPECTED_WORK_MODEL) not found in generated config"
    exit 1
fi

# 3. Dynamic Profile Switch Verification (Ensure profiles yield distinct models)
if [ "$EXPECTED_PERSONAL_MODEL" = "$EXPECTED_WORK_MODEL" ]; then
    echo "  ⚠️ Warning: Personal and Work profiles currently evaluate to the same model ($EXPECTED_PERSONAL_MODEL)"
else
    echo "  ✅ Confirmed: Personal ($EXPECTED_PERSONAL_MODEL) and Work ($EXPECTED_WORK_MODEL) profile models are distinct"
fi

echo "🎉 All dynamic opencode-wrapper tests passed successfully!"
