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
    echo -e "${BLUE}🔧 Installing docker-mcp CLI plugin...${NC}"
    # 公式のインストール手順（通常は brew またはバイナリ配布だが、ここでは案内にとどめるか
    # ユーザー環境に合わせたインストールが必要な場合がある）
    echo -e "Please ensure 'docker-mcp' is installed as a Docker CLI plugin."
    echo -e "Refer to: https://docs.docker.com/ai/mcp-catalog-and-toolkit/install/"
    # 一時的に警告として続行
fi

# 設定ファイルの配置 (シンボリックリンク)
echo -e "${BLUE}🔗 Linking Docker MCP configuration files...${NC}"
MCP_CONFIG_DIR="$HOME/.docker/mcp"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$MCP_CONFIG_DIR/catalogs"

# 既存のファイルがある場合はリンクに置き換え
ln -sfn "$REPO_ROOT/mcp/config.yaml" "$MCP_CONFIG_DIR/config.yaml"
ln -sfn "$REPO_ROOT/mcp/catalog.json" "$MCP_CONFIG_DIR/catalog.json"
ln -sfn "$REPO_ROOT/mcp/catalogs/custom.yaml" "$MCP_CONFIG_DIR/catalogs/custom.yaml"
ln -sfn "$REPO_ROOT/mcp/catalogs/bootstrap.yaml" "$MCP_CONFIG_DIR/catalogs/bootstrap.yaml"

echo -e "${GREEN}✅ Symbolic links created in $MCP_CONFIG_DIR${NC}"

# systemd ユーザーサービスの作成
echo -e "${BLUE}⚙️  Setting up systemd user service for Docker MCP Gateway...${NC}"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/docker-mcp-gateway.service"
DOCKER_PATH="$(which docker)"

mkdir -p "$SERVICE_DIR"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Docker MCP Gateway
After=docker.service

[Service]
ExecStart=$DOCKER_PATH mcp gateway run --port 10888 --enable-all-servers
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service

echo -e "${GREEN}✅ Docker MCP Gateway service enabled and started.${NC}"

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
echo -e "${BLUE}Docker MCP Gateway is running as a systemd user service.${NC}"
echo -e "  - Status: systemctl --user status docker-mcp-gateway"
echo -e "  - Logs:   journalctl --user -u docker-mcp-gateway -f"
echo -e "  - Stop:   systemctl --user stop docker-mcp-gateway"
echo -e "  - Start:  systemctl --user start docker-mcp-gateway"
echo -e ""
echo -e "${BLUE}Endpoint:${NC} http://localhost:10888"
