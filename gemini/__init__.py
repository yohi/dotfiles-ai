"""
Gemini CLI パッケージ
"""

import os
from pathlib import Path

__version__ = "1.0.0"

# グローバル定数
HOME_DIR = str(Path.home())
GEMINI_HOME = os.path.join(HOME_DIR, ".gemini")
SHARED_DIR = os.path.join(GEMINI_HOME, "shared")
COMMANDS_DIR = os.path.join(GEMINI_HOME, "commands")
GEMINI_MD = os.path.join(GEMINI_HOME, "GEMINI.md")

__all__ = [
    "__version__",
    "GEMINI_HOME",
    "SHARED_DIR",
    "COMMANDS_DIR",
    "GEMINI_MD",
]
