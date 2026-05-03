#!/usr/bin/env bash
# _scripts/test-mcp-connectivity.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

FAILED=0

# Ensure environment variables are loaded
if [ -f ".env" ]; then
    # shellcheck disable=SC1091
    source .env
fi

# ANSI color codes removal helper
strip_ansi() {
    sed 's/\x1b\[[0-9;]*m//g'
}

echo -e "${YELLOW}🔍 Checking MCP Connectivity for all CLI tools...${NC}"

# 1. Claude Code
echo -n "Claude Code: "
claude mcp list > claude_out.txt 2>&1 || true
CLAUDE_OUT=$(strip_ansi < claude_out.txt)
if echo "$CLAUDE_OUT" | grep -q "docker-mcp:.*Connected"; then
    echo -e "${GREEN}✓ Connected${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    echo "$CLAUDE_OUT" | grep "docker-mcp" || true
    FAILED=1
fi
rm -f claude_out.txt

# 2. Gemini CLI
echo -n "Gemini CLI: "
# Use 'script' to simulate a TTY because gemini mcp list may produce no output otherwise
script -q -c "gemini mcp list" gemini_raw.txt > /dev/null 2>&1 || true
GEMINI_OUT=$(strip_ansi < gemini_raw.txt)
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
rm -f gemini_raw.txt

# 3. OpenCode
echo -n "OpenCode: "
opencode mcp list > opencode_out.txt 2>&1 || true
OPENCODE_OUT=$(strip_ansi < opencode_out.txt)
if echo "$OPENCODE_OUT" | grep -q "docker-mcp connected"; then
    echo -e "${GREEN}✓ Connected${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    echo "$OPENCODE_OUT" | grep "docker-mcp" || true
    FAILED=1
fi
rm -f opencode_out.txt

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✅ All MCP configurations verified!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some MCP connections failed or are missing.${NC}"
    exit 1
fi
