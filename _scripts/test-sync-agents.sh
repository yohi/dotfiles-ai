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

# Verify files contain <available_skills>
for f in "AGENTS.md" "global-rules/AGENTS.global.md"; do
    if ! grep -qF "<available_skills>" "$REPO_ROOT/$f"; then
        echo "FAIL: <available_skills> not found in $f"
        exit 1
    fi
    if ! grep -qF "External skills (anthropics/*, superpowers/*)" "$REPO_ROOT/$f"; then
        echo "FAIL: External skills note not found in $f"
        exit 1
    fi
    echo "PASS: $f verified."
done

echo "🎉 All sync agents tests passed successfully!"
