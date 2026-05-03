#!/usr/bin/env bash
# _scripts/mcp-stdio-wrapper.sh

LOG_FILE="${MCP_LOG_FILE:-$HOME/.mcp/gateway-stdio.log}"
mkdir -p "$(dirname "$LOG_FILE")"

# Docker MCP Gateway が多数のコンテナを制御するため、
# ファイル記述子の上限を引き上げて 'too many open files' エラーを防ぐ。
ulimit -n 4096 2>/dev/null || true

# stderr をログへ。stdout (JSON-RPC) をエージェントへ。
exec docker mcp gateway run "$@" 2> "$LOG_FILE"
