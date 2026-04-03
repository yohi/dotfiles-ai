#!/bin/sh
# Claude Code statusLine script
# Inspired by Powerlevel10k configuration (p10k lean style)
# Displays: user@host  cwd  git  model  context%

input=$(cat)

# --- Core info ---
user=$(whoami)
host=$(hostname -s)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
[ -z "$cwd" ] && cwd=$(pwd)

# Shorten home directory to ~
home_dir="$HOME"
short_cwd=$(case "$cwd" in "${home_dir}"*) printf '~%s' "${cwd#"$home_dir"}" ;; *) printf '%s' "$cwd" ;; esac)

# --- Git branch ---
git_branch=""
if git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
             || git -C "$cwd" describe --tags --exact-match 2>/dev/null \
             || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
    if [ -n "$branch" ]; then
        # Check dirty state (skip optional locks)
        if git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | grep -q .; then
            git_branch="${branch}*"
        else
            git_branch="${branch}"
        fi
    fi
fi

# --- Extract data with a single jq call ---
# (model, used_pct, five_hour, vim_mode)
IFS='	' read -r model used_pct five_hour vim_mode <<EOF
$(echo "$input" | jq -r '[.model.display_name, .context_window.used_percentage, .rate_limits.five_hour.used_percentage, .vim.mode] | map(. // "") | @tsv')
EOF

# --- Build output ---
# Colors (ANSI, dimmed-friendly)
RESET='\033[0m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
MAGENTA='\033[35m'
RED='\033[31m'

line=""

# user@host
line="${line}$(printf "${CYAN}%s@%s${RESET}" "$user" "$host")"

# cwd
line="${line}  $(printf "${BLUE}%s${RESET}" "$short_cwd")"

# git
if [ -n "$git_branch" ]; then
    line="${line}  $(printf "${GREEN}%s${RESET}" "$git_branch")"
fi

# model
if [ -n "$model" ]; then
    line="${line}  $(printf "${MAGENTA}%s${RESET}" "$model")"
fi

# context usage
if [ -n "$used_pct" ]; then
    pct_int=$(printf '%.0f' "$used_pct")
    if [ "$pct_int" -ge 80 ]; then
        line="${line}  $(printf "${RED}ctx:%s%%${RESET}" "$pct_int")"
    elif [ "$pct_int" -ge 50 ]; then
        line="${line}  $(printf "${YELLOW}ctx:%s%%${RESET}" "$pct_int")"
    else
        line="${line}  ctx:${pct_int}%"
    fi
fi

# 5-hour rate limit
if [ -n "$five_hour" ]; then
    five_int=$(printf '%.0f' "$five_hour")
    if [ "$five_int" -ge 80 ]; then
        line="${line}  $(printf "${RED}5h:%s%%${RESET}" "$five_int")"
    else
        line="${line}  5h:${five_int}%"
    fi
fi

# vim mode
if [ -n "$vim_mode" ]; then
    line="${line}  $(printf "${YELLOW}[%s]${RESET}" "$vim_mode")"
fi

printf "%s\n" "$line"
