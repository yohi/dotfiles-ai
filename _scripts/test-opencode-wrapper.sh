#!/bin/bash
# _scripts/test-opencode-wrapper.sh: Test suite for opencode-wrapper.sh profile switching

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_PATH="$SCRIPT_DIR/../opencode"
WRAPPER="$SCRIPT_DIR/opencode-wrapper.sh"

echo "🧪 Running opencode-wrapper.sh tests..."

get_profile_model() {
    local env_file="$1"
    (
        set -a
        source "$env_file"
        echo "$SISYPHUS_MODEL"
    )
}

EXPECTED_PERSONAL_MODEL=$(get_profile_model "$BASE_PATH/personal.env")
EXPECTED_WORK_MODEL=$(get_profile_model "$BASE_PATH/work.env")

if [ -z "$EXPECTED_PERSONAL_MODEL" ] || [ -z "$EXPECTED_WORK_MODEL" ]; then
    echo "❌ Failed: Could not load models from env files."
    exit 1
fi

TEST_SANDBOX=$(mktemp -d)
trap 'rm -rf "$TEST_SANDBOX"' EXIT

MOCK_BIN_DIR="$TEST_SANDBOX/bin"
mkdir -p "$MOCK_BIN_DIR"
MOCK_LOG="$TEST_SANDBOX/mock_opencode.log"
PKILL_LOG="$TEST_SANDBOX/mock_pkill.log"

cat << EOF > "$MOCK_BIN_DIR/opencode"
#!/bin/bash
echo "CALL: opencode \$@" >> "$MOCK_LOG"
echo "ENV_KIMI_K2_6=\${KIMI_K2_6:-unset}" >> "$MOCK_LOG"
echo "OPENCODE_CONFIG_DIR=\$OPENCODE_CONFIG_DIR" >> "$MOCK_LOG"
if [ -n "\$OPENCODE_CONFIG_DIR" ] && [ -d "\$OPENCODE_CONFIG_DIR" ] && [ -f "\$OPENCODE_CONFIG_DIR/oh-my-openagent.jsonc" ]; then
    echo "CONFIG_GENERATED=true" >> "$MOCK_LOG"
    cat "\$OPENCODE_CONFIG_DIR/oh-my-openagent.jsonc" > "$MOCK_LOG.generated_config"
fi
EOF
chmod +x "$MOCK_BIN_DIR/opencode"

cat << EOF > "$MOCK_BIN_DIR/pkill"
#!/bin/bash
echo "PKILL_CALL: pkill \$@" >> "$PKILL_LOG"
EOF
chmod +x "$MOCK_BIN_DIR/pkill"

export PATH="$MOCK_BIN_DIR:$PATH"

echo "  - Testing wrapper invocation with personal profile..."
rm -f "$MOCK_LOG" "$MOCK_LOG.generated_config" "$PKILL_LOG"
"$WRAPPER" personal run "hello" >/dev/null 2>&1

if grep -q "CALL: opencode --model $EXPECTED_PERSONAL_MODEL" "$MOCK_LOG" && \
   grep -q "CONFIG_GENERATED=true" "$MOCK_LOG" && \
   grep -q "$EXPECTED_PERSONAL_MODEL" "$MOCK_LOG.generated_config" && \
   grep -q "PKILL_CALL: pkill -f opencode.*--port" "$PKILL_LOG"; then
    echo "  ✅ Personal profile wrapper invocation & pkill cleanup verified"
else
    echo "  ❌ Failed: Personal profile wrapper invocation did not generate expected config/args or trigger pkill"
    cat "$MOCK_LOG" "$PKILL_LOG" 2>/dev/null || true
    exit 1
fi

echo "  - Testing wrapper env var unsetting across profile switch..."
rm -f "$MOCK_LOG" "$MOCK_LOG.generated_config" "$PKILL_LOG"
(
    export KIMI_K2_6="should_be_cleared_by_wrapper"
    "$WRAPPER" work run "hello" >/dev/null 2>&1
)

if grep -q "CALL: opencode --model $EXPECTED_WORK_MODEL" "$MOCK_LOG" && \
   grep -q "ENV_KIMI_K2_6=unset" "$MOCK_LOG" && \
   grep -q "PKILL_CALL: pkill -f opencode.*--port" "$PKILL_LOG"; then
    echo "  ✅ Work profile wrapper invocation & old env var unsetting (KIMI_K2_6) verified"
else
    echo "  ❌ Failed: Work profile wrapper invocation did not clear old profile env vars or pass expected args"
    cat "$MOCK_LOG" "$PKILL_LOG" 2>/dev/null || true
    exit 1
fi

echo "  - Testing ~/.omo/omo.jsonc preservation and restoration..."
MOCK_HOME="$TEST_SANDBOX/home"
mkdir -p "$MOCK_HOME/.omo"
echo '{"user_custom": true}' > "$MOCK_HOME/.omo/omo.jsonc"

(
    export HOME="$MOCK_HOME"
    export PATH="$MOCK_BIN_DIR:$PATH"
    "$WRAPPER" personal run "hello" >/dev/null 2>&1
)

if [ -f "$MOCK_HOME/.omo/omo.jsonc" ] && grep -q "user_custom" "$MOCK_HOME/.omo/omo.jsonc"; then
    echo "  ✅ Persistent ~/.omo/omo.jsonc was safely preserved and restored after execution"
else
    echo "  ❌ Failed: ~/.omo/omo.jsonc was lost or corrupted"
    exit 1
fi

echo "🎉 All wrapper end-to-end integration tests passed successfully!"
