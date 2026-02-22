#!/usr/bin/env python3
"""
SuperGemini CLI
Gemini CLIを拡張するためのコマンドラインツール
"""

import os
import sys
import argparse
import logging
from pathlib import Path

from . import __version__, show_version, get_config
from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD
from .. import cli_shared

# ロガーの設定
logger = logging.getLogger("SuperGemini.CLI")

def create_parser():
    """
    コマンドラインパーサーの作成
    """
    parser = argparse.ArgumentParser(
        description="SuperGemini - Gemini CLI拡張フレームワーク",
        epilog="SuperGemini v" + __version__
    )

    # サブコマンドの設定
    subparsers = parser.add_subparsers(dest="command", help="コマンド")

    # バージョン表示コマンド
    version_parser = subparsers.add_parser("version", help="バージョン情報を表示")

    # インストールコマンド
    install_parser = subparsers.add_parser("install", help="SuperGemini をインストールまたは更新")
    install_parser.add_argument("--profile", choices=["minimal", "standard", "developer"],
                              default="standard", help="インストールプロファイル")
    install_parser.add_argument("--interactive", action="store_true", help="対話モードでインストール")
    install_parser.add_argument("--force", action="store_true", help="既存の設定を上書き")

    # コマンド一覧表示
    commands_parser = subparsers.add_parser("commands", help="利用可能なコマンド一覧を表示")

    # 設定表示・編集
    config_parser = subparsers.add_parser("config", help="設定を表示・編集")
    config_parser.add_argument("--edit", action="store_true", help="設定をエディタで開く")
    config_parser.add_argument("--reset", action="store_true", help="設定をデフォルトにリセット")

    # ペルソナ一覧表示
    personas_parser = subparsers.add_parser("personas", help="利用可能なペルソナ一覧を表示")

    return parser

def main():
    """
    メイン関数
    """
    # コマンドライン引数のパース
    parser = create_parser()
    args = parser.parse_args()

    # コマンドが指定されていない場合はヘルプを表示
    if not args.command:
        parser.print_help()
        return

    # コマンドの実行
    if args.command == "version":
        show_version()
    elif args.command == "install":
        cli_shared.install_framework(args.profile, args.interactive, args.force, GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD, get_config)
    elif args.command == "commands":
        cli_shared.show_commands(get_config)
    elif args.command == "personas":
        cli_shared.show_personas(get_config)
    elif args.command == "config":
        from . import CONFIG_PATH
        cli_shared.show_config(args.edit, args.reset, get_config, CONFIG_PATH)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
