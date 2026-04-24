#!/usr/bin/env bash
# _scripts/mcp-watchdog.sh
# Monitors logs.json size and sends SIGHUP to docker-mcp-gateway to prevent handshake deadlocks.
set -euo pipefail

MAX_LOG_SIZE=1024000 # 1MB
INTERVAL=3600        # 1 hour

echo "🚀 Starting MCP Watchdog (MAX_LOG_SIZE=${MAX_LOG_SIZE} bytes, INTERVAL=${INTERVAL}s)..."

while true; do
  # 1. Rotate large logs.json files in ~/.gemini/tmp/
  # We use printf '[]' to keep it as a valid JSON array.
  # We find files larger than MAX_LOG_SIZE bytes.
  find "$HOME/.gemini/tmp/" -name "logs.json" -type f -size +"${MAX_LOG_SIZE}c" 2>/dev/null | while read -r logfile; do
    SIZE=$(stat -c%s "$logfile" 2>/dev/null || stat -f%z "$logfile" 2>/dev/null)
    echo "⚠️  Rotating large log file ($SIZE bytes): $logfile"
    # Atomic rotation using tmp file and mv
    printf '[]' > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
  done

  # 2. Refresh Docker MCP Gateway process with SIGHUP
  # This helps clear logical deadlocks in the gateway memory.
  # Get MainPID directly from systemd for reliability.
  GATEWAY_PID=$(systemctl --user show -p MainPID --value docker-mcp-gateway.service 2>/dev/null || echo "0")
  if [[ "$GATEWAY_PID" =~ ^[0-9]+$ ]] && [ "$GATEWAY_PID" -gt 0 ]; then
    echo "🔄 Sending SIGHUP to Docker MCP Gateway process (PID: $GATEWAY_PID)"
    kill -HUP "$GATEWAY_PID"
  else
    echo "ℹ️  Docker MCP Gateway process not found. Skipping SIGHUP."
  fi

  sleep "$INTERVAL"
done
