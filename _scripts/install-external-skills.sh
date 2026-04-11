#!/usr/bin/env bash
#
# _scripts/install-external-skills.sh
# description: EXTERNAL_SKILLS.md (Lock-file) を解析し、
#              全 namespace の外部スキルを skillport add でインストールする。
#
# Usage:
#   ./install-external-skills.sh              # 通常インストール
#   ./install-external-skills.sh --dry-run    # 解析のみ（インストールしない）
#   ./install-external-skills.sh --force      # 既存スキル上書きインストール
#

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

readonly MANIFEST_FILE="agent-skills/EXTERNAL_SKILLS.md"
readonly SKILLS_DIR="agent-skills"

DRY_RUN=false
FORCE=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --force)   FORCE=true ;;
        *)         echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if [ ! -f "$MANIFEST_FILE" ]; then
    echo "⚠️  $MANIFEST_FILE が見つかりません。外部スキルのインストールをスキップします。"
    exit 0
fi

# EXTERNAL_SKILLS.md のテーブル行を解析
# Format: | namespace | source_repo | commit_hash | pinned_at | note |
parse_manifest() {
    awk -F'|' '
        NR > 1 && NF >= 5 {
            ns = $2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", ns)
            url = $3; gsub(/^[[:space:]]+|[[:space:]]+$/, "", url)
            hash = $4; gsub(/^[[:space:]]+|[[:space:]]+$/, "", hash)

            # ヘッダー行・セパレータ行をスキップ
            if (ns == "" || ns == "Skill Namespace" || ns ~ /^:?-/) next
            if (url == "" || hash == "") next

            print ns "|" url "|" hash
        }
    ' "$MANIFEST_FILE"
}

install_namespace() {
    local ns="$1" url="$2" hash="$3"
    local target_dir="$SKILLS_DIR/$ns"

    echo "📦 [$ns] $url@$hash"

    if $DRY_RUN; then
        echo "  [DRY-RUN] skillport add (skipped)"
        return 0
    fi

    # 既にインストール済みかチェック
    if [ -d "$target_dir" ] && [ ! "$FORCE" = true ]; then
        # ディレクトリ内に SKILL.md が1つ以上存在すればインストール済みとみなす
        if find "$target_dir" -name "SKILL.md" -maxdepth 3 | grep -q .; then
            echo "  [SKIP] 既にインストール済み ($target_dir)"
            return 0
        fi
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' RETURN

    echo "  📥 リポジトリをクローン中..."
    if ! git clone "$url" "$tmp_dir" --quiet 2>/dev/null; then
        echo "  ❌ クローンに失敗しました: $url" >&2
        return 1
    fi

    echo "  🔀 バージョン $hash にチェックアウト中..."
    if ! (cd "$tmp_dir" && git checkout "$hash" --quiet 2>/dev/null); then
        echo "  ❌ チェックアウトに失敗しました: $hash" >&2
        return 1
    fi

    # skillport add の入力パスを決定
    # superpowers: skills/ サブディレクトリ
    # anthropics: ルートディレクトリ直下に各スキル
    local src_dir="$tmp_dir"
    if [ -d "$tmp_dir/skills" ]; then
        src_dir="$tmp_dir/skills/"
    fi

    echo "  📝 skillport add を実行中..."
    local skillport_cmd=""
    if command -v skillport >/dev/null 2>&1; then
        skillport_cmd="skillport"
    elif command -v uvx >/dev/null 2>&1; then
        skillport_cmd="uvx skillport"
    else
        echo "  ❌ skillport が見つかりません。" >&2
        echo "     インストール: pip install skillport または uvx skillport" >&2
        return 1
    fi

    if $skillport_cmd add "$src_dir" --namespace "$ns" --yes --force; then
        echo "  ✅ [$ns] インストール完了"
    else
        echo "  ❌ [$ns] インストールに失敗しました" >&2
        return 1
    fi
}

echo "🔄 外部スキルのインストールを開始..."
if $DRY_RUN; then
    echo "  (ドライランモード: 実際のインストールは行いません)"
fi
echo ""

ERRORS=0
while IFS='|' read -r ns url hash; do
    if ! install_namespace "$ns" "$url" "$hash"; then
        ((ERRORS++))
    fi
    echo ""
done < <(parse_manifest)

if [ "$ERRORS" -gt 0 ]; then
    echo "⚠️  $ERRORS 件のエラーが発生しました。"
    exit 1
fi

echo "✅ 全外部スキルのインストールが完了しました。"
