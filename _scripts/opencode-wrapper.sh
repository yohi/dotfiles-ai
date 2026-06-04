#!/bin/bash
# opencode-wrapper.sh: Dynamic configuration generator for OpenCode

set -e

# --- Configuration ---
export PATH="$HOME/.opencode/bin:$PATH"
# Ensure auth data is loaded from the correct XDG data directory
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"


BASE_PATH="$REPO_ROOT/opencode"
TEMPLATE="$BASE_PATH/oh-my-openagent.jsonc.template"
REAL_CONFIG_DIR="$HOME/.config/opencode"

# --- Port Detection ---
PORT=""
if command -v ss >/dev/null 2>&1; then
    for p in {4090..4100}; do
        if ! ss -tln | grep -q ":$p " >/dev/null 2>&1; then
            PORT=$p
            break
        fi
    done
fi

# --- Profile Selection ---

PROFILE="personal"
if [[ "$1" == "work" || "$1" == "personal" ]]; then
    PROFILE="$1"
    shift
fi

ENV_FILE="$BASE_PATH/${PROFILE}.env"

if [ ! -f "$TEMPLATE" ]; then
    echo "❌ Error: Template not found at $TEMPLATE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  Warning: Profile env file not found at $ENV_FILE, using default environment"
fi

# --- Execution ---
TMP_DIR=$(mktemp -d)
# Ensure cleanup on any exit
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

# 1. Inherit other configurations (antigravity.json, AGENTS.md, etc.)
if [ -d "$REAL_CONFIG_DIR" ]; then
    # Create symlinks to all files in the real config dir except the one we are generating
    for f in "$REAL_CONFIG_DIR"/*; do
        filename=$(basename "$f")
        if [[ "$filename" != "oh-my-openagent.jsonc" && "$filename" != "oh-my-opencode.jsonc" ]]; then
            ln -s "$f" "$TMP_DIR/$filename" 2>/dev/null || true
        fi
    done
fi

# 2. Generate the dynamic config
(
    if [ -z "$TEMPLATE" ] || [ -z "$TMP_DIR" ]; then
        echo "❌ Error: TEMPLATE or TMP_DIR is not set" >&2
        exit 1
    fi

    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    # Use envsubst to process the template
    envsubst < "$TEMPLATE" > "$TMP_DIR/oh-my-openagent.jsonc"

    # After envsubst substituted values, check if any model configuration has an empty value
    if grep -qE '"model"\s*:\s*""' "$TMP_DIR/oh-my-openagent.jsonc"; then
        echo "❌ Error: Empty model configuration detected in generated JSONC" >&2
        exit 1
    fi
)

# 3. Run OpenCode
# Note: We use OPENCODE_CONFIG_DIR to point to our temporary directory
export OPENCODE_CONFIG_DIR="$TMP_DIR"

# Only use automatic port for the main agent loop (no arguments or starting with -)
# Subcommands like auth, mcp, doctor, etc. don't accept --port
if [[ -n "$PORT" && ( -z "$1" || "$1" == -* ) ]]; then
    echo "✅ Profile [${PROFILE}] | Port [${PORT}]"
    opencode --port "$PORT" "$@"
else
    echo "✅ Profile [${PROFILE}]"
    opencode "$@"
fi


