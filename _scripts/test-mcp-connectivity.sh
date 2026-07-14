#!/usr/bin/env bash
# _scripts/test-mcp-connectivity.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

FAILED=0

# Create temporary directory for logs
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# ANSI color codes removal helper
strip_ansi() {
    sed 's/\x1b\[[0-9;]*m//g'
}

# Helper to check if command exists
has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# Ensure environment variables are loaded
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
else
    echo -e "${YELLOW}[!] .env file not found. Connection tests might fail due to missing tokens.${NC}"
fi

echo -e "${YELLOW}[*] Checking MCP connectivity for all CLI tools...${NC}"

# Helper: check that a direct MCP server name appears in a client's MCP list
check_client_server() {
    local server_name="$1"
    local output="$2"
    if echo "$output" | grep -qE "${server_name}[[:space:]:].*(Connected|connected|active)"; then
        echo -e "${GREEN}[+] ${server_name}${NC}"
        return 0
    elif echo "$output" | grep -qE "${server_name}[[:space:]:]"; then
        echo -e "${RED}[x] ${server_name} present but not connected${NC}"
        echo "$output" | grep -E "${server_name}[[:space:]:]" || true
        return 1
    else
        echo -e "${RED}[x] ${server_name} not found${NC}"
        return 1
    fi
}

# Servers that should be present in all clients after migration
EXPECTED_SERVERS=(
    github-official
    filesystem
    sequentialthinking
    aws-iac
    aws-mcp
    aws-documentation
    sentry-remote
)

# 1. Claude Code
echo "Claude Code:"
if ! has_cmd "claude"; then
    echo -e "${YELLOW}[i] Skipped (not installed)${NC}"
else
    CLAUDE_OUT=$(claude mcp list 2>&1 | strip_ansi || true)
    for server in "${EXPECTED_SERVERS[@]}"; do
        if ! check_client_server "$server" "$CLAUDE_OUT"; then
            FAILED=1
        fi
    done
fi

# 2. Gemini CLI
echo "Gemini CLI:"
if ! has_cmd "gemini"; then
    echo -e "${YELLOW}[i] Skipped (not installed)${NC}"
else
    if command -v script > /dev/null 2>&1; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            script -q "$TMP_DIR/gemini_raw.txt" gemini mcp list > /dev/null 2>&1 || true
        else
            script -q -c "gemini mcp list" "$TMP_DIR/gemini_raw.txt" > /dev/null 2>&1 || true
        fi
    else
        gemini mcp list > "$TMP_DIR/gemini_raw.txt" 2>&1 || true
    fi

    if [ -f "$TMP_DIR/gemini_raw.txt" ]; then
        GEMINI_OUT=$(strip_ansi < "$TMP_DIR/gemini_raw.txt")
        for server in "${EXPECTED_SERVERS[@]}"; do
            if ! check_client_server "$server" "$GEMINI_OUT"; then
                FAILED=1
            fi
        done
    else
        echo -e "${RED}[x] Failed to capture output${NC}"
        FAILED=1
    fi
fi

# 3. OpenCode
echo "OpenCode:"
if ! has_cmd "opencode"; then
    echo -e "${YELLOW}[i] Skipped (not installed)${NC}"
else
    opencode mcp list > "$TMP_DIR/opencode_out.txt" 2>&1 || true
    OPENCODE_OUT=$(strip_ansi < "$TMP_DIR/opencode_out.txt")
    for server in "${EXPECTED_SERVERS[@]}"; do
        if ! check_client_server "$server" "$OPENCODE_OUT"; then
            FAILED=1
        fi
    done
fi

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}[+] All MCP configurations verified!${NC}"
    exit 0
else
    echo -e "\n${RED}[x] Some MCP connections failed or are missing.${NC}"
    exit 1
fi
