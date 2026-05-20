#!/usr/bin/env bash
# _scripts/test-sync-agents.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running Sync Agents Verification Tests..."

# Backup current files
cp "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md" "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.bak"

# Ensure cleanup on exit
cleanup() {
    mv "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.bak" "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md" || true
}
trap cleanup EXIT

# Clear out the skills section to test if the script adds it back
sed -i.tmp '/<available_skills>/,/<[/]available_skills>/d' "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md"
rm -f "$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md.tmp"

# Run sync_agents.sh
bash "$REPO_ROOT/_scripts/sync_agents.sh" >/dev/null

# Verify files
f="agent-skills/AVAILABLE_SKILLS.md"
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
if ! grep -qF "External skills (anthropics/*, superpowers/*)" "$REPO_ROOT/$f"; then
    echo "FAIL: External skills note not found in $f"
    exit 1
fi
if ! grep -qF "<name>anthropics/pdf</name>" "$REPO_ROOT/$f"; then
    echo "FAIL: anthropics/pdf skill entry not found in $f"
    exit 1
fi
echo "PASS: $f verified."

echo "🎉 All sync agents tests passed successfully!"
