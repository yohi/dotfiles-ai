#!/usr/bin/env bash
# scripts/setup-docker-mcp.sh
set -euo pipefail

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Starting Docker MCP setup...${NC}"

# Dockerの確認
if ! command -v docker > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is installed and running.${NC}"

# Node.jsの確認
if ! command -v node > /dev/null 2>&1; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Node.js is installed.${NC}"

# docker-mcp プラグインの確認
if ! docker mcp version > /dev/null 2>&1; then
    echo -e "${RED}❌ docker-mcp CLI plugin not found.${NC}"
    echo -e "Please install docker-mcp as a Docker CLI plugin."
    echo -e "Refer to: https://docs.docker.com/ai/mcp-catalog-and-toolkit/install/"
    exit 1
fi
echo -e "${GREEN}✅ docker-mcp CLI plugin found.${NC}"

# 設定ファイルの配置 (シンボリックリンク)
echo -e "${BLUE}🔗 Linking Docker MCP configuration files...${NC}"
MCP_CONFIG_DIR="$HOME/.docker/mcp"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$MCP_CONFIG_DIR/catalogs"

# 1. 既存のファイルがある場合はコピーに置き換え (ソースの存在を確認してから)
FILES_TO_COPY=(
    "config.yaml:$MCP_CONFIG_DIR/config.yaml"
    "catalog.json:$MCP_CONFIG_DIR/catalog.json"
    "catalogs/custom.yaml:$MCP_CONFIG_DIR/catalogs/custom.yaml"
    "catalogs/bootstrap.yaml:$MCP_CONFIG_DIR/catalogs/bootstrap.yaml"
)

for pair in "${FILES_TO_COPY[@]}"; do
    SRC="${pair%%:*}"
    DST="${pair##*:}"
    if [[ ! -f "$REPO_ROOT/mcp/$SRC" ]]; then
        echo -e "${RED}❌ Source file not found: $REPO_ROOT/mcp/$SRC${NC}"
        exit 1
    fi
    # 一時ファイルへコピーしてからアトミックに移動
    TMP_DST="$DST.tmp.$$"
    if cp -f "$REPO_ROOT/mcp/$SRC" "$TMP_DST"; then
        mv "$TMP_DST" "$DST"
    else
        echo -e "${RED}❌ Failed to copy $SRC to $TMP_DST${NC}"
        rm -f "$TMP_DST"
        exit 1
    fi
done

# catalog.json 内の $HOME を実際のホームディレクトリに置換 (docker mcp が環境変数を展開しない場合のため)
sed -i.bak "s|\$HOME|$HOME|g" "$MCP_CONFIG_DIR/catalog.json" && rm -f "$MCP_CONFIG_DIR/catalog.json.bak"

echo -e "${GREEN}✅ Configuration files copied and paths updated in $MCP_CONFIG_DIR${NC}"

# systemd ユーザーサービスの作成
echo -e "${BLUE}⚙️  Setting up systemd user services...${NC}"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/docker-mcp-gateway.service"
PROXY_SERVICE_FILE="$SERVICE_DIR/docker-mcp-proxy.service"
DOCKER_PATH="$(which docker)"
NODE_PATH="$(which node)"

# ENABLE_SERVERS が指定されていない場合は、--servers フラグを付けず、config.yaml の全設定を使用する
ENABLE_SERVERS="${ENABLE_SERVERS:-}"

# Persistent secret store for MCP token in project root .env
DOTENV_FILE="$REPO_ROOT/.env"
if [[ -f "$DOTENV_FILE" ]] && grep -q "^MCP_GATEWAY_AUTH_TOKEN=" "$DOTENV_FILE"; then
    echo -e "${BLUE}🔑 Using existing MCP Gateway auth token from .env${NC}"
    MCP_GATEWAY_AUTH_TOKEN=$(grep "^MCP_GATEWAY_AUTH_TOKEN=" "$DOTENV_FILE" | head -n 1 | cut -d'=' -f2-)
else
    echo -e "${BLUE}🔑 Generating new MCP Gateway auth token...${NC}"
    if command -v openssl > /dev/null 2>&1; then
        MCP_GATEWAY_AUTH_TOKEN=$(openssl rand -hex 24)
    else
        MCP_GATEWAY_AUTH_TOKEN=$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 48 | head -n 1)
    fi
    if [[ -f "$DOTENV_FILE" ]]; then
        if grep -q "^MCP_GATEWAY_AUTH_TOKEN=" "$DOTENV_FILE"; then
            sed -i "s/^MCP_GATEWAY_AUTH_TOKEN=.*$/MCP_GATEWAY_AUTH_TOKEN=$MCP_GATEWAY_AUTH_TOKEN/" "$DOTENV_FILE"
        else
            echo "MCP_GATEWAY_AUTH_TOKEN=$MCP_GATEWAY_AUTH_TOKEN" >> "$DOTENV_FILE"
        fi
    else
        echo "MCP_GATEWAY_AUTH_TOKEN=$MCP_GATEWAY_AUTH_TOKEN" > "$DOTENV_FILE"
        chmod 600 "$DOTENV_FILE"
    fi
fi

SERVERS_ARG=""
if [[ -n "$ENABLE_SERVERS" ]]; then
    SERVERS_ARG="--servers $ENABLE_SERVERS"
fi

