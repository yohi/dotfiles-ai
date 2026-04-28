#!/usr/bin/env bash
# _scripts/test-sync-agents.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running Sync Agents Verification Tests..."

# Backup current files
cp "$REPO_ROOT/AGENTS.md" "$REPO_ROOT/AGENTS.md.bak"
cp "$REPO_ROOT/global-rules/AGENTS.global.md" "$REPO_ROOT/global-rules/AGENTS.global.md.bak"

# Ensure cleanup on exit
cleanup() {
    mv "$REPO_ROOT/AGENTS.md.bak" "$REPO_ROOT/AGENTS.md" || true
    mv "$REPO_ROOT/global-rules/AGENTS.global.md.bak" "$REPO_ROOT/global-rules/AGENTS.global.md" || true
}
trap cleanup EXIT

# Clear out the skills section to test if the script adds it back
sed -i.tmp '/<available_skills>/,/<[/]available_skills>/d' "$REPO_ROOT/AGENTS.md"
sed -i.tmp '/<available_skills>/,/<[/]available_skills>/d' "$REPO_ROOT/global-rules/AGENTS.global.md"
rm -f "$REPO_ROOT/AGENTS.md.tmp" "$REPO_ROOT/global-rules/AGENTS.global.md.tmp"

# Run sync_agents.sh
bash "$REPO_ROOT/_scripts/sync_agents.sh" >/dev/null

# Verify files
# global-rules/AGENTS.global.md should contain the skill list
f="global-rules/AGENTS.global.md"
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

# AGENTS.md should also contain the skill list
f="AGENTS.md"
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
