#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

# 1. The legacy apm.yml-based generator must be removed.
if [ -e "$REPO_ROOT/_scripts/render-antigravity-config.py" ]; then
    fail "legacy generator still present: _scripts/render-antigravity-config.py"
fi

# 2. sync-antigravity must invoke the canonical lockfile-based generator.
if ! grep -q "sync_antigravity.py" "$REPO_ROOT/_mk/antigravity.mk"; then
    fail "_mk/antigravity.mk does not invoke sync_antigravity.py"
fi

# 3. No reference to the legacy generator may remain in the Make wiring.
if grep -q "render-antigravity-config.py" "$REPO_ROOT/_mk/antigravity.mk"; then
    fail "_mk/antigravity.mk still references render-antigravity-config.py"
fi

# 4. The removed uninstall-superpowers target must not be invoked anywhere in _mk.
if grep -rq "uninstall-superpowers" "$REPO_ROOT/_mk"; then
    fail "_mk still references removed target uninstall-superpowers"
fi

printf 'PASS: antigravity generator consolidation verified.\n'
