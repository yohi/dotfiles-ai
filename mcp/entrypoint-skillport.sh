#!/usr/bin/env bash
set -e

# uv を使用してバージョン情報を取得 (失敗しても中断しないように)
VERSION=$(uv pip show skillport-mcp 2>/dev/null | grep Version | awk '{print $2}' || true)
if [ -z "$VERSION" ]; then
    VERSION="unknown"
fi

echo "[skillport] Version: $VERSION" >&2

# メインプロセスの実行
exec skillport-mcp "$@"
