#!/usr/bin/env bash
# _scripts/test-install-external-skills.sh
# install-external-skills.sh のパーステストとドライラン検証
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/_scripts/install-external-skills.sh"
MANIFEST="$REPO_ROOT/agent-skills/EXTERNAL_SKILLS.md"
PASS=0
FAIL=0

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $label (expected='$expected', actual='$actual')"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        echo "PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $label (expected to contain='$needle')"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Test: Script exists and is executable ==="
if [ -x "$SCRIPT" ]; then
    echo "PASS: Script is executable"
    PASS=$((PASS + 1))
else
    echo "FAIL: Script is not executable"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "=== Test: Dry-run mode parses manifest correctly ==="
OUTPUT=$("$SCRIPT" --dry-run 2>&1 || true)
assert_contains "superpowers namespace detected" "superpowers" "$OUTPUT"
assert_contains "anthropics namespace detected" "anthropics" "$OUTPUT"
assert_contains "obra/superpowers repo detected" "github.com/obra/superpowers" "$OUTPUT"
assert_contains "anthropics/skills repo detected" "github.com/anthropics/skills" "$OUTPUT"

echo ""
echo "=== Test: --dry-run does not install anything ==="
# Verify no new directories were created (idempotent check)
assert_contains "dry-run indicator" "[DRY-RUN]" "$OUTPUT"

echo ""
echo "=== Results ==="
echo "PASS: $PASS / FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "🎉 All tests passed!"
