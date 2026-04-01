#!/usr/bin/env bash
# _scripts/find-local-cursor.sh
set -euo pipefail

# Cursor AppImageのサイズ制限 (bytes)
CURSOR_MIN_SIZE_BYTES="${CURSOR_MIN_SIZE_BYTES:-100000000}"
CURSOR_MAX_SIZE_BYTES="${CURSOR_MAX_SIZE_BYTES:-500000000}"
CURSOR_SHA256="${CURSOR_SHA256:-}"
CURSOR_NO_VERIFY_HASH="${CURSOR_NO_VERIFY_HASH:-false}"
HOME_DIR="${HOME_DIR:-$HOME}"

# OS検出と互換コマンドの設定
OS_NAME=$(uname -s)
if [ "$OS_NAME" = "Darwin" ]; then
    STAT_SIZE_CMD="stat -f%z"
    SHA256_CMD="shasum -a 256"
else
    STAT_SIZE_CMD="stat -c%s"
    SHA256_CMD="sha256sum"
fi

verify_file() {
    local file="$1"
    local file_size
    file_size=$($STAT_SIZE_CMD "$file" 2>/dev/null || echo "0")
    
    # サイズ検証
    if [ "$file_size" -lt "$CURSOR_MIN_SIZE_BYTES" ] || [ "$file_size" -gt "$CURSOR_MAX_SIZE_BYTES" ]; then
        echo "❌ ファイルのサイズが不正です ($file_size bytes): $file" >&2
        return 1
    fi

    # ハッシュ検証
    if [ -n "$CURSOR_SHA256" ]; then
        local actual_hash
        actual_hash=$($SHA256_CMD "$file" | awk '{print $1}')
        if [ "$actual_hash" != "$CURSOR_SHA256" ]; then
            echo "❌ ハッシュ不一致エラー: $file" >&2
            echo "   期待値: $CURSOR_SHA256" >&2
            echo "   実際値: $actual_hash" >&2
            return 1
        fi
        echo "✅ ハッシュ検証に成功しました: $file" >&2
    elif [ "$CURSOR_NO_VERIFY_HASH" = "true" ]; then
        echo "⚠️  【セキュリティ警告】CURSOR_NO_VERIFY_HASH=true により、ハッシュ検証をスキップします: $file" >&2
    else
        echo "❌ エラー: CURSOR_SHA256 が設定されておらず、整合性検証をスキップできません: $file" >&2
        echo "   (CURSOR_NO_VERIFY_HASH=true を設定することでスキップ可能です)" >&2
        return 1
    fi

    return 0
}

# 検索対象ディレクトリ
SEARCH_DIRS=("$HOME_DIR/Downloads" "$HOME_DIR/Desktop" "/tmp")

for dir in "${SEARCH_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        # ファイルが見つかった場合のみループに入る
        for file in "$dir"/cursor*.AppImage; do
            if [ -f "$file" ]; then
                echo "🔍 $file が見つかりました。検証中..." >&2
                if verify_file "$file"; then
                    echo "$file" # 見つかったファイルのパスを標準出力に
                    exit 0
                fi
            fi
        done
    fi
done

echo "❌ 妥当な Cursor AppImage が見つかりませんでした。" >&2
exit 1
