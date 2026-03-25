#!/usr/bin/env bash
# scripts/validate_skills_locations.sh

set -euo pipefail

FILE_TO_CHECK="global-rules/AGENTS.global.md"
EXIT_STATUS=0

echo "Validating skill locations in ${FILE_TO_CHECK}..."

if [[ ! -f "$FILE_TO_CHECK" ]]; then
    echo "Error: File $FILE_TO_CHECK not found."
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
    if [[ ! -f "$loc" ]]; then
        echo "Error: Referenced skill location '$loc' does not exist."
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
