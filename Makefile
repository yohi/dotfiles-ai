include _mk/core.mk
include _mk/help.mk

# .PHONY targets
.PHONY: all clean test install setup install-ai setup-ai init sync secrets status

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

# Standard Makefile targets
# (Standard targets like all, install, setup, sync are defined in _mk/main.mk)

clean: ## 生成されたアーティファクトとキャッシュを削除
	@echo "🧹 クリーンアップ中..."
	@$(MAKE) -s clean-legacy 2>/dev/null || true
	@# _mk/main.mk の clean-internal を呼び出し
	@$(MAKE) -s clean-internal 2>/dev/null || true
	@rm -rf build/ dist/ *.pyc __pycache__ .ruff_cache .mypy_cache
	@echo "✅ クリーンアップが完了しました"

test: ## プロジェクトのテスト/静的解析を実行
	@$(MAKE) lint
