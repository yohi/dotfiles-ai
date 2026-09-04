#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: Generate agent-skills/AVAILABLE_SKILLS.md from the runtime
# skill trees. Global agent instructions deliberately keep only a lightweight
# reference to this catalog so every AI agent can share the same rules without
# injecting the entire skill inventory into every prompt.
#

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILE="agent-skills/AVAILABLE_SKILLS.md"

if [[ ! -d "$(dirname "$OUTPUT_FILE")" ]] || [[ ! -w "$(dirname "$OUTPUT_FILE")" ]]; then
    echo "Error: Output directory '$(dirname "$OUTPUT_FILE")' does not exist or is not writable." >&2
    exit 1
fi

if [[ -e "$OUTPUT_FILE" ]] && { [[ ! -f "$OUTPUT_FILE" ]] || [[ ! -r "$OUTPUT_FILE" ]] || [[ ! -w "$OUTPUT_FILE" ]]; }; then
    echo "Error: Output file '$OUTPUT_FILE' exists but is not a readable/writable regular file." >&2
    exit 1
fi

tmp_file=$(mktemp)
tmp_skills_dir=$(mktemp -d)
cleanup() {
    rm -rf "$tmp_file" "$tmp_skills_dir"
}
trap cleanup EXIT

# Runtime skills installed by APM/SkillPort.
if [[ -d ".agents/skills" ]]; then
    cp -a .agents/skills/. "$tmp_skills_dir/"
fi

# Global custom skills maintained in yohi/agent-skills.
if [[ -d "agent-skills/custom" ]] && [[ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]]; then
    mkdir -p "$tmp_skills_dir/custom"
    cp -a agent-skills/custom/. "$tmp_skills_dir/custom/"
fi

# Project-local skills tracked under .claude/skills/.
if command -v git >/dev/null 2>&1; then
    tracked_local_skills=$(git ls-files .claude/skills/ 2>/dev/null | awk -F'/' '{print $3}' | sort -u)
    if [[ -n "$tracked_local_skills" ]]; then
        mkdir -p "$tmp_skills_dir/local"
        while IFS= read -r skill_dir; do
            if [[ -d ".claude/skills/$skill_dir" ]]; then
                cp -a ".claude/skills/$skill_dir" "$tmp_skills_dir/local/"
            fi
        done <<< "$tracked_local_skills"
    fi
fi

if command -v skillport >/dev/null 2>&1; then
    echo "Running skillport doc for ${OUTPUT_FILE}..."
    skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force
elif command -v uvx >/dev/null 2>&1; then
    echo "Running uvx skillport doc for ${OUTPUT_FILE}..."
    uvx skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force
else
    echo "Error: neither 'skillport' nor 'uvx' is available." >&2
    exit 1
fi

python3 - "$tmp_file" "$OUTPUT_FILE" "$tmp_skills_dir" <<'PY'
from __future__ import annotations

from pathlib import Path
import re
import sys


generated_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
tmp_skills_dir = sys.argv[3].rstrip("/")

start_marker = "<!-- SKILLPORT_START -->"
end_marker = "<!-- SKILLPORT_END -->"
external_note = """<!-- NOTE: External skills (anthropics/*, superpowers/*) are managed via apm.yml.
     They are automatically synchronized and locked using 'apm install'.
     IMPORTANT: Custom skills are tracked in Git. External namespaces should generally be ignored
     in the project root .gitignore (blacklist strategy) unless explicitly required for the repository's configuration. -->"""


def normalize_generated(text: str) -> str:
    prefix = re.escape(tmp_skills_dir)
    text = re.sub(prefix + r"/local/", ".claude/skills/", text)
    text = re.sub(prefix + r"/custom/", "agent-skills/custom/", text)
    text = re.sub(prefix + r"/", ".agents/skills/", text)

    text = text.replace(
        "If search returns too many results, use more specific terms",
        "If search returns 10+ results, refine your query",
    )
    text = re.sub(
        r"<description>Reference for the Claude API / Anthropic SDK.*?</description>",
        "<description>Reference for the Claude API / Anthropic SDK. Use when working with Claude/Anthropic APIs, model selection, pricing, tool use. Skip when working with other providers like OpenAI or Gemini.</description>",
        text,
    )

    if "<available_skills" in text and "External skills (anthropics/*, superpowers/*)" not in text:
        text = re.sub(
            r"(^\s*<available_skills(?:\s|>)?)",
            external_note + r"\n\1",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    start = text.find(start_marker)
    end = text.rfind(end_marker)
    if start != -1 and end > start:
        inner = text[start : end + len(end_marker)]
        inner = re.sub(r"<!-- SKILLPORT_START -->\s*\n+", start_marker + "\n", inner)
        inner = re.sub(r"\n+<!-- SKILLPORT_END -->", "\n" + end_marker, inner)
        inner = re.sub(r"\n{3,}", "\n\n", inner)
        text = text[:start].rstrip("\n") + "\n" + inner + "\n" + text[end + len(end_marker) :].lstrip("\n")
    return text


generated = normalize_generated(generated_path.read_text(encoding="utf-8"))

new_start = generated.find(start_marker)
new_end = generated.rfind(end_marker)
if new_start == -1 or new_end <= new_start:
    raise SystemExit("Error: generated SkillPort document is missing marker block")
new_block = generated[new_start : new_end + len(end_marker)]

if output_path.exists():
    original = output_path.read_text(encoding="utf-8")
    old_start = original.find(start_marker)
    old_end = original.rfind(end_marker)
    if old_start != -1 and old_end > old_start:
        original = original[:old_start] + new_block + original[old_end + len(end_marker) :]
        output_path.write_text(original, encoding="utf-8")
    else:
        output_path.write_text(generated, encoding="utf-8")
else:
    output_path.write_text(generated, encoding="utf-8")
PY

echo "[+] Successfully synchronized skill catalog: ${OUTPUT_FILE}"
