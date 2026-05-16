#!/usr/bin/env bash
# _scripts/setup-docker-mcp.sh
set -euo pipefail

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# ヘルパー関数: .env から安全に値を取得する (キーがない場合や空の場合もエラーにせず空文字を返す)
safe_dotenv_get() {
    local key="$1"
    local file="$2"
    if [ ! -f "$file" ]; then
        return 0
    fi
    # grep -m1 で最初の一致のみ取得し、sed でクォートを除去。
    # パイプの最後で || true を置くことで grep が見つからなくてもエラーにしない。
    grep -E "^[[:space:]]*${key}=" "$file" | head -n 1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | xargs || true
}

echo -e "${BLUE}🐳 Starting Docker MCP setup...${NC}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# オプション解析
SKIP_DOCKER_CHECK=false
for arg in "$@"; do
    if [ "$arg" == "--skip-docker-check" ]; then
        SKIP_DOCKER_CHECK=true
    fi
done

# Dockerの確認
if [ "$SKIP_DOCKER_CHECK" = "false" ]; then
    if ! command -v docker > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
        exit 1
    fi

    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker daemon is not running. Please start Docker first.${NC}"
        
        # Ubuntu 24.04+ の Rootless 制限チェック
        if [[ -f /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]]; then
            RESTRICT_VAL=$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns)
            if [[ "$RESTRICT_VAL" == "1" ]]; then
                echo -e "${YELLOW}⚠️  Ubuntu 24.04+ restriction detected.${NC}"
                echo -e "It seems unprivileged user namespaces are restricted by AppArmor."
                echo -e "Please run the following command to fix it:"
                echo -e "${BLUE}  make fix-ubuntu-rootless${NC}"
            fi
        fi
        exit 1
    fi
    echo -e "${GREEN}✅ Docker is installed and running.${NC}"

    # node_modules の確認
    if [ ! -d "$REPO_ROOT/node_modules" ]; then
        echo -e "${YELLOW}⚠️  node_modules not found. Installing dependencies...${NC}"
        npm install --silent --prefix "$REPO_ROOT"
    fi
    echo -e "${GREEN}✅ Node.js dependencies checked/ready.${NC}"

    # docker-mcp プラグインの確認
    if ! docker mcp version > /dev/null 2>&1; then
        echo -e "${RED}❌ docker-mcp CLI plugin not found.${NC}"
        echo -e "Please install docker-mcp as a Docker CLI plugin."
        echo -e "Refer to: https://docs.docker.com/ai/mcp-catalog-and-toolkit/install/"
        exit 1
    fi
    echo -e "${GREEN}✅ docker-mcp CLI plugin found.${NC}"
else
    echo -e "${YELLOW}⚠️  Skipping Docker checks as requested.${NC}"
fi

# 共有シークレットファイルの設定
echo -e "${BLUE}🔑 Preparing shared .env for Docker MCP secrets...${NC}"
DOTENV_FILE="$REPO_ROOT/.env"

# 書き込み前に権限を制限する (作成時に 600 になるように)
if [ ! -f "$DOTENV_FILE" ]; then
    (umask 077 && touch "$DOTENV_FILE")
else
    chmod 600 "$DOTENV_FILE"
fi

# トークンの存在確認と取得
GATEWAY_TOKEN=$(safe_dotenv_get "MCP_GATEWAY_TOKEN" "$DOTENV_FILE")

# プレースホルダ値をチェックし、該当する場合は空として扱う
if [[ "$GATEWAY_TOKEN" == *"your-mcp-"* ]]; then
    echo -e "${YELLOW}⚠️  Placeholder token detected for MCP_GATEWAY_TOKEN.${NC}"
    GATEWAY_TOKEN=""
fi

if [ -z "$GATEWAY_TOKEN" ]; then
    # 既存の古いトークン名があるか確認
    EXISTING_TOKEN=$(safe_dotenv_get "MCP_AUTH_TOKEN" "$DOTENV_FILE")
    if [[ "$EXISTING_TOKEN" == *"your-mcp-"* ]]; then
        EXISTING_TOKEN=""
    fi
    
    if [ -n "$EXISTING_TOKEN" ]; then
        echo "MCP_GATEWAY_TOKEN=$EXISTING_TOKEN" >> "$DOTENV_FILE"
        echo -e "${GREEN}✅ Migrated existing MCP_AUTH_TOKEN to MCP_GATEWAY_TOKEN in .env${NC}"
        GATEWAY_TOKEN="$EXISTING_TOKEN"
    else
        # 新しいトークンを生成 (32 bytes)
        NEW_TOKEN=$(openssl rand -hex 32)
        # 重複を防ぐため、既存のプレースホルダやエントリを削除
        sed -i.tmp '/^MCP_GATEWAY_TOKEN=/d; /^MCP_GATEWAY_AUTH_TOKEN=/d; /^MCP_AUTH_TOKEN=/d' "$DOTENV_FILE"
        rm -f "$DOTENV_FILE.tmp"
        {
            echo "MCP_GATEWAY_TOKEN=$NEW_TOKEN"
            echo "MCP_GATEWAY_AUTH_TOKEN=$NEW_TOKEN"
            echo "MCP_AUTH_TOKEN=$NEW_TOKEN"
        } >> "$DOTENV_FILE"
        echo -e "${GREEN}✅ Generated new random tokens and added to .env${NC}"
        GATEWAY_TOKEN="$NEW_TOKEN"
    fi
