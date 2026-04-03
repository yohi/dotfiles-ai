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
all: install ## 全てのコンポーネントをビルド/インストール

clean: ## 生成されたアーティファクトとキャッシュを削除
	@echo "🧹 クリーンアップ中..."
	@$(MAKE) -s clean-legacy 2>/dev/null || true
	@# _mk/main.mk の clean を呼び出し
	@$(MAKE) -s -f _mk/main.mk clean REPO_ROOT=$(REPO_ROOT) 2>/dev/null || true
	@rm -rf build/ dist/ *.pyc __pycache__ .ruff_cache .mypy_cache
	@echo "✅ クリーンアップが完了しました"

test: ## プロジェクトのテスト/静的解析を実行
	@$(MAKE) lint

# Top-level install and setup (delegated to _mk/main.mk)
# install: install-agents install-ides (Defined in _mk/main.mk)
# setup: setup-agents setup-ides (Defined in _mk/main.mk)

# Component-specific targets (Core AI logic)
install-ai: ## dotfiles-ai のコアコンポーネントをインストール
	@echo "==> Installing dotfiles-ai core..."
	@if ! command -v npm >/dev/null 2>&1; then echo "❌ npm が見つかりません。Node.js をインストールしてください"; exit 1; fi
	@if ! command -v python3 >/dev/null 2>&1; then echo "❌ python3 が見つかりません。Python をインストールしてください"; exit 1; fi
	@$(MAKE) install-requirements
	@echo "✅ dotfiles-ai のコアコンポーネントがインストールされました"

setup-ai: ## dotfiles-ai のコア設定を適用
	@echo "==> Setting up dotfiles-ai core..."
	@# MCP 設定のレンダリング
	@$(MAKE) mcp-render
	@# エージェントスキルの同期
	@$(MAKE) sync-agents
	@echo "✅ dotfiles-ai のコア設定が適用されました"
