#!/bin/bash
# scripts/update-skill-manifest.sh: Update External Skills Manifest (Lock-file) table

set -euo pipefail

MANIFEST_FILE="agent-skills/EXTERNAL_SKILLS.md"

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <namespace> <url> <hash> <pinned_at_date> [note]"
  exit 1
fi

NAMESPACE="$1"
URL="$2"
HASH="$3"
PINNED_AT="$4"
NOTE="${5:-""}"

if [ ! -f "$MANIFEST_FILE" ]; then
  echo "Error: $MANIFEST_FILE not found"
  exit 1
fi

# Create entry if it doesn't exist, or update existing one
if grep -q "| $NAMESPACE |" "$MANIFEST_FILE"; then
  # Update existing line safely with awk
  TEMP_FILE=$(mktemp)
  awk -v ns="$NAMESPACE" -v url="$URL" -v hash="$HASH" -v pinned="$PINNED_AT" -v note="$NOTE" '
    BEGIN { FS="|"; OFS="|" }
    {
      # Match the namespace in field 2 (trimmed)
      ns_field = $2;
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", ns_field);
      if (ns_field == ns) {
        $3 = " " url " ";
        $4 = " " hash " ";
        $5 = " " pinned " ";
        if (note != "") {
          $6 = " " note " ";
        }
        # If note is empty, field 6 is preserved
      }
      print $0;
    }
  ' "$MANIFEST_FILE" > "$TEMP_FILE" && mv "$TEMP_FILE" "$MANIFEST_FILE"
  echo "✅ Updated lock-file entry for '$NAMESPACE' (Pinned to: $HASH)"
else
  # Add new line
  echo "| $NAMESPACE | $URL | $HASH | $PINNED_AT | $NOTE |" >> "$MANIFEST_FILE"
  echo "✅ Added new pinned entry to lock-file for '$NAMESPACE' (Pinned to: $HASH)"
fi
