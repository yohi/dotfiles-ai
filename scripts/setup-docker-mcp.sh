#!/usr/bin/env bash
# scripts/setup-docker-mcp.sh
set -euo pipefail

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
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
echo -e "${BLUE}⚙️  Setting up systemd user service for Docker MCP Gateway...${NC}"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/docker-mcp-gateway.service"
DOCKER_PATH="$(which docker)"

# ENABLE_SERVERS が指定されていない場合は、--servers フラグを付けず、config.yaml の全設定を使用する
ENABLE_SERVERS="${ENABLE_SERVERS:-}"
SERVERS_ARG=""
if [[ -n "$ENABLE_SERVERS" ]]; then
    SERVERS_ARG="--servers $ENABLE_SERVERS"
fi

# secrets.env の存在を確認（存在しない場合は空のファイルを作成して警告）
if [[ ! -f "$MCP_CONFIG_DIR/secrets.env" ]]; then
    echo -e "${YELLOW}⚠️  Warning: $MCP_CONFIG_DIR/secrets.env not found. Creating an empty one.${NC}"
    touch "$MCP_CONFIG_DIR/secrets.env"
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

# systemd ユーザーセッションが利用可能か確認
if systemctl --user status > /dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable docker-mcp-gateway.service
    systemctl --user restart docker-mcp-gateway.service
    echo -e "${GREEN}✅ Docker MCP Gateway service enabled and started.${NC}"
else
    echo -e "${RED}⚠️  Warning: User systemd session is unavailable. Skipping service activation.${NC}"
    echo -e "You can start the gateway manually with:"
    echo -e "  $GATEWAY_CMD"
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
    echo -e "${BLUE}Docker MCP Gateway is running as a systemd user service.${NC}"
    echo -e "  - Status: systemctl --user status docker-mcp-gateway"
    echo -e "  - Logs:   journalctl --user -u docker-mcp-gateway -f"
    echo -e "  - Stop:   systemctl --user stop docker-mcp-gateway"
    echo -e "  - Start:  systemctl --user start docker-mcp-gateway"
else
    echo -e "${BLUE}Manual Execution:${NC}"
    echo -e "  $GATEWAY_CMD"
fi
echo -e ""
echo -e "${BLUE}Endpoint:${NC} http://localhost:10888"