fi

# 個別の変数が欠けているか、不整合がある場合の補完 (最新の GATEWAY_TOKEN を基準にする)
GATEWAY_AUTH_TOKEN=$(safe_dotenv_get "MCP_GATEWAY_AUTH_TOKEN" "$DOTENV_FILE")
if [ -z "$GATEWAY_AUTH_TOKEN" ] || [[ "$GATEWAY_AUTH_TOKEN" == *"your-mcp-"* ]] || [ "$GATEWAY_AUTH_TOKEN" != "$GATEWAY_TOKEN" ]; then
    # 重複を避けるため、既存の定義を削除してから追加
    sed -i.tmp '/^MCP_GATEWAY_AUTH_TOKEN=/d' "$DOTENV_FILE"
    rm -f "$DOTENV_FILE.tmp"
    echo "MCP_GATEWAY_AUTH_TOKEN=$GATEWAY_TOKEN" >> "$DOTENV_FILE"
    echo -e "${GREEN}✅ Synchronized MCP_GATEWAY_AUTH_TOKEN with MCP_GATEWAY_TOKEN${NC}"
fi

AUTH_TOKEN=$(safe_dotenv_get "MCP_AUTH_TOKEN" "$DOTENV_FILE")
if [ -z "$AUTH_TOKEN" ] || [[ "$AUTH_TOKEN" == *"your-mcp-"* ]] || [ "$AUTH_TOKEN" != "$GATEWAY_TOKEN" ]; then
    sed -i.tmp '/^MCP_AUTH_TOKEN=/d' "$DOTENV_FILE"
    rm -f "$DOTENV_FILE.tmp"
    echo "MCP_AUTH_TOKEN=$GATEWAY_TOKEN" >> "$DOTENV_FILE"
    echo -e "${GREEN}✅ Synchronized MCP_AUTH_TOKEN (backward compatibility) with MCP_GATEWAY_TOKEN${NC}"
fi

echo -e "${GREEN}✅ Shared .env file is ready.${NC}"

# 設定ファイルの配置は APM (Standard Dependencies) に集約
echo -e "${BLUE}🔗 Synchronizing Docker MCP configuration files via APM...${NC}"
apm install --force
make sync-mcp-gateway
echo -e "${GREEN}✅ Configuration files synchronized.${NC}"

# systemd ユーザーサービスの作成
if [ "$SKIP_DOCKER_CHECK" = "true" ]; then
    echo -e "${YELLOW}⚠️  Skipping systemd service setup as --skip-docker-check is enabled.${NC}"
    exit 0
fi

# カタログの初期化（未初期化の場合のみ、docker-mcp.yaml を取得するため）
MCP_CONFIG_DIR="$HOME/.docker/mcp"
CATALOG_FILE="$MCP_CONFIG_DIR/catalogs/docker-mcp.yaml"
if [[ ! -f "$CATALOG_FILE" ]]; then
    echo -e "${BLUE}📦 Initializing official MCP Catalog...${NC}"
    # Try update, fallback to init + update
    if ! docker mcp catalog update; then
        echo -e "${YELLOW}⚠️  Update failed, trying init then update...${NC}"
        docker mcp catalog init || true
        docker mcp catalog update || true
    fi
    
    # Verify final existence
    if [[ ! -f "$CATALOG_FILE" ]]; then
        echo -e "${RED}❌ Failed to initialize official MCP Catalog (File not found: $CATALOG_FILE).${NC}"
        echo -e "Please check your network connection or Docker AI configuration."
        exit 1
    fi
    echo -e "${GREEN}✅ Official MCP Catalog initialized.${NC}"
fi

echo -e "${BLUE}⚙️  Setting up systemd service...${NC}"
# Service file is deployed by the sync-mcp-gateway target (called above).
# Only reload and enable/restart here.
systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service
systemctl --user enable mcp-watchdog.service
systemctl --user restart mcp-watchdog.service
echo -e "${GREEN}✅ systemd services (gateway & watchdog) enabled and started.${NC}"

echo -e "${GREEN}✅ Docker MCP setup completed successfully.${NC}"
echo -e "${BLUE}Docker MCP Gateway is now running as an SSE server at http://localhost:10888/sse${NC}"
