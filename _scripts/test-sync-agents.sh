#!/usr/bin/env bash
# _scripts/test-sync-agents.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CATALOG="$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md"
GLOBAL_RULES="$REPO_ROOT/global-rules/AGENTS.global.md"

echo "Running Sync Agents Verification Tests..."

cp "$CATALOG" "$CATALOG.bak"
cp "$GLOBAL_RULES" "$GLOBAL_RULES.bak"

cleanup() {
    mv "$CATALOG.bak" "$CATALOG" || true
    mv "$GLOBAL_RULES.bak" "$GLOBAL_RULES" || true
}
trap cleanup EXIT

# Remove the generated section only from the dedicated catalog. The global
# instruction file must stay compact and must never receive the full catalog.
sed -i.tmp '/<!-- SKILLPORT_START -->/,/<!-- SKILLPORT_END -->/d' "$CATALOG"
rm -f "$CATALOG.tmp"

bash "$REPO_ROOT/_scripts/sync_agents.sh" >/dev/null

if ! grep -qF "<!-- SKILLPORT_START -->" "$CATALOG"; then
    echo "FAIL: <!-- SKILLPORT_START --> marker not found in agent-skills/AVAILABLE_SKILLS.md"
    exit 1
fi
if ! grep -qF "<!-- SKILLPORT_END -->" "$CATALOG"; then
    echo "FAIL: <!-- SKILLPORT_END --> marker not found in agent-skills/AVAILABLE_SKILLS.md"
    exit 1
fi
if ! grep -qF "<available_skills>" "$CATALOG"; then
    echo "FAIL: <available_skills> not found in agent-skills/AVAILABLE_SKILLS.md"
    exit 1
fi
if ! awk '/<available_skills>/, /<\/available_skills>/ { if ($0 ~ /<skill>/) { found=1; exit } } END { if (!found) exit 1 }' "$CATALOG"; then
    echo "FAIL: <available_skills> section is empty or missing <skill> elements"
    exit 1
fi
if ! grep -qF "External skills (anthropics/*, superpowers/*)" "$CATALOG"; then
    echo "FAIL: External skills note not found in agent-skills/AVAILABLE_SKILLS.md"
    exit 1
fi
if ! grep -qF "<name>pdf</name>" "$CATALOG"; then
    echo "FAIL: pdf skill entry not found in agent-skills/AVAILABLE_SKILLS.md"
    exit 1
fi

# Context-footprint regression guard: the full catalog must not be embedded in
# the always-on global instructions. The global file should only point to the
# catalog / on-demand loader.
if grep -qF "<!-- SKILLPORT_START -->" "$GLOBAL_RULES" || \
   grep -qF "<available_skills>" "$GLOBAL_RULES"; then
    echo "FAIL: global-rules/AGENTS.global.md contains an embedded skill catalog"
    exit 1
fi
if ! grep -qF "agent-skills/AVAILABLE_SKILLS.md" "$GLOBAL_RULES"; then
    echo "FAIL: global-rules/AGENTS.global.md no longer references the skill catalog"
    exit 1
fi

echo "PASS: agent-skills/AVAILABLE_SKILLS.md verified."
echo "PASS: global-rules/AGENTS.global.md remains compact."
echo "🎉 All sync agents tests passed successfully!"
