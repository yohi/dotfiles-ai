#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: Generate agent-skills/AVAILABLE_SKILLS.md from the runtime
# .agents/skills tree, local custom skills under agent-skills/custom, and
# project-local skills tracked under .claude/skills/.
#
# The full generated skill catalog is intentionally NOT embedded into
# global-rules/AGENTS.global.md. Global instructions stay compact and point to
# the catalog / on-demand skill loader instead (progressive disclosure).

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILE="agent-skills/AVAILABLE_SKILLS.md"

cleanup_paths=()
cleanup() {
    local p
    for p in "${cleanup_paths[@]:-}"; do
        rm -rf "$p"
    done
}
trap cleanup EXIT

make_combined_skills_dir() {
    local tmp_skills_dir
    tmp_skills_dir=$(mktemp -d)
    cleanup_paths+=("$tmp_skills_dir")

    if [ -d ".agents/skills" ]; then
        cp -a .agents/skills/. "$tmp_skills_dir/"
    fi

    if [ -d "agent-skills/custom" ] && [ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]; then
        mkdir -p "$tmp_skills_dir/custom"
        cp -a agent-skills/custom/. "$tmp_skills_dir/custom/"
    fi

    if command -v git >/dev/null 2>&1; then
        local tracked_local_skills
        tracked_local_skills=$(git ls-files .claude/skills/ 2>/dev/null | awk -F'/' '{print $3}' | sort -u)
        if [ -n "$tracked_local_skills" ]; then
            mkdir -p "$tmp_skills_dir/local"
            while IFS= read -r skill_dir; do
                if [ -d ".claude/skills/$skill_dir" ]; then
                    cp -a ".claude/skills/$skill_dir" "$tmp_skills_dir/local/"
                fi
            done <<< "$tracked_local_skills"
        fi
    fi

    printf '%s\n' "$tmp_skills_dir"
}

generate_catalog() {
    local tmp_skills_dir="$1"
    local tmp_file
    tmp_file=$(mktemp)
    cleanup_paths+=("$tmp_file")

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${OUTPUT_FILE}..."
        skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${OUTPUT_FILE}..."
        uvx skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force
    else
        echo "Error: 'skillport' command not found." >&2
        exit 1
    fi

    python3 - "$tmp_file" "$tmp_skills_dir" <<'PY'
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
if start != -1 and end != -1 and end > start:
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
    text = re.sub(r"(^\s*<available_skills(?:\s|>))", note + "\n" + r"\1", text, count=1, flags=re.MULTILINE)

path.write_text(text, encoding="utf-8")
PY

    mkdir -p "$(dirname "$OUTPUT_FILE")"
    cp "$tmp_file" "$OUTPUT_FILE"
}

main() {
    local tmp_skills_dir
    tmp_skills_dir=$(make_combined_skills_dir)
    generate_catalog "$tmp_skills_dir"

    # Defensive migration guard: the generated catalog must never be copied
    # back into the global instruction file.
    if grep -qF "<!-- SKILLPORT_START -->" global-rules/AGENTS.global.md 2>/dev/null; then
        echo "Error: global-rules/AGENTS.global.md still contains an embedded SkillPort catalog." >&2
        echo "Keep global instructions compact and load skills on demand." >&2
        exit 1
    fi

    echo "[+] Successfully synchronized ${OUTPUT_FILE}."
}

main "$@"
