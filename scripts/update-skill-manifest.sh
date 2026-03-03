#!/bin/bash
# scripts/update-skill-manifest.sh: Update External Skills Manifest table

set -euo pipefail

MANIFEST_FILE="agent-skills/EXTERNAL_SKILLS.md"

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <namespace> <url> <hash> <date> [note]"
  exit 1
fi

NAMESPACE="$1"
URL="$2"
HASH="$3"
DATE="$4"
NOTE="${5:-""}"

if [ ! -f "$MANIFEST_FILE" ]; then
  echo "Error: $MANIFEST_FILE not found"
  exit 1
fi

# Create entry if it doesn't exist, or update existing one
if grep -q "| $NAMESPACE |" "$MANIFEST_FILE"; then
  # Update existing line (preserving note if not provided)
  if [ -n "$NOTE" ]; then
    sed -i "s#| $NAMESPACE |.*#| $NAMESPACE | $URL | $HASH | $DATE | $NOTE |#" "$MANIFEST_FILE"
  else
    # Preserve current note if $NOTE is empty
    CURRENT_NOTE=$(grep "| $NAMESPACE |" "$MANIFEST_FILE" | awk -F'|' '{print $6}' | sed 's/^ //;s/ $//')
    sed -i "s#| $NAMESPACE |.*#| $NAMESPACE | $URL | $HASH | $DATE | $CURRENT_NOTE |#" "$MANIFEST_FILE"
  fi
  echo "✅ Updated manifest for '$NAMESPACE' (Version: $HASH)"
else
  # Add new line
  echo "| $NAMESPACE | $URL | $HASH | $DATE | $NOTE |" >> "$MANIFEST_FILE"
  echo "✅ Added new entry to manifest for '$NAMESPACE' (Version: $HASH)"
fi
