#!/bin/bash

set -euo pipefail

# Read JSON input from stdin
input=$(cat)

# Extract values from JSON
current_dir=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model_name=$(echo "$input" | jq -r '.model.display_name // "Claude"')
output_style=$(echo "$input" | jq -r '.output_style.name // ""')

# Get current user and hostname
user=$(whoami)
host=$(hostname -s)

# Get git branch if in a git repository
git_branch=""
if git -c core.fileMode=false rev-parse --git-dir > /dev/null 2>&1; then
    git_branch=$(git -c core.fileMode=false branch --show-current 2>/dev/null || echo "")
    if [ -n "$git_branch" ]; then
        # Check for uncommitted changes (skip optional locks)
        if ! git -c core.fileMode=false diff --quiet 2>/dev/null || ! git -c core.fileMode=false diff --cached --quiet 2>/dev/null; then
            git_branch="${git_branch}*"
        fi
    fi
fi

# Get short directory path (replace home with ~)
short_dir="${current_dir/#$HOME/~}"

# Build status line with colors (using printf for ANSI codes)
status=""

# Add user@host in blue
status="${status}$(printf '\033[34m[%s@%s]\033[0m' "$user" "$host")"

# Add directory in default color
status="${status} ${short_dir}"

# Add git branch in green if available
if [ -n "$git_branch" ]; then
    status="${status} $(printf '\033[32m(%s)\033[0m' "$git_branch")"
fi

# Add model name in cyan
status="${status} $(printf '\033[36m[%s]\033[0m' "$model_name")"

# Add output style if set
if [ -n "$output_style" ] && [ "$output_style" != "default" ]; then
    status="${status} $(printf '\033[33m<%s>\033[0m' "$output_style")"
fi

# Try to add ccusage if available
ccusage_info=""
if command -v bunx >/dev/null 2>&1; then
    ccusage_info=$(bunx -y ccusage statusline --visual-burn-rate emoji 2>/dev/null || echo "")
elif command -v bun >/dev/null 2>&1; then
    if [ -d "${HOME}/.bun/bin" ]; then
        export PATH="${HOME}/.bun/bin:${PATH}"
    fi
    ccusage_info=$(bun x ccusage statusline --visual-burn-rate emoji 2>/dev/null || echo "")
fi

if [ -n "$ccusage_info" ]; then
    status="${status} ${ccusage_info}"
fi

echo "$status"
