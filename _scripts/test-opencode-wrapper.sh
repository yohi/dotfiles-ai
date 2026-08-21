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
echo "OCTG_CF_ACCOUNT_ID=${OCTG_CF_ACCOUNT_ID:-unset}" >> "$MOCK_LOG"
echo "OCTG_CF_GATEWAY_ID=${OCTG_CF_GATEWAY_ID:-unset}" >> "$MOCK_LOG"
echo "OCTG_CF_API_TOKEN=${OCTG_CF_API_TOKEN:-unset}" >> "$MOCK_LOG"
EOF
# Inject MOCK_LOG path into the mock script
sed -i "s|\"\$MOCK_LOG\"|\"$MOCK_LOG\"|g" "$MOCK_BIN_DIR/opencode"
chmod +x "$MOCK_BIN_DIR/opencode"

export PATH="$MOCK_BIN_DIR:$PATH"

echo "  [0] Repository-local .env is loaded"
ENV_FIXTURE_ROOT="$TEST_SANDBOX/repo"
mkdir -p "$ENV_FIXTURE_ROOT/_scripts"
cp "$WRAPPER" "$ENV_FIXTURE_ROOT/_scripts/opencode-wrapper.sh"
chmod +x "$ENV_FIXTURE_ROOT/_scripts/opencode-wrapper.sh"
cat <<'EOF' > "$ENV_FIXTURE_ROOT/.env"
OCTG_CF_ACCOUNT_ID=test-account
OCTG_CF_GATEWAY_ID=test-gateway
OCTG_CF_API_TOKEN=test-token
EOF
rm -f "$MOCK_LOG"
if env -u OCTG_CF_ACCOUNT_ID -u OCTG_CF_GATEWAY_ID -u OCTG_CF_API_TOKEN \
    "$ENV_FIXTURE_ROOT/_scripts/opencode-wrapper.sh" personal --version >/dev/null 2>&1; then
    if grep -q "OCTG_CF_ACCOUNT_ID=test-account" "$MOCK_LOG" && \
       grep -q "OCTG_CF_GATEWAY_ID=test-gateway" "$MOCK_LOG" && \
       grep -q "OCTG_CF_API_TOKEN=test-token" "$MOCK_LOG"; then
        pass "repository-local .env values are exported to opencode"
    else
        fail "repository-local .env values were not exported to opencode"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed while loading repository-local .env"
    cat "$MOCK_LOG" 2>/dev/null || true
fi

# --- Test 1: personal profile via argument ---
echo "  [1] Profile arg: personal"
rm -f "$MOCK_LOG"
if "$WRAPPER" personal --version >/dev/null 2>&1; then
    if grep -q "OMO_PROFILE=personal" "$MOCK_LOG" 2>/dev/null; then
        pass "OMO_PROFILE=personal is set"
    else
        fail "OMO_PROFILE=personal not found in env"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for personal profile"
fi

# --- Test 2: work profile via argument ---
echo "  [2] Profile arg: work"
rm -f "$MOCK_LOG"
if "$WRAPPER" work --version >/dev/null 2>&1; then
    if grep -q "OMO_PROFILE=work" "$MOCK_LOG" 2>/dev/null; then
        pass "OMO_PROFILE=work is set"
    else
        fail "OMO_PROFILE=work not found in env"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for work profile"
fi

# --- Test 3: default profile (no arg) ---
echo "  [3] Default profile (no arg)"
rm -f "$MOCK_LOG"
if "$WRAPPER" --version >/dev/null 2>&1; then
    if grep -q "OMO_PROFILE=personal" "$MOCK_LOG" 2>/dev/null; then
        pass "Default profile is 'personal'"
    else
        fail "Default profile not 'personal'"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for default profile"
fi

# --- Test 4: PROFILE env var ---
echo "  [4] PROFILE env var override"
rm -f "$MOCK_LOG"
if PROFILE=work "$WRAPPER" --version >/dev/null 2>&1; then
    if grep -q "OMO_PROFILE=work" "$MOCK_LOG" 2>/dev/null; then
        pass "PROFILE=work env var sets OMO_PROFILE=work"
    else
        fail "PROFILE=work env var did not set OMO_PROFILE=work"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for PROFILE=work"
fi

