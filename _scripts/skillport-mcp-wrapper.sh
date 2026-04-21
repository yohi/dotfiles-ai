#!/usr/bin/env bash
# MCP communication happens on stdout. Redirect all potential noise to stderr.
# We use exec to replace the shell process with the actual server.
exec /home/y_ohi/.local/bin/skillport-mcp "$@" 2>&1 >&3 3>&- | grep --line-buffered -v ".*" >&2 3>&1
