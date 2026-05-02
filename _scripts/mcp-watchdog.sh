#!/usr/bin/env bash
# _scripts/mcp-watchdog.sh
set -euo pipefail

GATEWAY_URL="http://127.0.0.1:10888/health"
CHECK_INTERVAL=300
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# トークンの取得
TOKEN=""
if [ -f "$REPO_ROOT/.env" ]; then
    # render-mcp-configs.py と同様の正規表現ロジックで抽出
    TOKEN=$(sed -n 's/^[[:space:]]*MCP_GATEWAY_TOKEN=\(.*\)$/\1/p' "$REPO_ROOT/.env" | sed -e 's/^["'\'']//' -e 's/["'\'']$//')
fi

if [ -z "$TOKEN" ]; then
    echo "⚠️  Warning: MCP_GATEWAY_TOKEN is not set or empty. Proceeding without Authorization header." >&2
fi

echo "🛡️ MCP Watchdog started (Target: $GATEWAY_URL)"

while true; do
    # トークンがある場合のみヘッダーを追加
    CURL_ARGS=("-s" "-o" "/dev/null" "-w" "%{http_code}" "--max-time" "10")
    if [ -n "$TOKEN" ]; then
        CURL_ARGS+=("-H" "Authorization: Bearer $TOKEN")
    fi

    # set -e による中断を防ぐため、失敗を許容し終了コードを確認
    HTTP_CODE=$(curl "${CURL_ARGS[@]}" "$GATEWAY_URL" || echo "000")

    if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "405" ]; then
        echo "⚠️  Docker MCP Gateway is not responding (HTTP $HTTP_CODE). Attempting to restart..."
        if ! systemctl --user restart docker-mcp-gateway.service; then
            EXIT_CODE=$?
            echo "❌ Error: Failed to restart docker-mcp-gateway.service (Exit code: $EXIT_CODE)" >&2
            echo "💡 Tip: Check if systemd user mode is available and service is correctly installed." >&2
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
