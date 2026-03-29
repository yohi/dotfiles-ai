#!/usr/bin/env bash
set -e

# uv を使用してバージョン情報を表示
echo "[skillport] Version: $(uv pip show skillport-mcp | grep Version | awk '{print $2}')" >&2

# メインプロセスの実行
exec skillport-mcp "$@"
