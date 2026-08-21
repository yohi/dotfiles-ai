#!/bin/bash
# opencode-wrapper.sh: Profile-aware OpenCode launcher (omo native profiles)
#
# Usage:
#   opencode-wrapper.sh [personal|work] [opencode args...]
#   PROFILE=work opencode-wrapper.sh [opencode args...]
#
# Profile selection activates the corresponding omo.jsonc profile via OMO_PROFILE.
# Model configuration is managed in ~/.omo/omo.jsonc profiles.personal / profiles.work.

set -e

# Ensure auth data is loaded from the correct XDG data directory
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "$REPO_ROOT/.env"
    set +a
fi

# --- Profile Selection ---
PROFILE="${PROFILE:-personal}"
if [[ "$1" == "work" || "$1" == "personal" ]]; then
    PROFILE="$1"
    shift
fi

if [[ "$PROFILE" != "work" && "$PROFILE" != "personal" ]]; then
    PROFILE="personal"
fi

# Activate omo native profile
export OMO_PROFILE="$PROFILE"

export SKILLPORT_SKILLS_DIR="${SKILLPORT_SKILLS_DIR:-$REPO_ROOT/.agents/skills}"

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

# Only use automatic port for the main agent loop (no arguments or starting with -)
# Subcommands like auth, mcp, doctor, etc. don't accept --port
if [[ -n "$PORT" && ( -z "$1" || "$1" == -* ) ]]; then
    echo "✅ Profile [${PROFILE}] | Port [${PORT}]"
    opencode --port "$PORT" "$@"
else
    echo "✅ Profile [${PROFILE}]"
    opencode "$@"
fi
