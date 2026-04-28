import os
import logging

logger = logging.getLogger("Gemini.CLI")

def setup_environment():
    """
    Gemini CLI の実行環境をセットアップする
    """
    from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD
    
    os.makedirs(gemini_home, exist_ok=True)
    os.makedirs(shared_dir, exist_ok=True)
    os.makedirs(commands_dir, exist_ok=True)
    
    if not os.path.exists(gemini_md):
        try:
            with open(gemini_md, 'w', encoding='utf-8') as f:
                f.write("# Gemini CLI\n\n")
                f.write("Gemini CLI のための設定ファイルです。\n")
        except Exception:
            logger.exception("GEMINI.md ファイルの作成エラー")

def show_version():
    """
    バージョン情報を表示
    """
    from . import __version__
    print(f"Gemini CLI v{__version__}")
