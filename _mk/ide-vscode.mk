export SHELL := /bin/bash

# ============================================================
# VSCode IDE セットアップ用Makefile
# VSCodeのAI設定（MCP等）の管理を担当
# ============================================================

# OS検出とディレクトリ設定
OS_NAME := $(shell uname -s)
ifeq ($(OS_NAME),Darwin)
    # macOS
    VSCODE_USER_DIR := $(HOME)/Library/Application Support/Code/User
else
    # Linux
    VSCODE_USER_DIR := $(HOME)/.config/Code/User
endif

.PHONY: setup-vscode

setup-vscode:
	@echo "📝 VSCodeのAI設定をリンクしています..."
	@mkdir -p "$(VSCODE_USER_DIR)/globalStorage"
	@# VSCodeのUI設定（settings.json, keybindings.json）は dotfiles-ide が担当します。
	@# ここでは古い（壊れた）リンクのクリーンアップのみ行います。
	@for f in settings.json keybindings.json; do \
	        dst="$(VSCODE_USER_DIR)/$$f"; \
	        if [ -L "$$dst" ] && [ ! -e "$$dst" ]; then \
	                echo "🧹 古い設定シンボリックリンクを削除します (dotfiles-ide へ移管): $$f"; \
	                rm "$$dst"; \
	        fi; \
	done
	@echo "✅ VSCodeのAI設定（クリーンアップ）が完了しました"

.PHONY: uninstall-vscode
uninstall-vscode:
	@echo "🧹 VSCodeのAI設定リンクを解除しています..."
	@echo "✅ VSCodeのAI設定解除が完了しました"
