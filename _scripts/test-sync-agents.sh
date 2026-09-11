#!/usr/bin/env bash
# _scripts/test-sync-agents.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CATALOG="$REPO_ROOT/agent-skills/AVAILABLE_SKILLS.md"
GLOBAL_RULES_DIR="$REPO_ROOT/global-rules"
GLOBAL_RULES="$REPO_ROOT/global-rules/AGENTS.global.md"
META_PROMPT="$REPO_ROOT/global-rules/META_PROMPT.md"
OPENCODE_GLOBAL_RULES="$REPO_ROOT/opencode/docs/global-rules/AGENTS.global.md"
OPENCODE_META_PROMPT="$REPO_ROOT/opencode/docs/global-rules/META_PROMPT.md"
OPENCODE_SKILL_CATALOG="$REPO_ROOT/opencode/docs/agent-skills/AVAILABLE_SKILLS.md"
SKILL_CATALOG_REFERENCE="../agent-skills/AVAILABLE_SKILLS.md"
SKILL_DIRECTORY_REFERENCE="../agent-skills/"

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
if ! grep -qF "$SKILL_CATALOG_REFERENCE" "$GLOBAL_RULES"; then
    echo "FAIL: global-rules/AGENTS.global.md no longer references the skill catalog"
    exit 1
fi
if [ ! -f "$GLOBAL_RULES_DIR/$SKILL_CATALOG_REFERENCE" ]; then
    echo "FAIL: skill catalog reference resolves to a missing file"
    exit 1
fi
if [ ! -f "$OPENCODE_GLOBAL_RULES" ] || \
   ! grep -qF "$SKILL_CATALOG_REFERENCE" "$OPENCODE_GLOBAL_RULES"; then
    echo "FAIL: OpenCode global-rules mirror does not reference the skill catalog"
    exit 1
fi
if ! grep -qF "$SKILL_DIRECTORY_REFERENCE" "$META_PROMPT" || \
   [ ! -f "$OPENCODE_META_PROMPT" ] || \
   ! grep -qF "$SKILL_DIRECTORY_REFERENCE" "$OPENCODE_META_PROMPT"; then
    echo "FAIL: global-rules META_PROMPT references are not synchronized"
    exit 1
fi
if [ ! -f "$OPENCODE_SKILL_CATALOG" ]; then
    echo "FAIL: OpenCode mirror skill catalog reference resolves to a missing file"
    exit 1
fi

echo "PASS: agent-skills/AVAILABLE_SKILLS.md verified."
echo "PASS: global-rules/AGENTS.global.md remains compact."
echo "🎉 All sync agents tests passed successfully!"
