#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: skillport doc を実行して、agent-skills/ をソースに
#              global-rules/AGENTS.global.md の skill 一覧を
#              直接更新する。
#

set -euo pipefail

# プロジェクトルートディレクトリに移動（どこから実行されても動作するように）
cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILES=(
    "global-rules/AGENTS.global.md"
)

run_skillport_doc() {
    local output_file="$1"
    local tmp_file
    tmp_file=$(mktemp)

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: skillport doc failed." >&2; rm "$tmp_file"; exit 1
        }
    elif command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport doc --mode mcp --output "$tmp_file" --force || {
            echo "Error: uvx skillport doc failed." >&2; rm "$tmp_file"; exit 1
        }
    else
        echo "Error: 'skillport' command not found." >&2; rm "$tmp_file"; exit 1
    fi

    if [[ -f "$output_file" ]] && grep -q "<!-- SKILLPORT_START -->" "$output_file" && grep -q "<!-- SKILLPORT_END -->" "$output_file"; then
        echo "Updating SkillPort section in existing ${output_file}..."
        perl -0777 -i -pe "BEGIN{undef $/; open(F, '<', '$tmp_file') or die; \$s=<F>; close F;} s/<!-- SKILLPORT_START -->.*?<!-- SKILLPORT_END -->/\$s/gs" "$output_file"
    else
        echo "Writing initial skill listings to ${output_file}..."
        cp "$tmp_file" "$output_file"
    fi
    rm "$tmp_file"
}

normalize_locations() {
    local file_path="$1"
    local repo_root="$2"

    perl -0pi -e "s|(<location>)\Q${repo_root}/\E|\$1|g" "$file_path"
}

restore_external_skills_note() {
    local file_path="$1"
    local note
    local tmp_file

    note='<!-- NOTE: External skills (anthropics/*, superpowers/*) must be installed via:
     skillport add <pkg> agent-skills/<ns> --namespace <ns>
     (e.g., skillport add anthropics/algorithmic-art agent-skills/anthropics --namespace anthropics)
     See agent-skills/EXTERNAL_SKILLS.md for the authoritative external-skill lock file.
     IMPORTANT: Custom skills are tracked in Git, but external namespaces must be ignored
     in the project root .gitignore (blacklist strategy) to avoid polluting the repo. -->'

    if grep -Eq '^[[:space:]]*<available_skills([[:space:]]|>)' "$file_path" && ! grep -qF "External skills (anthropics/*, superpowers/*)" "$file_path"; then
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

echo "✅ Successfully synchronized skill listings to global-rules/AGENTS.global.md."
