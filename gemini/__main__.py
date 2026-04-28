#!/usr/bin/env python3
"""
Gemini CLI
"""

import argparse
from . import cli_shared

def create_parser():
    """
    コマンドラインパーサーの作成
    """
    from . import __version__
    parser = argparse.ArgumentParser(
        description="Gemini CLI",
        epilog="Gemini CLI v" + __version__,
    )

    # サブコマンドの設定
    subparsers = parser.add_subparsers(dest="command", help="コマンド")

    # バージョン表示コマンド
    subparsers.add_parser("version", help="バージョン情報を表示")

    return parser

def main():
    """
    メイン関数
    """
    # 環境セットアップ
    # cli_shared.setup_environment() # 必要な場合に有効化

    # コマンドライン引数のパース
    parser = create_parser()
    args = parser.parse_args()

    # コマンドが指定されていない場合はヘルプを表示
    if not args.command:
        parser.print_help()
        return

    # コマンドの実行
    if args.command == "version":
        cli_shared.show_version()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