# --- Test 4b: Invalid PROFILE env var fallback ---
echo "  [4b] Invalid PROFILE env var fallback"
rm -f "$MOCK_LOG"
if PROFILE=wrk "$WRAPPER" --version >/dev/null 2>&1; then
    if grep -q "OMO_PROFILE=personal" "$MOCK_LOG" 2>/dev/null; then
        pass "PROFILE=wrk falls back to OMO_PROFILE=personal"
    else
        fail "PROFILE=wrk did not fall back to personal"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for PROFILE=wrk"
fi

# --- Test 5: profile arg consumed & port forwarding ---
echo "  [5] Profile arg not forwarded & port forwarding check"
rm -f "$MOCK_LOG"
if "$WRAPPER" personal >/dev/null 2>&1; then
    if grep -q "CALL: opencode.*personal" "$MOCK_LOG" 2>/dev/null; then
        fail "'personal' was forwarded as arg to opencode"
        cat "$MOCK_LOG" 2>/dev/null || true
    else
        pass "'personal' arg is consumed by wrapper, not forwarded"
    fi

    # Check if --port parameter was added when port detected
    if command -v ss >/dev/null 2>&1; then
        EXPECTED_PORT=""
        for p in {4090..4100}; do
            if ! ss -tln | grep -q ":$p " >/dev/null 2>&1; then
                EXPECTED_PORT=$p
                break
            fi
        done

        if [ -n "$EXPECTED_PORT" ]; then
            if grep -q "CALL: opencode --port $EXPECTED_PORT" "$MOCK_LOG" 2>/dev/null; then
                pass "Detected port ($EXPECTED_PORT) was correctly forwarded to opencode"
            else
                fail "Port $EXPECTED_PORT was available but --port was not forwarded to opencode"
                cat "$MOCK_LOG" 2>/dev/null || true
            fi
        else
            skip "No available port found in 4090..4100 range"
        fi
    else
        skip "ss command not available for port detection test"
    fi
else
    fail "Wrapper invocation failed for no-arg invocation"
fi

# --- Test 6: SKILLPORT_SKILLS_DIR is set ---
echo "  [6] SKILLPORT_SKILLS_DIR is exported"
rm -f "$MOCK_LOG"
if "$WRAPPER" personal --version >/dev/null 2>&1; then
    if grep -q "SKILLPORT_SKILLS_DIR=" "$MOCK_LOG" 2>/dev/null && \
       ! grep -q "SKILLPORT_SKILLS_DIR=unset" "$MOCK_LOG" 2>/dev/null; then
        pass "SKILLPORT_SKILLS_DIR is set"
    else
        fail "SKILLPORT_SKILLS_DIR is not set"
        cat "$MOCK_LOG" 2>/dev/null || true
    fi
else
    fail "Wrapper invocation failed for SKILLPORT_SKILLS_DIR test"
fi

# --- Test 7: opencode/omo.jsonc profiles sanity check ---
echo "  [7] opencode/omo.jsonc has profiles.personal and profiles.work"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_OMO_JSONC="$REPO_ROOT/opencode/omo.jsonc"
if [ -f "$REPO_OMO_JSONC" ]; then
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

raw = open('$REPO_OMO_JSONC', encoding='utf-8').read()
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
        pass "opencode/omo.jsonc has valid profiles.personal (non-bedrock) and profiles.work (bedrock)"
    else
        fail "opencode/omo.jsonc profiles structure invalid"
    fi
else
    fail "opencode/omo.jsonc not found in repo"
fi

# --- Test 8: ~/.omo/omo.jsonc symlink contract check ---
echo "  [8] ~/.omo/omo.jsonc symlink contract check"
HOME_OMO_JSONC="$HOME/.omo/omo.jsonc"
if [ -L "$HOME_OMO_JSONC" ]; then
    LINK_TARGET=$(readlink -f "$HOME_OMO_JSONC")
    EXPECTED_TARGET=$(readlink -f "$REPO_OMO_JSONC")
    if [ "$LINK_TARGET" = "$EXPECTED_TARGET" ]; then
        pass "~/.omo/omo.jsonc correctly links to repo opencode/omo.jsonc"
    else
        fail "~/.omo/omo.jsonc links to $LINK_TARGET instead of $EXPECTED_TARGET"
    fi
elif [ -f "$HOME_OMO_JSONC" ]; then
    skip "~/.omo/omo.jsonc exists but is a regular file (not a symlink)"
else
    skip "~/.omo/omo.jsonc does not exist"
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
