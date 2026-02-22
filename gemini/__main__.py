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

from . import __version__, show_version, get_config, get_personas_config
from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD
from . import cli_shared

# ロガーの設定
logger = logging.getLogger("SuperGemini.CLI")


def create_parser():
    """
    コマンドラインパーサーの作成
    """
    parser = argparse.ArgumentParser(
        description="SuperGemini - Gemini CLI拡張フレームワーク",
        epilog="SuperGemini v" + __version__,
    )

    # サブコマンドの設定
    subparsers = parser.add_subparsers(dest="command", help="コマンド")

    # バージョン表示コマンド
    version_parser = subparsers.add_parser("version", help="バージョン情報を表示")

    # インストールコマンド
    install_parser = subparsers.add_parser(
        "install", help="SuperGemini をインストールまたは更新"
    )
    install_parser.add_argument(
        "--profile",
        choices=["minimal", "standard", "developer"],
        default="standard",
        help="インストールプロファイル",
    )
    install_parser.add_argument(
        "--interactive", action="store_true", help="対話モードでインストール"
    )
    install_parser.add_argument(
        "--force", action="store_true", help="既存の設定を上書き"
    )

    # コマンド一覧表示
    commands_parser = subparsers.add_parser(
        "commands", help="利用可能なコマンド一覧を表示"
    )

    # 設定表示・編集
    config_parser = subparsers.add_parser("config", help="設定を表示・編集")
    config_parser.add_argument(
        "--edit", action="store_true", help="設定をエディタで開く"
    )
    config_parser.add_argument(
        "--reset", action="store_true", help="設定をデフォルトにリセット"
    )

    # ペルソナ一覧表示
    personas_parser = subparsers.add_parser(
        "personas", help="利用可能なペルソナ一覧を表示"
    )

    # ペルソナ詳細表示
    persona_detail_parser = subparsers.add_parser(
        "persona-detail", help="指定されたペルソナの詳細情報を表示"
    )
    persona_detail_parser.add_argument("persona_name", help="詳細を表示するペルソナ名")

    return parser


def show_persona_detail(persona_name):
    """
    指定されたペルソナの詳細情報を表示
    """
    personas_config = get_personas_config()
    personas_data = personas_config.get("personas", {})

    if persona_name not in personas_data:
        print(f"❌ ペルソナ '{persona_name}' が見つかりません。")
        print("利用可能なペルソナ一覧を確認するには: python -m gemini personas")
        return

    persona_info = personas_data[persona_name]
    emoji = persona_info.get("emoji", "")
    title = persona_info.get("title", "")
    description = persona_info.get("description", "")
    specialties = persona_info.get("specialties", [])

    print(f"🎭 ペルソナ詳細: @{persona_name}")
    print("=" * 50)
    print(f"{emoji} {title}")
    print("")
    print("📝 説明:")
    print(f"  {description}")
    print("")

    if specialties:
        print("🎯 専門分野:")
        for specialty in specialties:
            print(f"  • {specialty}")
        print("")

    print("💡 使用例:")
    print(f"  @{persona_name} として、システムの改善提案をして")


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
        cli_shared.show_personas(get_config, get_personas_config)
    elif args.command == "persona-detail":
        show_persona_detail(args.persona_name)
    elif args.command == "config":
        from .supergemini import CONFIG_PATH
        cli_shared.show_config(args.edit, args.reset, get_config, CONFIG_PATH)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
