#!/usr/bin/env bash
# scripts/check-skillport-version.sh
set -euo pipefail

# PyPIから最新バージョンを取得
LATEST_VERSION=$(curl -s https://pypi.org/pypi/skillport-mcp/json | grep -oP '"version":"\K[^"]+')

# コンテナ内のバージョンを取得
INSTALLED_VERSION=$(docker run --rm --entrypoint pip ghcr.io/yohi/skillport:latest show skillport-mcp | grep Version | awk '{print $2}')

echo "Skillport Version Check:"
echo "------------------------"
echo "Installed (GHCR): $INSTALLED_VERSION"
echo "Latest (PyPI):    $LATEST_VERSION"

if [ "$LATEST_VERSION" == "$INSTALLED_VERSION" ]; then
    echo "✅ Skillport is up to date."
else
    echo "⚠️  New version available! Please run 'workflow_dispatch' on GitHub Actions to rebuild the image."
fi
