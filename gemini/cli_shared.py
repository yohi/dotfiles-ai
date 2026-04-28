import os
import logging

logger = logging.getLogger("Gemini.CLI")

def setup_environment():
    """
    Gemini CLI の実行環境をセットアップする
    """
    from . import GEMINI_HOME, SHARED_DIR, COMMANDS_DIR, GEMINI_MD
    
    os.makedirs(GEMINI_HOME, exist_ok=True)
    os.makedirs(SHARED_DIR, exist_ok=True)
    os.makedirs(COMMANDS_DIR, exist_ok=True)
    
    if not os.path.exists(GEMINI_MD):
        try:
            with open(GEMINI_MD, 'x', encoding='utf-8') as f:
                f.write("# Gemini CLI\n\n")
                f.write("Gemini CLI のための設定ファイルです。\n")
        except FileExistsError:
            pass  # 既に存在する場合は何もしない
        except OSError:
            logger.exception("GEMINI.md ファイルの作成エラー")
            raise

def show_version():
    """
    バージョン情報を表示
    """
    from . import __version__
    print(f"Gemini CLI v{__version__}")
