#!/bin/bash
set -euo pipefail

echo "Fixing _mk/sync-agents.mk..."
# Replace complex sed with small python script
python3 -c '
import sys
try:
    with open("_mk/sync-agents.mk", "r") as f:
        content = f.read()
    target = """body=$$(awk '\''BEGIN{n=0} /^---$$/{n++; next} n>=2{print}'\'' "$$cmd"); \\"""
    replacement = """body=$$(awk '\''BEGIN{n=0} /^---$$/{n++; next} n>=2{print}'\'' "$$cmd" | sed '\''s/\\\\/\\\\\\\\/g; s/\"\"\"/\\\\\"\"\"/g'\''); \\"""
    if target in content:
        content = content.replace(target, replacement)
        with open("_mk/sync-agents.mk", "w") as f:
            f.write(content)
except FileNotFoundError:
    pass
'
