#!/usr/bin/env bash
# Encapsulate nexus execution for cleaner MCP communication.
exec /usr/bin/node /home/y_ohi/program/private/nexus/dist/bin/nexus.js "$@" 2>&2
