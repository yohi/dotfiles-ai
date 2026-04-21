#!/usr/bin/env bash
set -e

# マウントされたディレクトリの所有権を skillport ユーザーに変更
# (root で実行されていることを前提とする)
if [ -d "/home/skillport/.skillport/db" ]; then
    chown -R skillport:skillport /home/skillport/.skillport/db
fi

# uv を使用してバージョン情報を取得
VERSION=$(su skillport -c "uv pip show skillport-mcp 2>/dev/null" | grep Version | awk '{print $2}' || true)
if [ -z "$VERSION" ]; then
    VERSION="unknown"
fi

echo "[skillport] Version: $VERSION" >&2

# skillport ユーザーとしてメインプロセスを実行
exec su skillport -c "skillport-mcp $*"
