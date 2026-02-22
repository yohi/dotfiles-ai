#!/bin/bash
set -eo pipefail

echo "Fixing _mk/sync-agents.mk..."
# 1. sync-agents.mk lines 110-114
sed -i 's/body=\$\$(awk '\''BEGIN{n=0} \/^---\$\$\/{n++; next} n>=2{print}'\'' "\$\$cmd"); \\/body=\$\$(awk '\''BEGIN{n=0} \/^---\$\$\/{n++; next} n>=2{print}'\'' "\$\$cmd" | sed '\''s\/\\\\\/\\\\\\\\\/g; s\/"""\/\\\\"""\/g'\''); \\/' _mk/sync-agents.mk
# Wait, replacing sed with backslashes is very tricky. I'll use python for sed replacements!
