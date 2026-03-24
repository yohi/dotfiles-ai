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
else
    echo -e "${YELLOW}⚠️  Skipping Docker checks as requested.${NC}"
fi

# 設定ファイルの配置 (シンボリックリンク)
echo -e "${BLUE}🔗 Linking Docker MCP configuration files...${NC}"
MCP_CONFIG_DIR="$HOME/.docker/mcp"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$MCP_CONFIG_DIR/catalogs"

# 1. 既存のファイルがある場合はコピーに置き換え (ソースの存在を確認してから)
FILES_TO_COPY=(
    "config.yaml:$MCP_CONFIG_DIR/config.yaml"
    "catalog.json:$MCP_CONFIG_DIR/catalog.json"
    "catalogs/bootstrap.yaml:$MCP_CONFIG_DIR/catalogs/bootstrap.yaml"
    "../antigravity/mcp_config.json.template:$REPO_ROOT/antigravity/mcp_config.json"
)

for pair in "${FILES_TO_COPY[@]}"; do
    SRC="${pair%%:*}"
    DST="${pair##*:}"

    # Resolve source file path
    SRC_FILE=""
    if [[ -f "$REPO_ROOT/mcp/$SRC" ]]; then
        SRC_FILE="$REPO_ROOT/mcp/$SRC"
    elif [[ "$SRC" == "../antigravity/"* ]] && [[ -f "$REPO_ROOT/antigravity/$(basename "$SRC")" ]]; then
        SRC_FILE="$REPO_ROOT/antigravity/$(basename "$SRC")"
    fi

    if [[ -z "$SRC_FILE" ]]; then
        echo -e "${RED}❌ Source file not found: $SRC (checked in $REPO_ROOT/mcp and $REPO_ROOT/antigravity)${NC}"
        exit 1
    fi

    # 一時ファイルへコピーしてからアトミックに移動
    TMP_DST="$DST.tmp.$$"

    # Escape $HOME for sed
    ESCAPED_HOME=$(echo "$HOME" | sed 's/[&/\|]/\\&/g')

    # テンプレートファイルの場合は置換を行う
    if [[ "$SRC" == *"template" ]]; then
        sed "s|__HOME__|$ESCAPED_HOME|g" "$SRC_FILE" > "$TMP_DST"
    else
        cp -f "$SRC_FILE" "$TMP_DST"
    fi

    if ! mv "$TMP_DST" "$DST"; then
        echo -e "${RED}❌ Failed to move $TMP_DST to $DST (Source: $SRC)${NC}"
        rm -f "$TMP_DST"
        exit 1
    fi
done

# 2. custom.yaml はシンボリックリンクにする
# これにより、リポジトリ内のファイルを編集して make mcp-render を実行するだけで、自動的に反映されるようになる
echo -e "${BLUE}🔗 Creating symbolic link for custom.yaml...${NC}"
CUSTOM_YAML_SRC="$REPO_ROOT/mcp/catalogs/custom.yaml"
CUSTOM_YAML_DST="$MCP_CONFIG_DIR/catalogs/custom.yaml"

if [[ -f "$CUSTOM_YAML_SRC" ]]; then
    ln -sf "$CUSTOM_YAML_SRC" "$CUSTOM_YAML_DST"
    echo -e "${GREEN}✅ Symbolic link created: $CUSTOM_YAML_DST -> $CUSTOM_YAML_SRC${NC}"
else
    echo -e "${RED}❌ Source file not found: $CUSTOM_YAML_SRC. Please run 'make mcp-render' first.${NC}"
    exit 1
fi

# catalog.json 内の $HOME を実際のホームディレクトリに置換 (docker mcp が環境変数を展開しない場合のため)
ESCAPED_HOME=$(echo "$HOME" | sed 's/[&/\|]/\\&/g')
sed -i.bak "s|\$HOME|$ESCAPED_HOME|g" "$MCP_CONFIG_DIR/catalog.json" && rm -f "$MCP_CONFIG_DIR/catalog.json.bak"

echo -e "${GREEN}✅ Configuration files copied and paths updated in $MCP_CONFIG_DIR${NC}"

# systemd ユーザーサービスの作成
if [ "$SKIP_DOCKER_CHECK" = "true" ]; then
    echo -e "${YELLOW}⚠️  Skipping systemd service setup as --skip-docker-check is enabled.${NC}"
    exit 0
fi

# カタログの初期化（未初期化の場合のみ、docker-mcp.yaml を取得するため）
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
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO_ROOT/mcp/docker-mcp-gateway.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service
echo -e "${GREEN}✅ systemd service enabled and started.${NC}"

echo -e "${GREEN}✅ Docker MCP setup completed successfully.${NC}"
echo -e "${BLUE}Docker MCP Gateway is now running as an SSE server at http://localhost:10888/sse${NC}"
