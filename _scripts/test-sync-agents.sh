#!/usr/bin/env bash
# _scripts/test-sync-agents.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running Sync Agents Verification Tests..."

# Backup current files
cp "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md" "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.bak"
cp "$REPO_ROOT/global-rules/AGENTS.global.md" "$REPO_ROOT/global-rules/AGENTS.global.md.bak"

# Ensure cleanup on exit
cleanup() {
    mv "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.bak" "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md" || true
    mv "$REPO_ROOT/global-rules/AGENTS.global.md.bak" "$REPO_ROOT/global-rules/AGENTS.global.md" || true
}
trap cleanup EXIT

# Clear out the skills section to test if the script adds it back
sed -i.tmp '/<available_skills>/,/<[/]available_skills>/d' "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md"
sed -i.tmp '/<available_skills>/,/<[/]available_skills>/d' "$REPO_ROOT/global-rules/AGENTS.global.md"
rm -f "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.tmp" "$REPO_ROOT/global-rules/AGENTS.global.md.tmp"

# Run sync_agents.sh
bash "$REPO_ROOT/_scripts/sync_agents.sh" >/dev/null

# Verify files
readonly OUTPUT_FILES=(
    "agent-skills/AVAILABLE_SKILLS.md"
    "global-rules/AGENTS.global.md"
)

for f in "${OUTPUT_FILES[@]}"; do
    if ! grep -qF "<!-- SKILLPORT_START -->" "$REPO_ROOT/$f"; then
        echo "FAIL: <!-- SKILLPORT_START --> marker not found in $f"
        exit 1
    fi
    if ! grep -qF "<!-- SKILLPORT_END -->" "$REPO_ROOT/$f"; then
        echo "FAIL: <!-- SKILLPORT_END --> marker not found in $f"
        exit 1
    fi
    if ! grep -qF "<available_skills>" "$REPO_ROOT/$f"; then
        echo "FAIL: <available_skills> not found in $f"
        exit 1
    fi
    # Check if <available_skills> section is not empty
    if grep -qF "<available_skills></available_skills>" "$REPO_ROOT/$f" || grep -qF "<available_skills />" "$REPO_ROOT/$f"; then
        echo "FAIL: <available_skills> section is empty in $f"
        exit 1
    fi
    if ! grep -qF "External skills (anthropics/*, superpowers/*)" "$REPO_ROOT/$f"; then
        echo "FAIL: External skills note not found in $f"
        exit 1
    fi
    if ! grep -qF "<name>pdf</name>" "$REPO_ROOT/$f"; then
        echo "FAIL: pdf skill entry not found in $f"
        exit 1
    fi
    echo "PASS: $f verified."
done

echo "🎉 All sync agents tests passed successfully!"
