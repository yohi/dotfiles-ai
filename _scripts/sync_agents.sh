#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: Generate the SkillPort section of
# agent-skills/AVAILABLE_SKILLS.md from the runtime .agents/skills tree, local
# custom skills under agent-skills/custom, and project-local skills tracked
# under .claude/skills/.
#
# The full generated skill catalog is intentionally NOT embedded into
# global-rules/AGENTS.global.md. Global instructions stay compact and point to
# the catalog / on-demand skill loader instead (progressive disclosure).

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILE="agent-skills/AVAILABLE_SKILLS.md"
readonly START_MARKER="<!-- SKILLPORT_START -->"
readonly END_MARKER="<!-- SKILLPORT_END -->"

TMP_SKILLS_DIR=""
TMP_GENERATED=""

cleanup() {
    [ -z "$TMP_SKILLS_DIR" ] || rm -rf "$TMP_SKILLS_DIR"
    [ -z "$TMP_GENERATED" ] || rm -f "$TMP_GENERATED"
}
trap cleanup EXIT

build_combined_skills_dir() {
    TMP_SKILLS_DIR=$(mktemp -d)

    if [ -d ".agents/skills" ]; then
        cp -a .agents/skills/. "$TMP_SKILLS_DIR/"
    fi

    if [ -d "agent-skills/custom" ] && [ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]; then
        mkdir -p "$TMP_SKILLS_DIR/custom"
        cp -a agent-skills/custom/. "$TMP_SKILLS_DIR/custom/"
    fi

    if command -v git >/dev/null 2>&1; then
        local tracked_local_skills
        tracked_local_skills=$(git ls-files .claude/skills/ 2>/dev/null | awk -F'/' '{print $3}' | sort -u)
        if [ -n "$tracked_local_skills" ]; then
            mkdir -p "$TMP_SKILLS_DIR/local"
            while IFS= read -r skill_dir; do
                if [ -d ".claude/skills/$skill_dir" ]; then
                    cp -a ".claude/skills/$skill_dir" "$TMP_SKILLS_DIR/local/"
                fi
            done <<< "$tracked_local_skills"
        fi
    fi
}

generate_skillport_document() {
    TMP_GENERATED=$(mktemp)

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${OUTPUT_FILE}..."
        skillport --skills-dir "$TMP_SKILLS_DIR" doc --mode mcp --output "$TMP_GENERATED" --force
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${OUTPUT_FILE}..."
        uvx skillport --skills-dir "$TMP_SKILLS_DIR" doc --mode mcp --output "$TMP_GENERATED" --force
    else
        echo "Error: 'skillport' command not found." >&2
        exit 1
    fi
}

normalize_generated_document() {
    python3 - "$TMP_GENERATED" "$TMP_SKILLS_DIR" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
tmp_skills_dir = sys.argv[2].rstrip("/")
text = path.read_text(encoding="utf-8")

text = text.replace(f"{tmp_skills_dir}/local/", ".claude/skills/")
text = text.replace(f"{tmp_skills_dir}/custom/", "agent-skills/custom/")
text = text.replace(f"{tmp_skills_dir}/", ".agents/skills/")

start_marker = "<!-- SKILLPORT_START -->"
end_marker = "<!-- SKILLPORT_END -->"
start = text.find(start_marker)
end = text.rfind(end_marker)
if start == -1 or end == -1 or end <= start:
    raise SystemExit("generated SkillPort document is missing expected markers")

prefix = text[:start].rstrip("\n")
inner = text[start:end + len(end_marker)]
suffix = text[end + len(end_marker):].lstrip("\n")
inner = re.sub(r"<!-- SKILLPORT_START -->\s*\n+", "<!-- SKILLPORT_START -->\n", inner)
inner = re.sub(r"\n+<!-- SKILLPORT_END -->", "\n<!-- SKILLPORT_END -->", inner)
inner = re.sub(r"\n{3,}", "\n\n", inner)
text = prefix + "\n" + inner + "\n" + suffix

text = text.replace(
    "If search returns too many results, use more specific terms",
    "If search returns 10+ results, refine your query",
)
text = re.sub(
    r"<description>Reference for the Claude API / Anthropic SDK.*</description>",
    "<description>Reference for the Claude API / Anthropic SDK. Use when working with Claude/Anthropic APIs, model selection, pricing, tool use. Skip when working with other providers like OpenAI or Gemini.</description>",
    text,
)

note = """<!-- NOTE: External skills (anthropics/*, superpowers/*) are managed via apm.yml.
     They are automatically synchronized and locked using 'apm install'.
     IMPORTANT: Custom skills are tracked in Git. External namespaces should generally be ignored
     in the project root .gitignore (blacklist strategy) unless explicitly required for the repository's configuration. -->"""
if "<available_skills" in text and "External skills (anthropics/*, superpowers/*)" not in text:
    text = re.sub(
        r"(^\s*<available_skills>)",
        note + "\n" + r"\1",
        text,
        count=1,
        flags=re.MULTILINE,
    )

path.write_text(text, encoding="utf-8")
PY
}

merge_skillport_section() {
    mkdir -p "$(dirname "$OUTPUT_FILE")"

    if [ -f "$OUTPUT_FILE" ] && \
       grep -qF "$START_MARKER" "$OUTPUT_FILE" && \
       grep -qF "$END_MARKER" "$OUTPUT_FILE"; then
        python3 - "$TMP_GENERATED" "$OUTPUT_FILE" <<'PY'
from pathlib import Path
import sys

generated_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
start_marker = "<!-- SKILLPORT_START -->"
end_marker = "<!-- SKILLPORT_END -->"

generated = generated_path.read_text(encoding="utf-8")
original = output_path.read_text(encoding="utf-8")

g_start = generated.find(start_marker)
g_end = generated.rfind(end_marker)
o_start = original.find(start_marker)
o_end = original.rfind(end_marker)
if min(g_start, g_end, o_start, o_end) < 0 or g_end <= g_start or o_end <= o_start:
    raise SystemExit("cannot merge SkillPort section: expected markers are missing")

new_block = generated[g_start:g_end + len(end_marker)]
prefix = original[:o_start].rstrip("\n")
suffix = original[o_end + len(end_marker):].lstrip("\n")
output_path.write_text(prefix + "\n\n" + new_block + "\n" + suffix, encoding="utf-8")
PY
    else
        cp "$TMP_GENERATED" "$OUTPUT_FILE"
    fi
}

verify_global_instructions_are_compact() {
    if grep -qF "$START_MARKER" global-rules/AGENTS.global.md 2>/dev/null || \
       grep -qF "<available_skills>" global-rules/AGENTS.global.md 2>/dev/null; then
        echo "Error: global-rules/AGENTS.global.md contains an embedded SkillPort catalog." >&2
        echo "Keep global instructions compact and load skills on demand." >&2
        exit 1
    fi
}

main() {
    build_combined_skills_dir
    generate_skillport_document
    normalize_generated_document
    merge_skillport_section
    verify_global_instructions_are_compact
    echo "[+] Successfully synchronized ${OUTPUT_FILE}."
}

main "$@"
