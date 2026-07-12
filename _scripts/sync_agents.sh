#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: Generate agent-skills/AVAILABLE_SKILLS.md and global-rules/AGENTS.global.md
# from the runtime .agents/skills tree, local custom skills under agent-skills/custom,
# and project-local skills tracked under .claude/skills/.
#

set -euo pipefail

# プロジェクトルートディレクトリに移動（どこから実行されても動作するように）
cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILES=(
    "agent-skills/AVAILABLE_SKILLS.md"
    "global-rules/AGENTS.global.md"
)

run_skillport_doc() {
    local output_file="$1"
    local tmp_file
    tmp_file=$(mktemp)

    # Create temporary combined skills directory
    local tmp_skills_dir
    tmp_skills_dir=$(mktemp -d)

    # Combine runtime skills first (using cp -a to preserve symlinks)
    if [ -d ".agents/skills" ]; then
        cp -a .agents/skills/. "$tmp_skills_dir/"
    fi

    # Overlay custom skills (using cp -a to preserve symlinks and checking if not empty)
    if [ -d "agent-skills/custom" ] && [ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]; then
        mkdir -p "$tmp_skills_dir/custom"
        cp -a agent-skills/custom/. "$tmp_skills_dir/custom/"
    fi

    # Overlay project-local skills tracked under .claude/skills/
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

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: skillport doc failed." >&2
            rm -rf "${tmp_skills_dir}" "${tmp_file}"
            exit 1
        }
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: uvx skillport doc failed." >&2
            rm -rf "${tmp_skills_dir}" "${tmp_file}"
            exit 1
        }
    else
        echo "Error: 'skillport' command not found." >&2
        rm -rf "${tmp_skills_dir}" "${tmp_file}"
        exit 1
    fi

    # Escape regex/sed metacharacters from tmp_skills_dir
    local escaped_tmp_skills_dir
    escaped_tmp_skills_dir=$(printf '%s' "${tmp_skills_dir}" | sed 's/[.[\*^$/|&]/\\&/g')

    # Replace temporary skills directory paths with real repo-relative paths in the temp file
    sed -i "s|${escaped_tmp_skills_dir}/local/|.claude/skills/|g" "$tmp_file"
    sed -i "s|${escaped_tmp_skills_dir}/custom/|agent-skills/custom/|g" "$tmp_file"
    sed -i "s|${escaped_tmp_skills_dir}/|.agents/skills/|g" "$tmp_file"

    # Normalize whitespace inside the generated SkillPort block so that repeated
    # syncs do not produce blank-line-only diffs in AGENTS.md files.
    # - Trim leading blank lines before the first marker.
    # - Trim trailing blank lines after the last marker.
    # - Collapse runs of blank lines inside the block to a single blank line.
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$tmp_file" <<'PY'
from pathlib import Path
import re
import sys
import re

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")

start = text.find("<!-- SKILLPORT_START -->")
end = text.rfind("<!-- SKILLPORT_END -->")

if start != -1 and end != -1 and end > start:
    prefix = text[:start].rstrip("\n")
    inner = text[start:end + len("<!-- SKILLPORT_END -->")]
    suffix = text[end + len("<!-- SKILLPORT_END -->"):].lstrip("\n")

    # Remove leading blank lines after the start marker.
    inner = re.sub(r"^(<!-- SKILLPORT_START -->\s*\n+)", r"\1", inner)
    # Actually strip all newlines after start marker, let single newline follow.
    inner = re.sub(r"<!-- SKILLPORT_START -->\s*\n+", "<!-- SKILLPORT_START -->\n", inner)
    inner = re.sub(r"\n+<!-- SKILLPORT_END -->", "\n<!-- SKILLPORT_END -->", inner)

    # Collapse 3+ consecutive newlines (i.e. 2+ blank lines) to 2 newlines (1 blank line).
    inner = re.sub(r"\n{3,}", "\n\n", inner)

    text = prefix + "\n" + inner + "\n" + suffix

p.write_text(text, encoding="utf-8")
PY
    fi

    if [[ -f "$output_file" ]] && grep -q "<!-- SKILLPORT_START -->" "$output_file" && grep -q "<!-- SKILLPORT_END -->" "$output_file"; then
        echo "Updating SkillPort section in existing ${output_file}..."
        # Replace the SkillPort block while preserving the blank lines that
        # existed immediately before and after the markers in the original file.
        if command -v python3 >/dev/null 2>&1; then
            python3 - "$tmp_file" "$output_file" <<'PY'
from pathlib import Path
import sys

tmp = Path(sys.argv[1]).read_text(encoding="utf-8")
orig = Path(sys.argv[2]).read_text(encoding="utf-8")

start_marker = "<!-- SKILLPORT_START -->"
end_marker = "<!-- SKILLPORT_END -->"

