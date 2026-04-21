#!/usr/bin/env bash
set -e

# マウントされたディレクトリの所有権を skillport ユーザーに包括的に変更 (再帰的に適用)
if [ -d "/home/skillport/.skillport" ]; then
    chown -R skillport:skillport /home/skillport/.skillport
fi

# バージョン情報の出力 (stderr)
# gosu を使用して実行し、一時的な権限移行を行う
VERSION=$(gosu skillport skillport-mcp --version 2>/dev/null || echo "unknown")
echo "[skillport] Version: $VERSION" >&2

# skillport ユーザーとしてメインプロセスを実行
# gosu は exec を実行して自身を指定したコマンドに置き換えるため、
# skillport-mcp が PID 1 となり、シグナルを直接受け取ることが可能になる
exec gosu skillport skillport-mcp "$@"
