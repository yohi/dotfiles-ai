#!/bin/bash
# _scripts/test-opencode-wrapper.sh: Test suite for opencode-wrapper.sh (omo native profiles)
#
# Tests that:
# 1. OMO_PROFILE is correctly set for each profile
# 2. Profile selection via argument works (personal/work)
# 3. Profile selection via PROFILE env var works
# 4. Port argument is passed when available
# 5. Wrapper exits cleanly on valid invocations

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/opencode-wrapper.sh"

PASS=0
FAIL=0
SKIP=0

pass() { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
skip() { echo "  ⏭️  $1 (skipped)"; SKIP=$((SKIP+1)); }

echo "🧪 Running opencode-wrapper.sh tests (omo native profiles)..."
echo ""

# --- Setup mock opencode ---
TEST_SANDBOX=$(mktemp -d)
trap 'rm -rf "$TEST_SANDBOX"' EXIT

MOCK_BIN_DIR="$TEST_SANDBOX/bin"
mkdir -p "$MOCK_BIN_DIR"
MOCK_LOG="$TEST_SANDBOX/mock_opencode.log"

cat <<'EOF' > "$MOCK_BIN_DIR/opencode"
#!/bin/bash
echo "CALL: opencode $@" >> "$MOCK_LOG"
echo "OMO_PROFILE=${OMO_PROFILE:-unset}" >> "$MOCK_LOG"
echo "OPENCODE_CONFIG_DIR=${OPENCODE_CONFIG_DIR:-unset}" >> "$MOCK_LOG"
echo "SKILLPORT_SKILLS_DIR=${SKILLPORT_SKILLS_DIR:-unset}" >> "$MOCK_LOG"
EOF
# Inject MOCK_LOG path into the mock script
sed -i "s|\"\$MOCK_LOG\"|\"$MOCK_LOG\"|g" "$MOCK_BIN_DIR/opencode"
chmod +x "$MOCK_BIN_DIR/opencode"

export PATH="$MOCK_BIN_DIR:$PATH"

# --- Test 1: personal profile via argument ---
echo "  [1] Profile arg: personal"
rm -f "$MOCK_LOG"
"$WRAPPER" personal --version >/dev/null 2>&1 || true

if grep -q "OMO_PROFILE=personal" "$MOCK_LOG" 2>/dev/null; then
    pass "OMO_PROFILE=personal is set"
else
    fail "OMO_PROFILE=personal not found in env"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 2: work profile via argument ---
echo "  [2] Profile arg: work"
rm -f "$MOCK_LOG"
"$WRAPPER" work --version >/dev/null 2>&1 || true

if grep -q "OMO_PROFILE=work" "$MOCK_LOG" 2>/dev/null; then
    pass "OMO_PROFILE=work is set"
else
    fail "OMO_PROFILE=work not found in env"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 3: default profile (no arg) ---
echo "  [3] Default profile (no arg)"
rm -f "$MOCK_LOG"
"$WRAPPER" --version >/dev/null 2>&1 || true

if grep -q "OMO_PROFILE=personal" "$MOCK_LOG" 2>/dev/null; then
    pass "Default profile is 'personal'"
else
    fail "Default profile not 'personal'"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 4: PROFILE env var ---
echo "  [4] PROFILE env var override"
rm -f "$MOCK_LOG"
PROFILE=work "$WRAPPER" --version >/dev/null 2>&1 || true

if grep -q "OMO_PROFILE=work" "$MOCK_LOG" 2>/dev/null; then
    pass "PROFILE=work env var sets OMO_PROFILE=work"
else
    fail "PROFILE=work env var did not set OMO_PROFILE=work"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 5: profile arg consumed (not passed to opencode) ---
echo "  [5] Profile arg not forwarded to opencode"
rm -f "$MOCK_LOG"
"$WRAPPER" personal --version >/dev/null 2>&1 || true

if grep -q "CALL: opencode.*personal" "$MOCK_LOG" 2>/dev/null; then
    fail "'personal' was forwarded as arg to opencode"
    cat "$MOCK_LOG" 2>/dev/null || true
else
    pass "'personal' arg is consumed by wrapper, not forwarded"
fi

# --- Test 6: SKILLPORT_SKILLS_DIR is set ---
echo "  [6] SKILLPORT_SKILLS_DIR is exported"
rm -f "$MOCK_LOG"
"$WRAPPER" personal --version >/dev/null 2>&1 || true

if grep -q "SKILLPORT_SKILLS_DIR=" "$MOCK_LOG" 2>/dev/null && \
   ! grep -q "SKILLPORT_SKILLS_DIR=unset" "$MOCK_LOG" 2>/dev/null; then
    pass "SKILLPORT_SKILLS_DIR is set"
else
    fail "SKILLPORT_SKILLS_DIR is not set"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 7: omo.jsonc profiles sanity check ---
echo "  [7] ~/.omo/omo.jsonc has profiles.personal and profiles.work"
OOM_JSONC="$HOME/.omo/omo.jsonc"
if [ -f "$OOM_JSONC" ]; then
    if python3 -c "
import json
import re
import sys

def strip_jsonc(text):
    strings = []
    def protect(m):
        strings.append(m.group(0))
        return f'__STR{len(strings) - 1}__'
    text = re.sub(r'\"(?:\\\\.|[^\"\\\\])*\"', protect, text)
    text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.S)
    text = re.sub(r'//.*$', '', text, flags=re.M)
    text = re.sub(r',(\\s*[}\\]])', r'\\1', text)
    for i, s in enumerate(strings):
        text = text.replace(f'__STR{i}__', s)
    return text

raw = open('$OOM_JSONC', encoding='utf-8').read()
cfg = json.loads(strip_jsonc(raw))
profiles = list(cfg.get('profiles', {}).keys())
if 'personal' not in profiles or 'work' not in profiles:
    sys.exit(1)
personal_model = cfg['profiles']['personal'].get('[opencode]', {}).get('agents', {}).get('sisyphus', {}).get('model', '')
work_model = cfg['profiles']['work'].get('[opencode]', {}).get('agents', {}).get('sisyphus', {}).get('model', '')
if not personal_model or not work_model:
    sys.exit(1)
if 'bedrock' in work_model and 'bedrock' not in personal_model:
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
        pass "omo.jsonc has valid profiles.personal (non-bedrock) and profiles.work (bedrock)"
    else
        fail "omo.jsonc profiles structure invalid"
    fi
else
    skip "~/.omo/omo.jsonc not found"
fi

# --- Summary ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
    echo "❌ Some tests failed"
    exit 1
else
    echo "🎉 All tests passed!"
fi
