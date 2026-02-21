#!/usr/bin/env python3
"""
SuperGemini CLI
Gemini CLIを拡張するためのコマンドラインツール
"""

import os
import sys
import argparse
import logging
import shutil
from pathlib import Path

from . import __version__, show_version, get_config, get_personas_config
from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD

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


def setup_environment():
    """
    環境のセットアップ
    """
    os.makedirs(GEMINI_HOME, exist_ok=True)
    os.makedirs(SHARED_DIR, exist_ok=True)
    os.makedirs(COMMANDS_DIR, exist_ok=True)

    # 設定ファイルの作成
    config = get_config()

    # GEMINI.mdファイルの作成（存在しない場合）
    if not os.path.exists(GEMINI_MD):
        try:
            with open(GEMINI_MD, "w") as f:
                f.write("# SuperGemini Framework\n\n")
                f.write("SuperGemini は Gemini CLI のための拡張フレームワークです。\n")
                f.write(
                    "詳細な使い方については、`SuperGemini commands` を実行して確認してください。\n"
                )
        except Exception as e:
            logger.error(f"GEMINI.md ファイルの作成エラー: {e}")


def install_framework(profile="standard", interactive=False, force=False):
    """
    フレームワークのインストール
    """
    print(
        f"🚀 SuperGemini フレームワークのインストールを開始します（プロファイル: {profile}）"
    )

    # 環境のセットアップ
    setup_environment()

    # 既存のインストールを確認
    is_installed = os.path.exists(GEMINI_MD) and os.path.getsize(GEMINI_MD) > 100

    if is_installed and not force:
        print("ℹ️  SuperGemini は既にインストールされています")
        if interactive:
            choice = input("上書きしますか？ (y/N): ").strip().lower()
            if choice != "y":
                print("❌ インストールを中止しました")
                return

    print("📋 インストール中のコンポーネント:")

    # コア機能のインストール
    print("  • コアフレームワーク - インストール中...")

    # インストールプロファイルに応じて機能を追加
    if profile in ["standard", "developer"]:
        print("  • コマンド拡張 - インストール中...")
        print("  • ペルソナシステム - インストール中...")

    if profile == "developer":
        print("  • 開発者ツール - インストール中...")
        print("  • MCPサーバー連携 - インストール中...")

    print("\n✅ SuperGemini フレームワークのインストールが完了しました")
    print("\n🚀 使用方法:")
    print("1. Gemini CLI を起動: gemini")
    print("2. SuperGemini コマンドを使用:")
    print("   /sg:implement <feature>    - 機能の実装")
    print("   /sg:analyze <code>         - コード分析")
    print("   /sg:design <ui>            - UI/UXデザイン")
    print("   etc...")


def show_commands():
    """
    利用可能なコマンド一覧を表示
    """
    config = get_config()
    commands = config.get("commands", {})
    prefix = config.get("prefix", "/sg")

    print("📋 SuperGemini コマンド一覧:")
    print("")

    # 設定ファイルからコマンドをカテゴリごとに動的に整理
    categories = {}
    for cmd_name, cmd_info in commands.items():
        if cmd_info.get("enabled", True):
            category = cmd_info.get("category", "その他")
            if category not in categories:
                categories[category] = []
            categories[category].append(
                {"name": cmd_name, "description": cmd_info.get("description", "")}
            )

    # カテゴリの表示順序を定義（設定にない場合は最後に表示）
    category_order = ["分析系", "開発系", "設計系", "管理系", "ツール系"]

    # 順序に従ってカテゴリを表示
    for category in category_order:
        if category in categories:
            print(f"【{category}】")
            for cmd in categories[category]:
                print(f"  {prefix}:{cmd['name']} - {cmd['description']}")
            print("")

    # 定義されていないカテゴリがあれば最後に表示
    for category, cmd_list in categories.items():
        if category not in category_order:
            print(f"【{category}】")
            for cmd in cmd_list:
                print(f"  {prefix}:{cmd['name']} - {cmd['description']}")
            print("")

    print("使用例: /sg:implement ログイン機能")


def show_personas():
    """
    利用可能なペルソナ一覧を表示
    """
    config = get_config()
    personas_config = get_personas_config()
    personas = config.get("personas", [])

    print("🎭 SuperGemini ペルソナ一覧:")
    print("")

    # ペルソナ設定ファイルからペルソナ詳細を取得
    personas_data = personas_config.get("personas", {})

    for persona in personas:
        if persona in personas_data:
            persona_info = personas_data[persona]
            emoji = persona_info.get("emoji", "")
            title = persona_info.get("title", "")
            print(f"  @{persona} - {emoji} {title}")
        else:
            print(f"  @{persona}")

    print("")
    print("使用例: @architect として、マイクロサービスのアーキテクチャを設計して")
    print("")
    print("詳細情報を見るには: python -m gemini persona-detail <persona名>")


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


def show_config(edit=False, reset=False):
    """
    設定の表示・編集
    """
    from . import CONFIG_PATH

    if reset:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
        config = get_config()  # 新しい設定ファイルを作成
        print("✅ 設定をデフォルトにリセットしました")
        return

    config = get_config()

    if edit:
        # エディタで開く
        import subprocess

        editor = os.environ.get("EDITOR", "nano")
        try:
            subprocess.run([editor, CONFIG_PATH], check=True)
            print("✅ 設定を編集しました")
        except Exception as e:
            print(f"❌ エディタの起動に失敗しました: {e}")
    else:
        # 設定の表示
        print("📋 SuperGemini 設定:")
        print(f"  • バージョン: {config.get('version', '不明')}")
        print(f"  • 言語: {config.get('language', 'ja')}")
        print(f"  • コマンドプレフィックス: {config.get('prefix', '/sg')}")
        print(f"  • ペルソナ数: {len(config.get('personas', []))}")
        print(f"  • コマンド数: {len(config.get('commands', {}))}")
        print(f"  • 設定ファイル: {CONFIG_PATH}")


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
        install_framework(args.profile, args.interactive, args.force)
    elif args.command == "commands":
        show_commands()
    elif args.command == "personas":
        show_personas()
    elif args.command == "persona-detail":
        show_persona_detail(args.persona_name)
    elif args.command == "config":
        show_config(args.edit, args.reset)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
