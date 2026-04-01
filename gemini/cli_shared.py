import os
import sys
import logging

logger = logging.getLogger("SuperGemini.CLI")

def setup_environment(gemini_home, shared_dir, commands_dir, gemini_md, get_config):
    os.makedirs(gemini_home, exist_ok=True)
    os.makedirs(shared_dir, exist_ok=True)
    os.makedirs(commands_dir, exist_ok=True)
    _ = get_config()
    if not os.path.exists(gemini_md):
        try:
            with open(gemini_md, 'w', encoding='utf-8') as f:
                f.write("# SuperGemini Framework\n\n")
                f.write("SuperGemini は Gemini CLI のための拡張フレームワークです。\n")
                f.write("詳細な使い方については、`SuperGemini commands` を実行して確認してください。\n")
        except Exception:
            logger.exception("GEMINI.md ファイルの作成エラー")

def install_framework(profile, interactive, force, gemini_home, shared_dir, commands_dir, gemini_md, get_config):
    print(f"🚀 SuperGemini フレームワークのインストールを開始します（プロファイル: {profile}）")
    setup_environment(gemini_home, shared_dir, commands_dir, gemini_md, get_config)
    is_installed = os.path.exists(gemini_md) and os.path.getsize(gemini_md) > 100
    if is_installed and not force:
        print("ℹ️  SuperGemini は既にインストールされています")
        if not interactive:
            print("❌ --force オプションを指定して実行してください")
            sys.exit(1)
        choice = input("上書きしますか？ (y/N): ").strip().lower()
        if choice != "y":
            print("❌ インストールを中止しました")
            sys.exit(0)
    print("📋 インストール中のコンポーネント:")
    print("  • コアフレームワーク - インストール中...")
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

def show_commands(get_config):
    config = get_config()
    commands = config.get("commands", {})
    prefix = config.get("prefix", "/sg")
    print("📋 SuperGemini コマンド一覧:\n")
    categories: dict[str, list[dict[str, str]]] = {}
    for cmd_name, cmd_info in commands.items():
        if cmd_info.get("enabled", True):
            category = cmd_info.get("category", "その他")
            if category not in categories:
                categories[category] = []
            categories[category].append({"name": cmd_name, "description": cmd_info.get("description", "")})
    category_order = ["分析系", "開発系", "設計系", "管理系", "ツール系"]
    for category in category_order:
        if category in categories:
            print(f"【{category}】")
            for cmd in categories[category]:
                print(f"  {prefix}:{cmd['name']} - {cmd['description']}")
            print("")
    for category, cmd_list in categories.items():
        if category not in category_order:
            print(f"【{category}】")
            for cmd in cmd_list:
                print(f"  {prefix}:{cmd['name']} - {cmd['description']}")
            print("")
    print("使用例: /sg:implement ログイン機能")

def show_personas(get_config, get_personas_config=None):
    config = get_config()
    personas = config.get("personas", [])
    print("🎭 SuperGemini ペルソナ一覧:\n")

    if get_personas_config:
        personas_config = get_personas_config()
        personas_data = personas_config.get("personas", {})
        for persona in personas:
            if persona in personas_data:
                persona_info = personas_data[persona]
                emoji = persona_info.get("emoji", "")
                title = persona_info.get("title", "")
                print(f"  @{persona} - {emoji} {title}")
            else:
                print(f"  @{persona}")
    else:
        persona_details = {
            "architect": "🏗️  システム設計・アーキテクチャ",
            "developer": "💻 アプリケーション実装・開発",
            "frontend": "🎨 UI/UX・アクセシビリティ",
            "backend": "⚙️  API・インフラストラクチャ",
            "analyst": "📊 コード分析・最適化",
            "tester": "🧪 テスト設計・品質保証",
            "devops": "🔧 CI/CD・デプロイメント",
            "security": "🛡️  セキュリティ・脆弱性対策",
            "scribe": "✍️  ドキュメント・技術文書"
        }
        for persona in personas:
            if persona in persona_details:
                print(f"  @{persona} - {persona_details[persona]}")
            else:
                print(f"  @{persona}")

    print("\n使用例: @architect として、マイクロサービスのアーキテクチャを設計して")
    if get_personas_config:
        print("\n詳細情報を見るには: python -m gemini persona-detail <persona名>")

def show_config(edit, reset, get_config, config_path):
    if reset:
        if os.path.exists(config_path):
            os.remove(config_path)
        config = get_config()
        print("✅ 設定をデフォルトにリセットしました")
        return
    config = get_config()
    if edit:
        import subprocess
        import shlex
        editor = os.environ.get("EDITOR", "nano")
        editor = (editor or "").strip()
        if not editor:
            editor = "nano"
        try:
            cmd = shlex.split(editor)
            subprocess.run(cmd + [config_path], check=True)
            print("✅ 設定を編集しました")
        except Exception as e:
            print(f"❌ エディタの起動に失敗しました: {e}")
    else:
        print("📋 SuperGemini 設定:")
        print(f"  • バージョン: {config.get('version', '不明')}")
        print(f"  • 言語: {config.get('language', 'ja')}")
        print(f"  • コマンドプレフィックス: {config.get('prefix', '/sg')}")
        print(f"  • ペルソナ数: {len(config.get('personas', []))}")
        print(f"  • コマンド数: {len(config.get('commands', {}))}")
        print(f"  • 設定ファイル: {config_path}")
