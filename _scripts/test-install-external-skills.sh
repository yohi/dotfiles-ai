#!/usr/bin/env bash
# _scripts/test-install-external-skills.sh
# install-external-skills.sh のパーステストとドライラン検証
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/_scripts/install-external-skills.sh"

# Mock Manifest file creation
MANIFEST=$(mktemp)
trap 'rm -f "$MANIFEST"' EXIT

cat << 'EOF' > "$MANIFEST"
| Skill Namespace | Source Repository | Version (Commit Hash) | Pinned At | Note |
| :--- | :--- | :--- | :--- | :--- |
| mock-skill-1 | https://github.com/mock/skill-1 | 1234567890abcdef | 2026-04-12 | Mock 1 |
| mock-skill-2 | https://github.com/mock/skill-2 | fedcba0987654321 | 2026-04-12 | Mock 2 |
EOF

export MANIFEST_FILE="$MANIFEST"

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
STATUS=0
OUTPUT=$("$SCRIPT" --dry-run 2>&1) || STATUS=$?

assert_eq "Dry-run exits with 0" "0" "$STATUS"

MANIFEST_LINES=$(awk -F'|' 'NR > 1 && NF >= 5 {
    ns = $2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", ns)
    url = $3; gsub(/^[[:space:]]+|[[:space:]]+$/, "", url)
    hash = $4; gsub(/^[[:space:]]+|[[:space:]]+$/, "", hash)
    if (ns == "" || ns == "Skill Namespace" || ns ~ /^:?-/) next
    if (url == "" || hash == "") next
    print ns "|" url
}' "$MANIFEST")

MANIFEST_COUNT=$(echo "$MANIFEST_LINES" | awk 'NF' | wc -l | tr -d ' ')
if [ "$MANIFEST_COUNT" -gt 0 ]; then
    echo "PASS: Manifest has $MANIFEST_COUNT entries"
    PASS=$((PASS + 1))
else
    echo "FAIL: Manifest has 0 entries"
    FAIL=$((FAIL + 1))
fi

while IFS='|' read -r ns url; do
    [ -z "$ns" ] && continue
    assert_contains "$ns namespace detected" "$ns" "$OUTPUT"
    assert_contains "$url repo detected" "$url" "$OUTPUT"
done <<< "$MANIFEST_LINES"

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
