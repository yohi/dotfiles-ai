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

# Helper to check if gateway is running
check_gateway() {
    if curl -s --connect-timeout 2 --max-time 5 -o /dev/null "http://127.0.0.1:10888/sse"; then
        return 0
    elif curl -s -k --connect-timeout 2 --max-time 5 -o /dev/null "https://127.0.0.1:10888/sse"; then
        return 0
    fi
    return 1
}

# Ensure environment variables are loaded
if [ -f ".env" ]; then
    # shellcheck disable=SC1091
    set -a
    source .env
    set +a
else
    echo -e "${YELLOW}⚠ .env file not found. Connection tests might fail due to missing tokens.${NC}"
fi

echo -e "${YELLOW}🔍 Checking MCP Connectivity for all CLI tools...${NC}"

if ! check_gateway; then
    echo -e "${RED}✗ MCP Gateway is not responding on port 10888.${NC}"
    echo -e "${YELLOW}  Hint: Run 'make sync-mcp' to start the gateway.${NC}"
    if [ "${CI:-}" = "true" ]; then
        echo -e "${YELLOW}⚠ Skipping hard failure in CI environment.${NC}"
    else
        FAILED=1
    fi
fi

# 1. Claude Code
echo -n "Claude Code: "
if ! has_cmd "claude"; then
    echo -e "${YELLOW}Skipped (not installed)${NC}"
else
    # claude mcp list might fail if it can't connect, but we want to capture the status
    CLAUDE_OUT=$(claude mcp list 2>&1 | strip_ansi || true)
    if echo "$CLAUDE_OUT" | grep -q "docker-mcp:.*Connected"; then
        echo -e "${GREEN}✓ Connected${NC}"
    elif echo "$CLAUDE_OUT" | grep -q "docker-mcp"; then
        echo -e "${RED}✗ Connection Failed${NC}"
        echo "$CLAUDE_OUT" | grep "docker-mcp" || true
        FAILED=1
    else
        echo -e "${YELLOW}⚠ docker-mcp not configured in Claude${NC}"
    fi
fi

# 2. Gemini CLI
echo -n "Gemini CLI: "
if ! has_cmd "gemini"; then
    echo -e "${YELLOW}Skipped (not installed)${NC}"
else
    # Use 'script' to simulate a TTY because gemini mcp list may produce no output otherwise
    if command -v script > /dev/null 2>&1; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS script syntax: script -q <file> <command>
            script -q "$TMP_DIR/gemini_raw.txt" gemini mcp list > /dev/null 2>&1 || true
        else
            # Linux script syntax: script -q -c <command> <file>
            script -q -c "gemini mcp list" "$TMP_DIR/gemini_raw.txt" > /dev/null 2>&1 || true
        fi
    else
        # Fallback for environments without 'script' command
        gemini mcp list > "$TMP_DIR/gemini_raw.txt" 2>&1 || true
    fi

    if [ -f "$TMP_DIR/gemini_raw.txt" ]; then
        GEMINI_OUT=$(strip_ansi < "$TMP_DIR/gemini_raw.txt")
        if echo "$GEMINI_OUT" | grep -q "docker-mcp:.*Connected"; then
            echo -e "${GREEN}✓ Connected${NC}"
        elif echo "$GEMINI_OUT" | grep -q "docker-mcp:.*Disconnected"; then
            echo -e "${RED}✗ Connection Failed (Disconnected)${NC}"
            echo "$GEMINI_OUT" | grep "docker-mcp" || true
            FAILED=1
        elif echo "$GEMINI_OUT" | grep -q "docker-mcp:.*sse"; then
            echo -e "${YELLOW}⚠ Found (in config)${NC}"
        else
            echo -e "${RED}✗ Not found in config${NC}"
            if [ -z "$GEMINI_OUT" ]; then
                echo "   (Empty output even with script)"
            else
                echo "   Output snippet: $(echo "$GEMINI_OUT" | head -n 3)"
            fi
            FAILED=1
        fi
    else
        echo -e "${RED}✗ Failed to capture output${NC}"
        FAILED=1
    fi
fi

# 3. OpenCode
echo -n "OpenCode: "
if ! has_cmd "opencode"; then
    echo -e "${YELLOW}Skipped (not installed)${NC}"
else
    opencode mcp list > "$TMP_DIR/opencode_out.txt" 2>&1 || true
    OPENCODE_OUT=$(strip_ansi < "$TMP_DIR/opencode_out.txt")
    if echo "$OPENCODE_OUT" | grep -q "docker-mcp connected"; then
        echo -e "${GREEN}✓ Connected${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$OPENCODE_OUT" | grep "docker-mcp" || true
        FAILED=1
    fi
fi

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✅ All MCP configurations verified!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some MCP connections failed or are missing.${NC}"
    exit 1
fi
