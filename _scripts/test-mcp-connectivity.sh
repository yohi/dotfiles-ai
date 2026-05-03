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

# Ensure environment variables are loaded
if [ -f ".env" ]; then
    # shellcheck disable=SC1091
    source .env
fi

# ANSI color codes removal helper
strip_ansi() {
    sed 's/\x1b\[[0-9;]*m//g'
}

# Helper to check if command exists
has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "${YELLOW}🔍 Checking MCP Connectivity for all CLI tools...${NC}"

# 1. Claude Code
echo -n "Claude Code: "
if ! has_cmd "claude"; then
    echo -e "${YELLOW}⚠ Skipped (not installed)${NC}"
else
    claude mcp list > "$TMP_DIR/claude_out.txt" 2>&1 || true
    CLAUDE_OUT=$(strip_ansi < "$TMP_DIR/claude_out.txt")
    if echo "$CLAUDE_OUT" | grep -q "docker-mcp:.*Connected"; then
        echo -e "${GREEN}✓ Connected${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$CLAUDE_OUT" | grep "docker-mcp" || true
        FAILED=1
    fi
fi

# 2. Gemini CLI
echo -n "Gemini CLI: "
if ! has_cmd "gemini"; then
    echo -e "${YELLOW}⚠ Skipped (not installed)${NC}"
else
    # Use 'script' to simulate a TTY because gemini mcp list may produce no output otherwise
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS script syntax: script -q <file> <command>
        script -q "$TMP_DIR/gemini_raw.txt" gemini mcp list > /dev/null 2>&1 || true
    else
        # Linux script syntax: script -q -c <command> <file>
        script -q -c "gemini mcp list" "$TMP_DIR/gemini_raw.txt" > /dev/null 2>&1 || true
    fi

    if [ -f "$TMP_DIR/gemini_raw.txt" ]; then
        GEMINI_OUT=$(strip_ansi < "$TMP_DIR/gemini_raw.txt")
        if echo "$GEMINI_OUT" | grep -q "docker-mcp:.*Connected"; then
            echo -e "${GREEN}✓ Connected${NC}"
        elif echo "$GEMINI_OUT" | grep -Eq "docker-mcp:.*(Disconnected|sse)"; then
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
    echo -e "${YELLOW}⚠ Skipped (not installed)${NC}"
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
