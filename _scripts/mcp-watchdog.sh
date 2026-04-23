#!/usr/bin/env bash
# _scripts/mcp-watchdog.sh
# Monitors logs.json size and sends SIGHUP to docker-mcp-gateway to prevent handshake deadlocks.

MAX_LOG_SIZE=512000 # 500KB
INTERVAL=300        # 5 minutes

echo "🚀 Starting MCP Watchdog (MAX_LOG_SIZE=${MAX_LOG_SIZE} bytes, INTERVAL=${INTERVAL}s)..."

while true; do
  # 1. Rotate large logs.json files in ~/.gemini/tmp/
  # We use echo "[]" to keep it as a valid JSON array.
  # We find files larger than MAX_LOG_SIZE bytes.
  find "$HOME/.gemini/tmp/" -name "logs.json" -type f -size +"${MAX_LOG_SIZE}c" 2>/dev/null | while read -r logfile; do
    SIZE=$(stat -c%s "$logfile" 2>/dev/null || stat -f%z "$logfile" 2>/dev/null)
    echo "⚠️  Rotating large log file ($SIZE bytes): $logfile"
    echo "[]" > "$logfile"
  done

  # 2. Refresh Docker MCP Gateway process with SIGHUP
  # This helps clear logical deadlocks in the gateway memory.
  # We look for the child process of "docker mcp gateway run" which is the actual plugin handler.
  GATEWAY_PID=$(pgrep -f "docker-mcp mcp gateway run" | head -n 1)
  if [ -n "$GATEWAY_PID" ]; then
    echo "🔄 Sending SIGHUP to Docker MCP Gateway process (PID: $GATEWAY_PID)"
    kill -HUP "$GATEWAY_PID"
  else
    echo "ℹ️  Docker MCP Gateway process not found. Skipping SIGHUP."
  fi

  sleep "$INTERVAL"
done
