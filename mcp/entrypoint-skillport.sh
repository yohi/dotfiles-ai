#!/usr/bin/env bash
set -e

# マウントされたディレクトリの所有権を skillport ユーザーに包括的に変更 (再帰的に適用)
if [ -d "/home/skillport/.skillport" ]; then
    chown -R skillport:skillport /home/skillport/.skillport
fi

# バージョン情報の出力 (stderr)
VERSION=$(su skillport -s /bin/bash -c 'exec skillport-mcp --version 2>/dev/null' -- || echo "unknown")
echo "[skillport] Version: $VERSION" >&2

# skillport ユーザーとしてメインプロセスを実行
# exec を重ねることでシグナル転送を確保し、"$@" で引数のクォートを維持する
exec su skillport -s /bin/bash -c 'exec skillport-mcp "$@"' -- "$@"
