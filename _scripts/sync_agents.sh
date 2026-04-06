#!/usr/bin/env bash
#
# _scripts/sync_agents.sh
# description: skillport doc を実行して AGENTS.md を生成し、
#              その内容を global-rules/AGENTS.global.md に上書き同期する。
#

set -euo pipefail

# プロジェクトルートディレクトリに移動（どこから実行されても動作するように）
cd "$(dirname "$0")/.." || exit 1

readonly SOURCE_MD="AGENTS.md"
readonly TARGET_MD="global-rules/AGENTS.global.md"
readonly START_MARKER="<!-- SKILLPORT_START -->"
readonly END_MARKER="<!-- SKILLPORT_END -->"

# 1. skillport docの実行
if command -v skillport >/dev/null 2>&1; then
    echo "Running skillport doc..."
    printf 'y\n' | skillport doc --mode mcp --all || {
        echo "Error: skillport doc failed." >&2
        exit 1
    }
elif command -v uvx >/dev/null 2>&1; then
    echo "Running uvx skillport doc..."
    printf 'y\n' | uvx skillport doc --mode mcp --all || {
        echo "Error: uvx skillport doc failed." >&2
        exit 1
    }
else
    echo "Error: 'skillport' command not found. Please install it." >&2
    exit 1
fi

# 2. ファイルの存在・権限チェック
if [[ ! -f "$SOURCE_MD" ]]; then
    echo "Error: Generated file '$SOURCE_MD' not found." >&2
    exit 1
fi

if [[ ! -w "$TARGET_MD" ]] || [[ ! -r "$TARGET_MD" ]]; then
    echo "Error: Target file '$TARGET_MD' is not accessible or writable." >&2
    exit 1
fi

# 3. 置換ロジック (一時ファイルを利用して安全に更新)
TMP_FILE=$(mktemp)
TMP_SOURCE=$(mktemp)
trap 'rm -f "$TMP_FILE" "$TMP_SOURCE"' EXIT

# AGENTS.md の内容をそのまま一時ファイルにコピー（将来的にフィルタリングが必要な場合はここで処理）
cat "$SOURCE_MD" > "$TMP_SOURCE"

# 4. 絶対パスを相対パスに変換する処理
# 現在のプロジェクトルートの絶対パスを取得し、それを削除して相対パス化する
REPO_ROOT=$(pwd)
perl -pi -e "s|(<location>)\Q${REPO_ROOT}/\E|\$1|g" "$SOURCE_MD"
perl -pi -e "s|(<location>)\Q${REPO_ROOT}/\E|\$1|g" "$TMP_SOURCE"

# 5. TARGET_MD (global-rules/AGENTS.global.md) への同期

# START_MARKER と END_MARKER が存在するかチェック
if grep -qF "$START_MARKER" "$TARGET_MD" && grep -qF "$END_MARKER" "$TARGET_MD"; then
    # 既存のマーカー間をごっそり置換 (絶対パス版の TMP_SOURCE を使用)
    awk -v start_m="$START_MARKER" -v end_m="$END_MARKER" \
        -v src="$TMP_SOURCE" '
    BEGIN { skip=0 }
    $0 == start_m {
        print start_m
        in_block=0
        while ((getline line < src) > 0) {
            if (line == start_m) { in_block=1; continue }
            if (line == end_m) { in_block=0; break }
            if (in_block) print line
        }
        skip=1
        next
    }
    $0 == end_m {
        print end_m
        skip=0
        next
    }
    skip == 0 { print }
    ' "$TARGET_MD" > "$TMP_FILE"
else
    # マーカーが存在しない場合は、ファイルの末尾に追記
    cat "$TARGET_MD" > "$TMP_FILE"
    echo "" >> "$TMP_FILE"
    echo "$START_MARKER" >> "$TMP_FILE"
    cat "$TMP_SOURCE" >> "$TMP_FILE"
    echo "$END_MARKER" >> "$TMP_FILE"
fi

# 一時ファイルを上書きして確定
mv "$TMP_FILE" "$TARGET_MD"

echo "✅ Successfully synchronized $SOURCE_MD to $TARGET_MD."
