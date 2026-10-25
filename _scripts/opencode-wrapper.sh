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

# --- MCP Portal Profile Routing (OpenCode V1) ---
# The APM-generated global MCP configuration contains all three Portals.
# Disable inactive profiles using OpenCode's highest-priority inline config.
# Default remains OFF until the existing account-bound upstreams are removed
# from Cloudflare's common Portal. CF_MCP_DEFAULT_ENABLED=1 is explicit opt-in.
# The Portal itself and upstream Access policies MUST enforce authorization.
if ! PORTAL_CONFIG_JSON=$(python3 - "$PROFILE" <<'PY'
import json
import os
import sys

profile = sys.argv[1]
default_flag = os.environ.get("CF_MCP_DEFAULT_ENABLED", "0")
if default_flag not in ("0", "1"):
    raise SystemExit("CF_MCP_DEFAULT_ENABLED must be 0 or 1")

existing = os.environ.get("OPENCODE_CONFIG_CONTENT", "")
try:
    config = json.loads(existing) if existing else {}
except json.JSONDecodeError as exc:
    raise SystemExit(f"Invalid OPENCODE_CONFIG_CONTENT JSON: {exc}")
if not isinstance(config, dict):
    raise SystemExit("OPENCODE_CONFIG_CONTENT must contain a JSON object")
mcp = config.setdefault("mcp", {})
if not isinstance(mcp, dict):
    raise SystemExit("OPENCODE_CONFIG_CONTENT.mcp must be a JSON object")

selection = {
    "cf-mcp-portal": default_flag == "1",
    "cf-mcp-portal-personal": profile == "personal",
    "cf-mcp-portal-work": profile == "work",
}
for name, enabled in selection.items():
    existing_entry = mcp.get(name, {})
    if not isinstance(existing_entry, dict):
        raise SystemExit(f"Invalid MCP override for {name}")
    mcp[name] = {**existing_entry, "enabled": enabled}

print(json.dumps(config, separators=(",", ":")))
PY
); then
    echo "❌ Failed to construct OpenCode MCP Portal profile configuration" >&2
    exit 1
fi
export OPENCODE_CONFIG_CONTENT="$PORTAL_CONFIG_JSON"
unset PORTAL_CONFIG_JSON

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
    # --- Sibyl Subagent Display (dynamic, port-aware) ---
    export OPENCODE_SERVER_URL="${OPENCODE_SERVER_URL:-http://127.0.0.1:${PORT}}"
    export OPENCODE_PROJECT_DIR="${OPENCODE_PROJECT_DIR:-$PWD}"
    export SIBYL_SUBAGENT_ENABLED="${SIBYL_SUBAGENT_ENABLED:-true}"
    opencode --port "$PORT" "$@"
else
    echo "✅ Profile [${PROFILE}]"
    opencode "$@"
fi
