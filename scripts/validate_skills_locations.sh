#!/usr/bin/env bash
# scripts/validate_skills_locations.sh

set -euo pipefail

# Compute the repository root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(cd "$(dirname "$0")" && pwd)")
cd "$REPO_ROOT" || exit 1

FILE_TO_CHECK="global-rules/AGENTS.global.md"
EXIT_STATUS=0

echo "Validating skill locations in ${FILE_TO_CHECK} (Root: $REPO_ROOT)..."

if [[ ! -f "$FILE_TO_CHECK" ]]; then
    echo "Error: File $FILE_TO_CHECK not found relative to $REPO_ROOT."
    exit 1
fi

# Extract locations and check existence
# Using sed to extract content between <location> tags for better compatibility
locations=$(grep -o '<location>[^<]*</location>' "$FILE_TO_CHECK" | sed 's|<location>\([^<]*\)</location>|\1|' || true)

if [[ -z "$locations" ]]; then
    echo "No skill locations found."
    exit 0
fi

while IFS= read -r loc; do
    if [[ -z "$loc" ]]; then continue; fi
    # Check existence relative to the repo root
    if [[ ! -f "$loc" ]]; then
        echo "Error: Referenced skill location '$loc' does not exist in $REPO_ROOT."
        EXIT_STATUS=1
    else
        echo "OK: $loc"
    fi
done <<< "$locations"

if [[ $EXIT_STATUS -eq 0 ]]; then
    echo "All skill locations validated successfully."
else
    echo "Validation failed. Some skill locations are missing."
fi

exit $EXIT_STATUS
