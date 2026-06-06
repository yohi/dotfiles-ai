#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: skillport doc を実行して、agent-skills/ をソースに
#              global-rules/AGENTS.global.md および AGENTS.md の skill 一覧を
#              直接更新する。
#

set -euo pipefail

# プロジェクトルートディレクトリに移動（どこから実行されても動作するように）
cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILES=(
    "agent-skills/AVAILABLE_SKILLS.md"
)

run_skillport_doc() {
    local output_file="$1"
    local tmp_file
    tmp_file=$(mktemp)

    # Create temporary combined skills directory
    local tmp_skills_dir
    tmp_skills_dir=$(mktemp -d)
    # Ensure cleanup on exit (expand variables now so trap executes with absolute paths at exit time)
    trap "rm -rf '${tmp_skills_dir}' '${tmp_file}'" EXIT INT TERM

    # Combine custom skills (using cp -a to preserve symlinks and checking if not empty)
    if [ -d "agent-skills/custom" ] && [ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]; then
        mkdir -p "$tmp_skills_dir/custom"
        cp -a agent-skills/custom/. "$tmp_skills_dir/custom/"
    fi

    # Combine external skills (using cp -a to preserve symlinks and checking if not empty)
    if [ -d ".agents/skills" ]; then
        for ns_dir in .agents/skills/*; do
            [ -d "$ns_dir" ] || continue
            [ -n "$(ls -A "$ns_dir" 2>/dev/null)" ] || continue
            local ns
            ns=$(basename "$ns_dir")
            mkdir -p "$tmp_skills_dir/$ns"
            cp -a "$ns_dir"/. "$tmp_skills_dir/$ns/"
        done
    fi

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: skillport doc failed." >&2; exit 1
        }
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport --skills-dir "$tmp_skills_dir" doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: uvx skillport doc failed." >&2; exit 1
        }
    else
        echo "Error: 'skillport' command not found." >&2; exit 1
    fi

    # Escape regex/sed metacharacters from tmp_skills_dir
    local escaped_tmp_skills_dir
    escaped_tmp_skills_dir=$(printf '%s' "${tmp_skills_dir}" | sed 's/[.[\*^$/|&]/\\&/g')

    # Replace temporary skills directory paths with real repo-relative paths in the temp file
    sed -i "s|${escaped_tmp_skills_dir}/custom/|agent-skills/custom/|g" "$tmp_file"
    sed -i "s|${escaped_tmp_skills_dir}/|.agents/skills/|g" "$tmp_file"

    if [[ -f "$output_file" ]] && grep -q "<!-- SKILLPORT_START -->" "$output_file" && grep -q "<!-- SKILLPORT_END -->" "$output_file"; then
        echo "Updating SkillPort section in existing ${output_file}..."
        # Slurp the entire tmp_file into $s and perform a tag-based replacement in the output_file.
        # This replaces everything between SKILLPORT_START and SKILLPORT_END tags.
        perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi
}

normalize_locations() {
    local file_path="$1"
    local repo_root="$2"

    perl -0pi -e "s|(<location>)\Q${repo_root}/\E|\$1|g" "$file_path"
    # Fix vague tips from skillport doc
    sed -i 's/If search returns too many results, use more specific terms/If search returns 10+ results, refine your query/' "$file_path"
    # Fix overly complex sentence for anthropics/claude-api
    sed -i 's|<description>Build, debug, and optimize Claude API \/ Anthropic SDK apps.*</description>|<description>Build apps with Claude API/Anthropic SDK. Trigger on: imports (anthropic, @anthropic-ai/sdk) or direct requests. Not for: openai, ML tasks.</description>|g' "$file_path"
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
        trap 'rm -f "$tmp_file"' EXIT INT TERM
        awk -v note="$note" '
            $0 ~ /^[[:space:]]*<available_skills([[:space:]]|>)/ {
                print note
                print
                next
            }
            { print }
        ' "$file_path" > "$tmp_file"
        mv "$tmp_file" "$file_path"
        trap - EXIT INT TERM
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

echo "✅ Successfully synchronized skill listings."