# secrets.env の存在を確認（存在しない場合は空のファイルを作成して警告）
if [[ ! -f "$MCP_CONFIG_DIR/secrets.env" ]]; then
    echo -e "${YELLOW}⚠️  Warning: $MCP_CONFIG_DIR/secrets.env not found. Creating an empty one.${NC}"
    touch "$MCP_CONFIG_DIR/secrets.env"
    chmod 600 "$MCP_CONFIG_DIR/secrets.env"
else
    chmod 600 "$MCP_CONFIG_DIR/secrets.env"
fi

# 共通の Gateway コマンド変数を定義
GATEWAY_CMD="$DOCKER_PATH mcp gateway run --transport sse --port 10888 --secrets \"$MCP_CONFIG_DIR/secrets.env\" --catalog \"$MCP_CONFIG_DIR/catalogs/bootstrap.yaml\" --catalog \"$MCP_CONFIG_DIR/catalogs/custom.yaml\" --watch=false $SERVERS_ARG"

mkdir -p "$SERVICE_DIR"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Docker MCP Gateway
After=docker.service

[Service]
LimitNOFILE=65536
Environment="ENABLE_SERVERS=$ENABLE_SERVERS"
Environment="MCP_GATEWAY_AUTH_TOKEN=$MCP_GATEWAY_AUTH_TOKEN"
# To enable all servers, you can change the ExecStart line to use --enable-all-servers
# ExecStart=$DOCKER_PATH mcp gateway run --transport sse --port 10888 --enable-all-servers
ExecStart=$GATEWAY_CMD
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

cat <<EOF > "$PROXY_SERVICE_FILE"
[Unit]
Description=Docker MCP Proxy
After=docker-mcp-gateway.service

[Service]
LimitNOFILE=65536
Environment="MCP_GATEWAY_AUTH_TOKEN=$MCP_GATEWAY_AUTH_TOKEN"
ExecStart=$NODE_PATH $REPO_ROOT/scripts/mcp-sse-proxy.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# systemd ユーザーセッションが利用可能か確認
if systemctl --user status > /dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable docker-mcp-gateway.service
    systemctl --user restart docker-mcp-gateway.service
    echo -e "${GREEN}✅ Docker MCP Gateway service enabled and started.${NC}"
    systemctl --user enable docker-mcp-proxy.service
    systemctl --user restart docker-mcp-proxy.service
    echo -e "${GREEN}✅ Docker MCP Proxy service enabled and started.${NC}"
else
    echo -e "${RED}⚠️  Warning: User systemd session is unavailable. Skipping service activation.${NC}"
    echo -e "You can start the services manually with:"
    echo -e "  Gateway: $GATEWAY_CMD"
    echo -e "  Proxy:   $NODE_PATH $REPO_ROOT/scripts/mcp-sse-proxy.js"
fi

# antigravity/mcp_config.json.template の確認と生成
TEMPLATE_FILE="$REPO_ROOT/antigravity/mcp_config.json.template"
TARGET_FILE="$REPO_ROOT/antigravity/mcp_config.json"
if [[ -f "$TEMPLATE_FILE" ]]; then
    echo -e "${BLUE}📝 Generating $TARGET_FILE from template...${NC}"
    # __MCP_GATEWAY_AUTH_TOKEN__ を実際のトークンで置換
    sed "s/__MCP_GATEWAY_AUTH_TOKEN__/$MCP_GATEWAY_AUTH_TOKEN/g" "$TEMPLATE_FILE" > "$TARGET_FILE"
    echo -e "${GREEN}✅ Generated $TARGET_FILE${NC}"
fi

# カタログの初期化（未初期化の場合のみ、docker-mcp.yaml を取得するため）
if [[ ! -f "$MCP_CONFIG_DIR/catalogs/docker-mcp.yaml" ]]; then
    echo -e "${BLUE}📦 Initializing official MCP Catalog...${NC}"
    docker mcp catalog update || docker mcp catalog init || true
fi

# 便利なサーバー（sqlite, filesystem, github等）が利用可能か確認
echo -e "${BLUE}🔍 Checking available MCP servers...${NC}"
# docker mcp catalog show | head -n 20

echo -e "${GREEN}✅ Docker MCP setup completed successfully.${NC}"
echo -e ""
if systemctl --user status > /dev/null 2>&1; then
    echo -e "${BLUE}Docker MCP services are running as systemd user services.${NC}"
    echo -e "Gateway:"
    echo -e "  - Status: systemctl --user status docker-mcp-gateway"
    echo -e "  - Logs:   journalctl --user -u docker-mcp-gateway -f"
    echo -e "Proxy:"
    echo -e "  - Status: systemctl --user status docker-mcp-proxy"
    echo -e "  - Logs:   journalctl --user -u docker-mcp-proxy -f"
    echo -e ""
    echo -e "Commands to manage both services:"
    echo -e "  - Stop:   systemctl --user stop docker-mcp-gateway docker-mcp-proxy"
    echo -e "  - Start:  systemctl --user start docker-mcp-gateway docker-mcp-proxy"
else
    echo -e "${BLUE}Manual Execution:${NC}"
    echo -e "  Gateway: $GATEWAY_CMD"
    echo -e "  Proxy:   $NODE_PATH $REPO_ROOT/scripts/mcp-sse-proxy.js"
fi
echo -e ""
echo -e "${BLUE}Endpoints:${NC}"
echo -e "  Gateway (SSE): http://localhost:10888"
echo -e "  Proxy   (SSE): http://localhost:10889 (Proxies to Gateway)"
