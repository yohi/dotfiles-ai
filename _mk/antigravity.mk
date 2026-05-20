# ============================================================
# Antigravity: インストール・設定 (New Version)
# ============================================================

# URLs
ANTIGRAVITY_IDE_URL := https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/stable/2.0.1-4861014005645312/linux-x64/Antigravity%20IDE.tar.gz
ANTIGRAVITY_HUB_URL := https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/linux-x64/Antigravity.tar.gz
ANTIGRAVITY_CLI_CMD := curl -fsSL https://antigravity.google/cli/install.sh | bash

# Paths
ANTIGRAVITY_OPT_DIR := $(HOME)/.local/opt/antigravity
ANTIGRAVITY_BIN_DIR := $(HOME)/.local/bin
ANTIGRAVITY_TMP_DIR := $(REPO_ROOT)/.tmp/antigravity

ANTIGRAVITY_CONFIG_DIR := $(HOME)/.gemini/antigravity
ANTIGRAVITY_MCP_PATH := $(ANTIGRAVITY_CONFIG_DIR)/mcp_config.json
# APMが生成するMCP設定
APM_MCP_CONFIG := $(REPO_ROOT)/.gemini/mcp-config.json

.PHONY: install-antigravity install-antigravity-ide install-antigravity-hub install-antigravity-cli
.PHONY: setup-antigravity uninstall-antigravity check-antigravity clean-antigravity-install

# Antigravity一式をインストール
install-antigravity: install-antigravity-ide install-antigravity-hub install-antigravity-cli setup-antigravity ## Antigravity一式をインストールして設定を同期

install-antigravity-ide: ## Antigravity IDE をインストール
	@echo "🎨 Installing Antigravity IDE..."
	@mkdir -p "$(ANTIGRAVITY_OPT_DIR)/ide" "$(ANTIGRAVITY_TMP_DIR)"
	@curl -L "$(ANTIGRAVITY_IDE_URL)" -o "$(ANTIGRAVITY_TMP_DIR)/ide.tar.gz"
	@tar -xzf "$(ANTIGRAVITY_TMP_DIR)/ide.tar.gz" -C "$(ANTIGRAVITY_OPT_DIR)/ide" --strip-components=1
	@ln -sfn "$(ANTIGRAVITY_OPT_DIR)/ide/antigravity-ide" "$(ANTIGRAVITY_BIN_DIR)/antigravity-ide"
	@echo "✅ Antigravity IDE installed to $(ANTIGRAVITY_OPT_DIR)/ide"

install-antigravity-hub: ## Antigravity Hub をインストール
	@echo "🔗 Installing Antigravity Hub..."
	@mkdir -p "$(ANTIGRAVITY_OPT_DIR)/hub" "$(ANTIGRAVITY_TMP_DIR)"
	@curl -L "$(ANTIGRAVITY_HUB_URL)" -o "$(ANTIGRAVITY_TMP_DIR)/hub.tar.gz"
	@tar -xzf "$(ANTIGRAVITY_TMP_DIR)/hub.tar.gz" -C "$(ANTIGRAVITY_OPT_DIR)/hub" --strip-components=1
	@ln -sfn "$(ANTIGRAVITY_OPT_DIR)/hub/antigravity-hub" "$(ANTIGRAVITY_BIN_DIR)/antigravity-hub"
	@echo "✅ Antigravity Hub installed to $(ANTIGRAVITY_OPT_DIR)/hub"

install-antigravity-cli: ## Antigravity CLI をインストール
	@echo "💻 Installing Antigravity CLI..."
	@$(ANTIGRAVITY_CLI_CMD)
	@echo "✅ Antigravity CLI installed"

# Antigravityの設定をAPMと同期
setup-antigravity: ## APMの設定をAntigravityに同期（シンボリックリンク作成）
	@echo "🔧 Synchronizing Antigravity config with APM..."
	@mkdir -p "$(ANTIGRAVITY_CONFIG_DIR)"
	@if [ -f "$(APM_MCP_CONFIG)" ]; then \
		if [ -e "$(ANTIGRAVITY_MCP_PATH)" ] && [ ! -L "$(ANTIGRAVITY_MCP_PATH)" ]; then \
			backup="$(ANTIGRAVITY_MCP_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "⚠️  Existing config backed up to: $$backup"; \
			mv "$(ANTIGRAVITY_MCP_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(APM_MCP_CONFIG)" "$(ANTIGRAVITY_MCP_PATH)"; \
		echo "✅ Linked: $(ANTIGRAVITY_MCP_PATH) -> $(APM_MCP_CONFIG)"; \
	else \
		echo "⚠️  APM MCP config not found: $(APM_MCP_CONFIG)"; \
		echo "ℹ️  Run 'apm install' first to generate the config."; \
	fi

# Antigravityの状態確認
check-antigravity: ## Antigravityの状態確認
	@echo "🔍 Antigravityの状態確認..."
	@for bin in antigravity antigravity-ide antigravity-hub; do \
		if command -v $$bin >/dev/null 2>&1; then \
			echo "✅ $$bin: $$(command -v $$bin)"; \
		else \
			echo "❌ $$bin: Not found in PATH"; \
		fi; \
	done
	@echo "🔗 Config Sync Status:"
	@if [ -L "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		target=$$(readlink -f "$(ANTIGRAVITY_MCP_PATH)"); \
		if [ "$$target" = "$$(readlink -f $(APM_MCP_CONFIG))" ]; then \
			echo "✅ Sync: OK ($(ANTIGRAVITY_MCP_PATH) -> APM)"; \
		else \
			echo "⚠️  Sync: Misaligned ($$target)"; \
		fi; \
	elif [ -e "$(ANTIGRAVITY_MCP_PATH)" ]; then \
		echo "⚠️  Sync: Not a symbolic link (manual config exists)"; \
	else \
		echo "❌ Sync: Not configured"; \
	fi

# Antigravityのアンインストール
uninstall-antigravity: ## Antigravity一式をアンインストール
	@echo "🗑️  Uninstalling Antigravity..."
	@rm -rf "$(ANTIGRAVITY_OPT_DIR)"
	@rm -f "$(ANTIGRAVITY_BIN_DIR)/antigravity-ide"
	@rm -f "$(ANTIGRAVITY_BIN_DIR)/antigravity-hub"
	@rm -f "$(ANTIGRAVITY_MCP_PATH)"
	@echo "⚠️  CLI (antigravity) は個別に削除してください"
	@echo "✅ Uninstalled Antigravity binaries and links"

.PHONY: clean-antigravity-install
clean-antigravity-install: ## Antigravityのインストール用一時ファイルを削除
	@echo "🧹 Cleaning Antigravity installation temporary files..."
	@rm -rf "$(ANTIGRAVITY_TMP_DIR)"
	@echo "✅ Cleaned"
