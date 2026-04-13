#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Running MCP Make target verification tests..."

# 検証対象のターゲットリスト
MCP_TARGETS=("status-mcp" "start-mcp" "stop-mcp" "restart-mcp")

for target in "${MCP_TARGETS[@]}"; do
    # -s: -C 使用時に出る "Entering/Leaving directory" メッセージを抑制
    # -n: コマンドを実行せずにレシピを表示 (dry-run)
    RECIPE="$(make -s -n -C "$REPO_ROOT" "$target")"

    # 全ターゲットで systemctl に --no-pager が含まれていることを確認
    if ! grep -Eq -- "systemctl.*--no-pager" <<<"$RECIPE"; then
        echo "FAIL: $target must invoke systemctl with --no-pager to avoid interactive paging." >&2
        exit 1
    fi
    echo "PASS: $target runs without pager."
done

echo "🎉 All MCP Make target tests passed successfully!"
