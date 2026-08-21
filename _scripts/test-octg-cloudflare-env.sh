#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILES=(
  "$REPO_ROOT/apm.yml"
  "$REPO_ROOT/.env.example"
)
if [[ -f "$REPO_ROOT/opencode/opencode.jsonc" ]]; then
  CONFIG_FILES+=("$REPO_ROOT/opencode/opencode.jsonc")
fi

for file in "${CONFIG_FILES[@]}"; do
  for name in OCTG_CF_ACCOUNT_ID OCTG_CF_GATEWAY_ID OCTG_CF_API_TOKEN; do
    rg -q "$name" "$file"
  done
  if rg -q 'CLOUDFLARE_(ACCOUNT_ID|GATEWAY_ID|API_TOKEN)' "$file"; then
    printf 'Legacy Cloudflare environment variable found in %s\n' "$file" >&2
    exit 1
  fi
done

rg -q '^  cloudflare-ai-gateway-octg:' "$REPO_ROOT/apm.yml"
printf 'OCTG Cloudflare environment variables are configured.\n'
