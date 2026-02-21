#!/bin/bash

set -euo pipefail

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BASE_CONFIG_PATH="${ROOT_DIR}/opencode/oh-my-opencode.base.jsonc"
CONFIG_PATH="${ROOT_DIR}/opencode/oh-my-opencode.jsonc"
PATTERNS_DIR="${ROOT_DIR}/opencode/patterns"
PATTERN_START="// @pattern:start"
PATTERN_END="// @pattern:end"

ensure_base_exists() {
  if [[ ! -f "${BASE_CONFIG_PATH}" ]]; then
    log_error "ベース設定ファイルが見つかりません: ${BASE_CONFIG_PATH}"
    exit 1
  fi
}

ensure_pattern_marker_exists() {
  if ! grep -q "${PATTERN_START}" "${BASE_CONFIG_PATH}"; then
    log_error "パターン開始マーカーが見つかりません: ${PATTERN_START}"
    exit 1
  fi

  if ! grep -q "${PATTERN_END}" "${BASE_CONFIG_PATH}"; then
    log_error "パターン終了マーカーが見つかりません: ${PATTERN_END}"
    exit 1
  fi
}

init_patterns() {
  mkdir -p "${PATTERNS_DIR}"

  shopt -s nullglob
  local existing=("${PATTERNS_DIR}"/*.jsonc)
  shopt -u nullglob

  if [[ ${#existing[@]} -eq 0 ]]; then
    if [[ -f "${CONFIG_PATH}" ]]; then
      extract_current_pattern "default" > "${PATTERNS_DIR}/default.jsonc"
    else
      cat > "${PATTERNS_DIR}/default.jsonc" <<'EOF'
{
  "description": "default",
  "agents": {},
  "categories": {}
}
EOF
      log_warn "CONFIG_PATH が存在しないため、空の default パターンを作成しました: ${PATTERNS_DIR}/default.jsonc"
    fi
    log_info "初期パターンを作成しました: ${PATTERNS_DIR}/default.jsonc"
  fi
}

ensure_generated_config() {
  if [[ ! -f "${CONFIG_PATH}" ]]; then
    init_patterns
    apply_pattern "default"
  fi
}

get_pattern_description() {
  local source="$1"
  local value
  value=$(awk -F '"' '/"description"\s*:/ {print $4; exit}' "${source}")
  if [[ -z "${value}" ]]; then
    value="説明なし"
  fi
  echo "${value}"
}

list_patterns() {
  shopt -s nullglob
  local files=("${PATTERNS_DIR}"/*.jsonc)
  shopt -u nullglob

  local file
  for file in "${files[@]}"; do
    local name
    local desc
    name="$(basename "${file}" .jsonc)"
    desc="$(get_pattern_description "${file}")"
    printf '%s|%s\n' "${name}" "${desc}"
  done
}

pattern_labels() {
  local line
  while IFS= read -r line; do
    local name="${line%%|*}"
    local desc="${line#*|}"
    printf '%s\n' "${name} - ${desc}"
  done
}

save_current_pattern() {
  local name
  read -r -p "保存名を入力してください（英数字・.-_のみ）: " name

  if [[ -z "${name}" ]]; then
    log_error "保存名が空です"
    exit 1
  fi

  if [[ ! "${name}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    log_error "保存名に使用できない文字が含まれています: ${name}"
    exit 1
  fi

  local target="${PATTERNS_DIR}/${name}.jsonc"
  if [[ -f "${target}" ]]; then
    log_error "同名のパターンが既に存在します: ${target}"
    exit 1
  fi

  local description
  read -r -p "説明を入力してください（空でも可）: " description
  if [[ -z "${description}" ]]; then
    description="${name}"
  fi

  extract_current_pattern "${description}" > "${target}"
  log_success "現在の設定を保存しました: ${target}"
}

extract_current_pattern() {
  local description="$1"

  if [[ ! -f "${CONFIG_PATH}" ]]; then
    log_error "設定ファイルが見つかりません: ${CONFIG_PATH}"
    exit 1
  fi

  local desc_json
  if command -v jq >/dev/null 2>&1; then
    desc_json="$(jq -Rn --arg d "${description}" '$d')"
  else
    local s="${description//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    desc_json="\"${s}\""
  fi

  local block
  block="$(awk -v start="${PATTERN_START}" -v end="${PATTERN_END}" '
    $0 ~ start {in_block=1; next}
    $0 ~ end {exit}
    in_block {print}
  ' "${CONFIG_PATH}")"

  if [[ -z "${block}" ]]; then
    printf '{\n  "description": %s,\n  "agents": {},\n  "categories": {}\n}\n' "${desc_json}"
  else
    printf '{\n  "description": %s,\n%s\n}\n' "${desc_json}" "${block}"
  fi
}

apply_pattern() {
  local name="$1"
  local source="${PATTERNS_DIR}/${name}.jsonc"

  if [[ ! -f "${source}" ]]; then
    log_error "選択したパターンが見つかりません: ${source}"
    exit 1
  fi

  if ! grep -q '"agents"' "${source}"; then
    log_error "パターンに agents が見つかりません: ${source}"
    exit 1
  fi

  if ! grep -q '"categories"' "${source}"; then
    log_error "パターンに categories が見つかりません: ${source}"
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"

  awk -v start="${PATTERN_START}" -v end="${PATTERN_END}" -v pattern="${source}" '
    $0 ~ start {
      print $0
      while ((getline line < pattern) > 0) { lines[++count]=line }
      close(pattern)
      for (i=1; i<=count; i++) {
        if (lines[i] ~ /"agents"\s*:/) { start_i=i; break }
      }
      for (i=count; i>=1; i--) {
        if (lines[i] ~ /^\s*}\s*$/) { end_i=i; break }
      }
      if (start_i == 0 || end_i == 0 || end_i <= start_i) {
        exit 2
      }
      for (i=start_i; i<end_i; i++) print lines[i]
      count=0
      start_i=0
      end_i=0
      in_block=1
      next
    }
    in_block {
      if ($0 ~ end) {
        print $0
        in_block=0
      }
      next
    }
    { print }
  ' "${BASE_CONFIG_PATH}" > "${tmp}"

  mv "${tmp}" "${CONFIG_PATH}"
  log_success "パターンを適用しました: ${name}"
}

main() {
  ensure_base_exists
  ensure_pattern_marker_exists
  ensure_generated_config
  init_patterns

  local patterns
  mapfile -t patterns < <(list_patterns)
  local labels
  mapfile -t labels < <(pattern_labels < <(printf '%s\n' "${patterns[@]}"))

  if [[ ${#patterns[@]} -eq 0 ]]; then
    log_error "パターンが見つかりません: ${PATTERNS_DIR}"
    exit 1
  fi

  local menu_items=("${labels[@]}" "現在の設定を保存" "終了")

  echo "============================================================"
  echo "🔁 oh-my-opencode パターン切替"
  echo "============================================================"
  echo ""

  PS3="番号を選択してください: "
  select choice in "${menu_items[@]}"; do
    if [[ -z "${choice}" ]]; then
      log_warn "無効な選択です。番号を選択してください。"
      continue
    fi

    case "${choice}" in
      "現在の設定を保存")
        save_current_pattern
        ;;
      "終了")
        log_info "終了します"
        exit 0
        ;;
      *)
        if [[ ${REPLY} -ge 1 && ${REPLY} -le ${#labels[@]} ]]; then
          local name
          name="${patterns[$((REPLY - 1))]%%|*}"
          apply_pattern "${name}"
        else
          log_warn "無効な選択です。番号を選択してください。"
          continue
        fi
        ;;
    esac
    break
  done
}

main "$@"
