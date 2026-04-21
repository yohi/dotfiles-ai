#!/usr/bin/env bash
set -e

# マウントされたディレクトリの所有権を skillport ユーザーに包括的に変更 (必要な場合のみ)
# recursive chown は大規模なボリュームで非常に遅くなる可能性があるため、
# 所有権の不一致が検出された場合にのみ実行する
if [ -d "/home/skillport/.skillport" ]; then
    # ディレクトリ自体の所有者を確認、または配下に skillport 以外が所有するファイルがあるか確認
    # (ここでは高速化のため、ディレクトリ自体の所有者と代表的なサブディレクトリを確認する簡易チェックを行う)
    CURRENT_OWNER=$(stat -c %u:%g /home/skillport/.skillport)
    if [ "$CURRENT_OWNER" != "1000:1000" ] || [ -n "$(find /home/skillport/.skillport ! -user skillport -print -quit)" ]; then
        echo "[skillport] Ownership mismatch detected. Applying chown -R skillport:skillport /home/skillport/.skillport ..." >&2
        chown -R skillport:skillport /home/skillport/.skillport
    fi
fi

# バージョン情報の出力 (stderr)
# gosu を使用して実行し、一時的な権限移行を行う
VERSION=$(gosu skillport skillport-mcp --version 2>/dev/null || echo "unknown")
echo "[skillport] Version: $VERSION" >&2

# skillport ユーザーとしてメインプロセスを実行
# gosu は exec を実行して自身を指定したコマンドに置き換えるため、
# skillport-mcp が PID 1 となり、シグナルを直接受け取ることが可能になる
exec gosu skillport skillport-mcp "$@"
