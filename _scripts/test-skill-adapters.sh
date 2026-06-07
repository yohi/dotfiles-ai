#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_SKILLS_DIR="$REPO_ROOT/.agents/skills"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

assert_link_target() {
    link_path="$1"
    expected="$2"
    [ -L "$link_path" ] || fail "not a symlink: $link_path"
    actual="$(readlink "$link_path")"
    [ "$actual" = "$expected" ] || fail "$link_path points to $actual, expected $expected"
}

assert_runtime_skill_links() {
    [ -d "$RUNTIME_SKILLS_DIR" ] || fail "directory not found: $RUNTIME_SKILLS_DIR"

    found=0
    while IFS= read -r link_path; do
        found=1
        target="$(readlink "$link_path")"
        if [ "${target#/}" = "$target" ]; then
            target="$(dirname "$link_path")/$target"
        fi
        [ -e "$target" ] || fail "broken runtime skill link: $link_path -> $target"
    done < <(find "$RUNTIME_SKILLS_DIR" -type l)

    [ "$found" -eq 1 ] || fail "no runtime skill links found under $RUNTIME_SKILLS_DIR"
}

assert_no_runtime_skillport_agent_skills() {
    if grep -R "SKILLPORT_SKILLS_DIR.*agent-skills" \
        "$REPO_ROOT/.mcp.json" \
        "$REPO_ROOT/opencode.json" \
        "$REPO_ROOT/.codex/config.toml" \
        "$REPO_ROOT/antigravity/mcp_config.json" \
        "$REPO_ROOT/.agents/mcp_config.json" 2>/dev/null; then
        fail "generated config still points SkillPort at agent-skills"
    fi
}

assert_runtime_skill_links

assert_link_target "$HOME/.opencode/skills" "$RUNTIME_SKILLS_DIR"
assert_link_target "$HOME/.claude/skills" "$RUNTIME_SKILLS_DIR"
assert_link_target "$HOME/.skillport/skills" "$RUNTIME_SKILLS_DIR"

assert_no_runtime_skillport_agent_skills

printf 'PASS: skill adapters verified.\n'