# Extract inner block from generated tmp file.
tmp_start = tmp.find(start_marker)
tmp_end = tmp.rfind(end_marker)
if tmp_start == -1 or tmp_end == -1 or tmp_end <= tmp_start:
    sys.exit(0)
new_inner = tmp[tmp_start:tmp_end + len(end_marker)]

# Split original file around the markers, keeping surrounding whitespace.
orig_start = orig.find(start_marker)
orig_end = orig.rfind(end_marker)
if orig_start == -1 or orig_end == -1 or orig_end <= orig_start:
    sys.exit(0)

orig_prefix = orig[:orig_start]
orig_suffix = orig[orig_end + len(end_marker):]

Path(sys.argv[2]).write_text(orig_prefix + new_inner + orig_suffix, encoding="utf-8")
PY
        else
            # Fallback for environments without python3.
            perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
        fi
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi

    # Normalize runs of blank lines inside the generated SkillPort block to a
    # single blank line, but leave the whitespace around the markers untouched.
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$output_file" <<'PY'
from pathlib import Path
import re
import sys
import re

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")

start = text.find("<!-- SKILLPORT_START -->")
end = text.rfind("<!-- SKILLPORT_END -->")

if start != -1 and end != -1 and end > start:
    inner = text[start:end + len("<!-- SKILLPORT_END -->")]

    # Ensure exactly one newline follows the start marker and one precedes the end marker.
    inner = re.sub(r"<!-- SKILLPORT_START -->\s*\n+", "<!-- SKILLPORT_START -->\n", inner)
    inner = re.sub(r"\n+<!-- SKILLPORT_END -->", "\n<!-- SKILLPORT_END -->", inner)

    # Collapse runs of 3+ newlines (i.e. 2+ blank lines) to a single blank line.
    inner = re.sub(r"\n{3,}", "\n\n", inner)

    text = text[:start] + inner + text[end + len("<!-- SKILLPORT_END -->"):]

p.write_text(text, encoding="utf-8")
PY
    fi

    rm -rf "${tmp_skills_dir}" "${tmp_file}"
}

normalize_locations() {
    local file_path="$1"
    local repo_root="$2"

    perl -0pi -e "s|(<location>)\Q${repo_root}/\E|\$1|g" "$file_path"
    # Fix vague tips from skillport doc
    sed -i 's/If search returns too many results, use more specific terms/If search returns 10+ results, refine your query/' "$file_path"
    # Fix overly complex sentence for anthropics/claude-api
    sed -i 's|<description>Reference for the Claude API / Anthropic SDK.*</description>|<description>Reference for the Claude API / Anthropic SDK. Use when working with Claude/Anthropic APIs, model selection, pricing, tool use. Skip when working with other providers like OpenAI or Gemini.</description>|g' "$file_path"
}

restore_external_skills_note() {
    local file_path="$1"
    local note
    local tmp_file

    note='<!-- NOTE: External skills (anthropics/*, superpowers/*) are managed via apm.yml.
     They are automatically synchronized and locked using '\''apm install'\''.
     IMPORTANT: Custom skills are tracked in Git. External namespaces should generally be ignored
     in the project root .gitignore (blacklist strategy) unless explicitly required for the repository'\''s configuration. -->'

    # check if the note already exists anywhere in the file (not just after run_skillport_doc)
    if grep -Eq '^[[:space:]]*<available_skills([[:space:]]|>)' "$file_path" && ! grep -q "External skills (anthropics/\*, superpowers/\*)" "$file_path"; then
        tmp_file=$(mktemp)
        awk -v note="$note" '
            $0 ~ /^[[:space:]]*<available_skills([[:space:]]|>)/ {
                print note
                print
                next
            }
            { print }
        ' "$file_path" > "$tmp_file" || { rm -f "$tmp_file"; return 1; }
        mv "$tmp_file" "$file_path" || { rm -f "$tmp_file"; return 1; }
        rm -f "$tmp_file"
    fi
}

REPO_ROOT=$(pwd)

for output_file in "${OUTPUT_FILES[@]}"; do
    output_dir=$(dirname "$output_file")
    if [[ ! -d "$output_dir" ]] || [[ ! -w "$output_dir" ]]; then
        echo "Error: Output directory '$output_dir' does not exist or is not writable." >&2
        exit 1
    fi

    if [[ -e "$output_file" ]]; then
        if [[ ! -f "$output_file" ]] || [[ ! -w "$output_file" ]] || [[ ! -r "$output_file" ]]; then
            echo "Error: Output file '$output_file' exists but is not a regular file or not accessible." >&2
            exit 1
        fi
    fi

    run_skillport_doc "$output_file"
    normalize_locations "$output_file" "$REPO_ROOT"
    restore_external_skills_note "$output_file"
done

echo "[+] Successfully synchronized skill listings."
