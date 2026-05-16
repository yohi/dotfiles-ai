# ============================================================
# Antigravity: インストール・設定
# ============================================================

ANTIGRAVITY_CONFIG_DIR ?= $(HOME)/.gemini/antigravity
ANTIGRAVITY_MCP_PATH ?= $(ANTIGRAVITY_CONFIG_DIR)/mcp_config.json
ANTIGRAVITY_DOTFILES_MCP ?= $(REPO_ROOT)/antigravity/mcp_config.json

.PHONY: setup-antigravity check-antigravity uninstall-antigravity

# Antigravityの設定を適用
setup-antigravity: ## Antigravityの設定ファイルを適用（設定ファイルがない場合はスキップ）
	@echo "🔧 Antigravityの設定を適用中..."; \
	if [ ! -f "$(ANTIGRAVITY_DOTFILES_MCP)" ]; then \
		echo "ℹ️  Antigravity MCP 設定ファイルが見つかりません（スキップ）: $(ANTIGRAVITY_DOTFILES_MCP)"; \
		exit 0; \
	fi; \
	mkdir -p "$(ANTIGRAVITY_CONFIG_DIR)"; \
	if [ -e "$(ANTIGRAVITY_MCP_PATH)" ] && [ ! -L "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		backup="$(ANTIGRAVITY_MCP_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "⚠️  既存の設定ファイルを退避します: $$backup"; \
		mv "$(ANTIGRAVITY_MCP_PATH)" "$$backup"; \
	fi; \
	ln -sfn "$(ANTIGRAVITY_DOTFILES_MCP)" "$(ANTIGRAVITY_MCP_PATH)"; \
	echo "✅ 設定を適用しました: $(ANTIGRAVITY_MCP_PATH)"

# Antigravityの状態確認
check-antigravity: ## Antigravityの状態を確認
	@echo "🔍 Antigravityの状態確認..."
	@if [ -L "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		actual=$$(readlink -f "$(ANTIGRAVITY_MCP_PATH)" 2>/dev/null || readlink "$(ANTIGRAVITY_MCP_PATH)" 2>/dev/null || true); \
		expected=$$(readlink -f "$(ANTIGRAVITY_DOTFILES_MCP)" 2>/dev/null || readlink "$(ANTIGRAVITY_DOTFILES_MCP)" 2>/dev/null || true); \
		if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
			echo "✅ config: $(ANTIGRAVITY_MCP_PATH) -> $(ANTIGRAVITY_DOTFILES_MCP)"; \
		else \
			echo "⚠️  config: $(ANTIGRAVITY_MCP_PATH) points to $$actual (expected $$expected)"; \
		fi; \
	elif [ -e "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		echo "⚠️  config: $(ANTIGRAVITY_MCP_PATH) exists but is not a symlink"; \
	else \
		echo "⚠️  config: $(ANTIGRAVITY_MCP_PATH) is not configured"; \
	fi

# Antigravity の起動
.PHONY: run-antigravity
run-antigravity: ## Antigravity を起動
	@if [ -f .env ]; then \
		set -a; \
		. ./.env; \
		set +a; \
	fi; \
	echo "🚀 Starting Antigravity..."; \
	antigravity &

# Antigravityの設定を削除
uninstall-antigravity: ## Antigravityの設定を削除
	@echo "🗑️  Antigravityの設定を削除中..."
	@if [ -L "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		rm "$(ANTIGRAVITY_MCP_PATH)"; \
		echo "✅ 設定を削除しました: $(ANTIGRAVITY_MCP_PATH)"; \
	else \
		echo "ℹ️  削除する設定はありません: $(ANTIGRAVITY_MCP_PATH)"; \
	fi
