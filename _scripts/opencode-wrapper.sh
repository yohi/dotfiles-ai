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

PROFILE="${PROFILE:-personal}"
if [[ "$1" == "work" || "$1" == "personal" ]]; then
    PROFILE="$1"
    shift
    # Kill any existing running server to force fresh config loading with the requested profile
    pkill -f "opencode --port" 2>/dev/null || true
    sleep 0.5
fi

ENV_FILE="$BASE_PATH/${PROFILE}.env"

if [ ! -f "$TEMPLATE" ]; then
    echo "❌ Error: Template not found at $TEMPLATE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  Warning: Profile env file not found at $ENV_FILE, using default environment"
fi

if [ -f "$ENV_FILE" ]; then
    # Clear all model profile env vars across work.env and personal.env so switching profiles doesn't keep old values
    ALL_PROFILE_VARS=$(grep -oP '^[A-Z0-9_]+=' "$BASE_PATH"/*.env 2>/dev/null | cut -d: -f2 | cut -d= -f1 | sort -u)
    if [ -n "$ALL_PROFILE_VARS" ]; then
        unset $ALL_PROFILE_VARS 2>/dev/null || true
    fi
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

export SKILLPORT_SKILLS_DIR="${SKILLPORT_SKILLS_DIR:-$REPO_ROOT/.agents/skills}"

# Ensure plugin's static config unification file doesn't override dynamic profile switching
rm -f "$HOME/.omo/omo.jsonc" 2>/dev/null || true

# --- Execution ---
TMP_DIR=$(mktemp -d)
# Ensure cleanup on any exit
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

# 1. Inherit other configurations (antigravity.json, AGENTS.md, etc.)
if [ -d "$REAL_CONFIG_DIR" ]; then
    # Create symlinks to all files in the real config dir except the one we are generating
    for f in "$REAL_CONFIG_DIR"/*; do
        filename=$(basename "$f")
        if [[ "$filename" != "oh-my-openagent.jsonc" && "$filename" != "oh-my-opencode.jsonc" && "$filename" != "opencode.jsonc" && "$filename" != *.bak.* ]]; then
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

    # Use envsubst to process the template, but only for variables that should be replaced.

    # We exclude $schema by explicitly providing the list of variables to substitute,
    # so that other schema-related variables like $schema remain untouched.
    envsubst '${SISYPHUS_MODEL} ${SISYPHUS_VARIANT} ${SISYPHUS_FALLBACK_MODEL} ${ULTRA_WORK_MODEL} ${ULTRA_WORK_FALLBACK_MODEL} ${HEPHAESTUS_DISABLED} ${HEPHAESTUS_MODEL} ${HEPHAESTUS_VARIANT} ${HEPHAESTUS_FALLBACK_MODEL} ${ORACLE_MODEL} ${ORACLE_VARIANT} ${ORACLE_FALLBACK_MODEL} ${LIBRARIAN_MODEL} ${LIBRARIAN_VARIANT} ${LIBRARIAN_FALLBACK_MODEL} ${EXPLORE_MODEL} ${EXPLORE_VARIANT} ${EXPLORE_FALLBACK_MODEL} ${MULTIMODAL_LOOKER_MODEL} ${MULTIMODAL_LOOKER_VARIANT} ${MULTIMODAL_LOOKER_FALLBACK_MODEL} ${PROMETHEUS_MODEL} ${PROMETHEUS_VARIANT} ${PROMETHEUS_FALLBACK_MODEL} ${METIS_MODEL} ${METIS_VARIANT} ${METIS_FALLBACK_MODEL} ${MOMUS_MODEL} ${MOMUS_VARIANT} ${MOMUS_FALLBACK_MODEL} ${ATLAS_MODEL} ${ATLAS_VARIANT} ${ATLAS_FALLBACK_MODEL} ${ULTRABRAIN_MODEL} ${ULTRABRAIN_VARIANT} ${ULTRABRAIN_FALLBACK_MODEL} ${DEEP_MODEL} ${DEEP_VARIANT} ${DEEP_FALLBACK_MODEL} ${QUICK_MODEL} ${QUICK_VARIANT} ${QUICK_FALLBACK_MODEL} ${WRITING_MODEL} ${WRITING_VARIANT} ${WRITING_FALLBACK_MODEL} ${UNSPECIFIED_LOW_MODEL} ${UNSPECIFIED_LOW_VARIANT} ${UNSPECIFIED_LOW_FALLBACK_MODEL} ${UNSPECIFIED_HIGH_MODEL} ${UNSPECIFIED_HIGH_VARIANT} ${UNSPECIFIED_HIGH_FALLBACK_MODEL} ${VISUAL_ENGINEERING_MODEL} ${VISUAL_ENGINEERING_VARIANT} ${VISUAL_ENGINEERING_FALLBACK_MODEL} ${ARTISTRY_MODEL} ${ARTISTRY_VARIANT} ${ARTISTRY_FALLBACK_MODEL}' < "$TEMPLATE" > "$TMP_DIR/oh-my-openagent.jsonc"

    # After envsubst substituted values, check if any model configuration has an empty value
    if grep -qE '"model"\s*:\s*""' "$TMP_DIR/oh-my-openagent.jsonc"; then
        echo "❌ Error: Empty model configuration detected in generated JSONC" >&2
        exit 1
    fi
)

# 3. Run OpenCode
# Note: We use OPENCODE_CONFIG_DIR to point to our temporary directory
export OPENCODE_CONFIG_DIR="$TMP_DIR"

# If user didn't pass an explicit --model flag, default to SISYPHUS_MODEL from current profile
MODEL_ARGS=()
if [[ -n "$SISYPHUS_MODEL" ]]; then
    has_model=false
    for arg in "$@"; do
        if [[ "$arg" == "-m" || "$arg" == "--model" || "$arg" == --model=* ]]; then
            has_model=true
            break
        fi
    done
    if [ "$has_model" = false ]; then
        MODEL_ARGS=(--model "$SISYPHUS_MODEL")
    fi
fi

# Only use automatic port for the main agent loop (no arguments or starting with -)
# Subcommands like auth, mcp, doctor, etc. don't accept --port
if [[ -n "$PORT" && ( -z "$1" || "$1" == -* ) ]]; then
    echo "✅ Profile [${PROFILE}] | Port [${PORT}]"
    opencode "${MODEL_ARGS[@]}" --port "$PORT" "$@"
else
    echo "✅ Profile [${PROFILE}]"
    opencode "${MODEL_ARGS[@]}" "$@"
fi

