include _mk/core.mk
include _mk/help.mk

# .PHONY targets
.PHONY: install setup install-ai setup-ai

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

# Top-level install and setup (delegates to _mk/main.mk which handles agents/ides)
install: install-agents install-ides ## AI 関連コンポーネントの全インストール
setup: setup-agents setup-ides ## AI 関連コンポーネントの全設定適用

# Component-specific targets (placeholder or direct implementation)
install-ai: ## dotfiles-ai のコアコンポーネントをインストール
	@echo "==> Installing dotfiles-ai core..."
	@# TODO: Add specific core installation steps here

setup-ai: ## dotfiles-ai のコア設定を適用
	@echo "==> Setting up dotfiles-ai core..."
	@# TODO: Add specific core setup steps here
