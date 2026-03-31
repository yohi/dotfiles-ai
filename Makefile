include _mk/core.mk
include _mk/help.mk

# Include individual modules
-include _mk/variables.mk
-include _mk/idempotency.mk
-include _mk/main.mk
-include _mk/claude.mk
-include _mk/gemini.mk
-include _mk/codex.mk
-include _mk/opencode.mk
-include _mk/antigravity.mk
-include _mk/superclaude.mk
-include _mk/skillport.mk
-include _mk/sync-agents.mk
-include _mk/mcp.mk
-include _mk/superpowers.mk
-include _mk/ide-cursor.mk
-include _mk/ide-vscode.mk

install: install-ai ## AI 関連のインストール
setup: setup-ai ## AI の設定適用

install-ai:
	@echo "==> Installing dotfiles-ai"

setup-ai:
	@echo "==> Setting up dotfiles-ai"
