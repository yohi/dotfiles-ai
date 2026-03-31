#!/usr/bin/env bash
# _scripts/check-skillport-version.sh
set -euo pipefail

# PyPIから最新バージョンを取得 (python3を使用して堅牢に)
LATEST_VERSION=$(curl -s https://pypi.org/pypi/skillport-mcp/json | python3 -c "import sys, json; print(json.load(sys.stdin)['info']['version'])")

# コンテナ内のバージョンを取得 (entrypointをpython3にして実行)
INSTALLED_VERSION=$(docker run --rm --entrypoint python3 ghcr.io/yohi/skillport:latest -m pip show skillport-mcp | grep Version | awk '{print $2}')

echo "Skillport Version Check:"
echo "------------------------"
echo "Installed (GHCR): $INSTALLED_VERSION"
echo "Latest (PyPI):    $LATEST_VERSION"

if [ "$INSTALLED_VERSION" != "$LATEST_VERSION" ]; then
    echo "Update available! Please rebuild the container."
    exit 1
fi
