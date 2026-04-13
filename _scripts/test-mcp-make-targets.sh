#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Running MCP Make target verification tests..."

STATUS_RECIPE="$(make -s -n -C "$REPO_ROOT" status-mcp)"

if ! grep -Fq -- "systemctl --user --no-pager status docker-mcp-gateway.service" <<<"$STATUS_RECIPE"; then
    echo "FAIL: status-mcp must invoke systemctl with --no-pager to avoid interactive paging."
    exit 1
fi

echo "PASS: status-mcp runs without pager."

echo "🎉 All MCP Make target tests passed successfully!"
