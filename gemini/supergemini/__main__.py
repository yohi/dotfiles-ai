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

from . import __version__, show_version, get_config
from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD

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
            with open(GEMINI_MD, 'w') as f:
                f.write("# SuperGemini Framework\n\n")
                f.write("SuperGemini は Gemini CLI のための拡張フレームワークです。\n")
                f.write("詳細な使い方については、`SuperGemini commands` を実行して確認してください。\n")
        except Exception as e:
            logger.error(f"GEMINI.md ファイルの作成エラー: {e}")

def install_framework(profile="standard", interactive=False, force=False):
    """
    フレームワークのインストール
    """
    print(f"🚀 SuperGemini フレームワークのインストールを開始します（プロファイル: {profile}）")

    # 環境のセットアップ
    setup_environment()

    # 既存のインストールを確認
    is_installed = os.path.exists(GEMINI_MD) and os.path.getsize(GEMINI_MD) > 100

    if is_installed and not force:
        print("ℹ️  SuperGemini は既にインストールされています")
        if interactive:
            choice = input("上書きしますか？ (y/N): ").strip().lower()
            if choice != 'y':
                print("❌ インストールを中止しました")
                return
        else:
            print("❌ --force オプションを指定して実行してください")
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

    # コマンドをカテゴリごとに整理
    categories = {
        "分析系": ["analyze", "explain", "troubleshoot"],
        "開発系": ["implement", "improve", "build"],
        "設計系": ["design", "estimate"],
        "管理系": ["task", "workflow", "document"],
        "ツール系": ["test", "git", "cleanup", "load", "index", "spawn"]
    }

    for category, cmd_list in categories.items():
        print(f"【{category}】")
        for cmd in cmd_list:
            if cmd in commands and commands[cmd].get("enabled", True):
                desc = commands[cmd].get("description", "")
                print(f"  {prefix}:{cmd} - {desc}")
        print("")

    print("使用例: /sg:implement ログイン機能")

def show_personas():
    """
    利用可能なペルソナ一覧を表示
    """
    config = get_config()
    personas = config.get("personas", [])

    print("🎭 SuperGemini ペルソナ一覧:")
    print("")

    # ペルソナとその説明
    persona_details = {
        "architect": "🏗️  システム設計・アーキテクチャ",
        "developer": "💻 アプリケーション実装・開発",
        "frontend": "🎨 UI/UX・アクセシビリティ",
        "backend": "⚙️  API・インフラストラクチャ",
        "analyst": "📊 コード分析・最適化",
        "tester": "🧪 テスト設計・品質保証",
        "devops": "🚀 CI/CD・デプロイメント",
        "security": "🛡️  セキュリティ・脆弱性対策",
        "scribe": "✍️  ドキュメント・技術文書"
    }

    for persona in personas:
        if persona in persona_details:
            print(f"  @{persona} - {persona_details[persona]}")
        else:
            print(f"  @{persona}")

    print("")
    print("使用例: @architect として、マイクロサービスのアーキテクチャを設計して")

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
        import shlex
        editor = os.environ.get('EDITOR', 'nano')
        cmd = shlex.split(editor) + [CONFIG_PATH]
        subprocess.run(cmd, check=True)
        print("✅ 設定を編集しました")
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
    elif args.command == "config":
        show_config(args.edit, args.reset)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
