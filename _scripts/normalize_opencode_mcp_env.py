#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
# How to run:
#   uv run _scripts/normalize_opencode_mcp_env.py opencode.json

"""Translate APM environment placeholders to OpenCode MCP syntax."""

import re
import sys
from pathlib import Path
from typing import Final

ENV_PLACEHOLDER: Final = re.compile(r"\$\{env:([^}]+)\}")


def main() -> int:
    """Normalize APM environment placeholders to OpenCode syntax."""
    if len(sys.argv) != 2:
        print("Usage: normalize_opencode_mcp_env.py <opencode.json>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[1])
    repository_root = Path(__file__).resolve().parent.parent
    if not config_path.resolve().is_relative_to(repository_root):
        print("Configuration path must stay within the repository", file=sys.stderr)
        return 2

    config = config_path.read_text(encoding="utf-8")
    normalized, replacements = ENV_PLACEHOLDER.subn(r"{env:\1}", config)
    if replacements:
        _ = config_path.write_text(normalized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
