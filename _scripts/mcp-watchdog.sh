#!/usr/bin/env bash
# _scripts/mcp-watchdog.sh

GATEWAY_URL="http://127.0.0.1:10888/sse"
CHECK_INTERVAL=300
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# トークンの取得
if [ -f "$REPO_ROOT/.env" ]; then
    TOKEN=$(grep "^MCP_GATEWAY_TOKEN=" "$REPO_ROOT/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

echo "🛡️ MCP Watchdog started (Target: $GATEWAY_URL)"

while true; do
    # 認証ヘッダーを付けて死活監視
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        -H "Authorization: Bearer $TOKEN" \
        "$GATEWAY_URL")

    if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "405" ]; then
        # 405 Method Not Allowed は SSE エンドポイントに対する GET 時に返ることがあるが疎通はしている
        echo "⚠️  Docker MCP Gateway is not responding (HTTP $HTTP_CODE). Attempting to restart..."
        systemctl --user restart docker-mcp-gateway.service
    fi

    sleep "$CHECK_INTERVAL"
done
