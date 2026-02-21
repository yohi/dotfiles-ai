"""
Gemini CLI拡張フレームワークパッケージ
"""

from gemini.supergemini import (
    __version__,
    show_version,
    get_config,
    get_personas_config,
    GEMINI_HOME,
    SHARED_DIR,
    COMMANDS_DIR,
    GEMINI_MD,
)

__all__ = [
    "__version__",
    "show_version",
    "get_config",
    "get_personas_config",
    "GEMINI_HOME",
    "SHARED_DIR",
    "COMMANDS_DIR",
    "GEMINI_MD",
]
