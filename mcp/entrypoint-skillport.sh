#!/usr/bin/env bash
set -e

# マウントされたディレクトリの所有権を skillport ユーザーに包括的に変更
if [ -d "/home/skillport/.skillport" ]; then
    chown -R skillport:skillport /home/skillport/.skillport
fi

# バージョン情報の出力 (stderr)
VERSION=$(su skillport -c "skillport-mcp --version 2>/dev/null" || echo "unknown")
echo "[skillport] Version: $VERSION" >&2

# skillport ユーザーとしてメインプロセスを実行
# 標準出力は MCP 通信用に保護される
exec su skillport -c "skillport-mcp $*"
