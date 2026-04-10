#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: skillport doc を実行して、agent-skills/ をソースに
#              AGENTS.md と global-rules/AGENTS.global.md の skill 一覧を
#              それぞれ直接更新する。
#

set -euo pipefail

# プロジェクトルートディレクトリに移動（どこから実行されても動作するように）
cd "$(dirname "$0")/.." || exit 1

readonly OUTPUT_FILES=(
    "AGENTS.md"
    "global-rules/AGENTS.global.md"
)

run_skillport_doc() {
    local output_file="$1"

    if command -v skillport >/dev/null 2>&1; then
        echo "Running skillport doc for ${output_file}..."
        skillport doc --mode mcp --output "$output_file" --force || {
            echo "Error: skillport doc failed for '$output_file'." >&2
            exit 1
        }
        return 0
    fi

    if command -v uvx >/dev/null 2>&1; then
        echo "Running uvx skillport doc for ${output_file}..."
        uvx skillport doc --mode mcp --output "$output_file" --force || {
            echo "Error: uvx skillport doc failed for '$output_file'." >&2
            exit 1
        }
        return 0
    fi

    echo "Error: 'skillport' command not found. Please install it." >&2
    exit 1
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
     See agent-skills/EXTERNAL_SKILLS.md for the authoritative external-skill lock file. -->'

    if grep -qF "<available_skills>" "$file_path" && ! grep -qF "External skills (anthropics/*, superpowers/*)" "$file_path"; then
        tmp_file=$(mktemp)
        awk -v note="$note" '
            $0 == "<available_skills>" {
                print note
                print
                next
            }
            { print }
        ' "$file_path" > "$tmp_file"
        mv "$tmp_file" "$file_path"
    fi
}

REPO_ROOT=$(pwd)

for output_file in "${OUTPUT_FILES[@]}"; do
    if [[ ! -f "$output_file" ]]; then
        echo "Error: Output file '$output_file' not found." >&2
        exit 1
    fi

    if [[ ! -w "$output_file" ]] || [[ ! -r "$output_file" ]]; then
        echo "Error: Output file '$output_file' is not accessible or writable." >&2
        exit 1
    fi

    run_skillport_doc "$output_file"
    normalize_locations "$output_file" "$REPO_ROOT"
    restore_external_skills_note "$output_file"
done

echo "✅ Successfully synchronized skill listings to AGENTS.md and global-rules/AGENTS.global.md."
