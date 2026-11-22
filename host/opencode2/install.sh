#!/usr/bin/env bash
# Explicit opt-in Host V2 installation; never installs/updates global OpenCode.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash host/opencode2/install.sh --check|--install
  --check    Print target paths, with no writes or npm execution.
  --install  Install pinned OpenCode V2 into a private prefix and create opencode2.
USAGE
}

if [[ $# -ne 1 ]]; then usage >&2; exit 64; fi
case "$1" in
  --check|--install) action="$1" ;;
  *) usage >&2; exit 64 ;;
esac
if [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
  printf 'install: HOME must be an absolute path\n' >&2
  exit 64
fi

version='2.3.2'
package="@opencode/cli@$version"
prefix="$HOME/.local/opt/opencode-v2-$version"
cli="$prefix/node_modules/.bin/opencode"
launcher_target="$HOME/.local/bin/opencode2"
config="$HOME/.config/opencode-v2/opencode/opencode.json"
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
launcher_source="$source_dir/opencode2"

printf 'OpenCode V2 package: %s\nV2 prefix: %s\nV2 launcher: %s\nV2 config: %s\n' \
  "$package" "$prefix" "$launcher_target" "$config"
if [[ "$action" == '--check' ]]; then exit 0; fi

if ! command -v npm >/dev/null 2>&1; then
  printf 'install: npm is required (nothing installed)\n' >&2
  exit 69
fi
if [[ ! -f "$launcher_source" || -L "$launcher_source" ]]; then
  printf 'install: launcher source is missing or symlinked\n' >&2
  exit 69
fi

# The v2 native CLI prints "opencode v2.3.2", while some wrappers/mocks
# print only "2.3.2". Accept only these exact version strings.
matches_pinned_version() {
  case "$1" in
    "$version"|"opencode v$version") return 0 ;;
    *) return 1 ;;
  esac
}

# Validate all existing targets BEFORE any installation writes. Never replace a
# different executable, unexpected prefix, or a symlinked config file.
if [[ -e "$prefix" || -L "$prefix" ]]; then
  if [[ -L "$prefix" || ! -d "$prefix" || ! -x "$cli" ]]; then
    printf 'install: unexpected V2 prefix; refusing to overwrite\n' >&2
    exit 73
  fi
  if ! actual="$("$cli" --version 2>&1)"; then
    printf 'install: existing V2 --version failed; refusing to overwrite\n' >&2
    exit 73
  fi
  if ! matches_pinned_version "$actual"; then
    printf 'install: installed V2 version mismatch (observed: %q); refusing to overwrite\n' "${actual:0:120}" >&2
    exit 73
  fi
fi
if [[ -e "$launcher_target" || -L "$launcher_target" ]]; then
  if [[ -L "$launcher_target" || ! -f "$launcher_target" ]] || ! cmp -s "$launcher_source" "$launcher_target"; then
    printf 'install: opencode2 already exists and differs; refusing to overwrite\n' >&2
    exit 73
  fi
fi
if [[ -L "$config" ]]; then
  printf 'install: V2 config must not be a symlink\n' >&2
  exit 73
fi
if [[ -e "$config" && ! -f "$config" ]]; then
  printf 'install: V2 config is not a regular file\n' >&2
  exit 73
fi

if [[ ! -e "$prefix" ]]; then
  parent="$(dirname -- "$prefix")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.opencode-v2-$version.XXXXXXXX")"
  trap 'rm -rf -- "$stage"' EXIT
  # npm >=11 requires project-local approval for dependency install scripts.
  # OpenCode needs its postinstall to select the platform binary. Approve only
  # the pinned CLI version; never enable all dependency lifecycle scripts.
  cat > "$stage/package.json" <<'PACKAGE'
{
  "name": "opencode-v2-host-private-install",
  "private": true,
  "allowScripts": {
    "@opencode/cli@2.3.2": true
  }
}
PACKAGE
  npm_config_cache="$HOME/.cache/opencode-v2/npm" \
    npm --prefix "$stage" install --no-save --no-package-lock --no-audit --no-fund \
      --strict-allow-scripts -- "$package"
  if [[ ! -x "$stage/node_modules/.bin/opencode" ]]; then
    printf 'install: npm did not provide an executable; refusing deployment\n' >&2
    exit 69
  fi
  if ! actual="$("$stage/node_modules/.bin/opencode" --version 2>&1)"; then
    printf 'install: staged V2 --version failed; refusing deployment\n' >&2
    exit 69
  fi
  if ! matches_pinned_version "$actual"; then
    printf 'install: unexpected npm CLI version (observed: %q); refusing deployment\n' "${actual:0:120}" >&2
    exit 69
  fi
  if [[ -e "$prefix" || -L "$prefix" ]]; then
    printf 'install: prefix appeared during installation; refusing deployment\n' >&2
    exit 73
  fi
  mv -T -- "$stage" "$prefix"
  trap - EXIT
fi

mkdir -p -- "$(dirname "$config")" "$(dirname "$launcher_target")"
if [[ ! -e "$config" ]]; then
  # Bash noclobber avoids truncating a concurrently created config.
  ( set -C; cat > "$config" <<'CONFIG'
{
  "$schema": "https://opencode.ai/config.json",
  "update": "disable",
  "plugins": [],
  "mcp": { "servers": {} }
}
CONFIG
  )
  chmod 600 -- "$config"
fi
if [[ ! -e "$launcher_target" ]]; then
  ( set -C; cat -- "$launcher_source" > "$launcher_target" )
  chmod 0755 -- "$launcher_target"
fi
printf 'Host V2 ready: %s\nRun: %s --version\n' "$launcher_target" "$launcher_target"
