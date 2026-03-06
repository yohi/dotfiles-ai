export SHELL := /bin/bash

# ============================================================
# VSCode IDE セットアップ用Makefile
# VSCodeの設定、拡張機能、SuperCopilotの管理を担当
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

.PHONY: setup-vscode install-supercopilot

setup-vscode:
	@echo "📝 VSCodeの設定をリンクしています..."
	@mkdir -p "$(VSCODE_USER_DIR)"
	@for f in settings.json keybindings.json; do \
		src="$(REPO_ROOT)/ide/vscode/$f"; \
		dst="$(VSCODE_USER_DIR)/$f"; \
		if [ -f "$dst" ] && [ ! -L "$dst" ]; then \
		        backup="$dst.bak.$$(date +%Y%m%d_%H%M%S)"; \
		        echo "⚠️  既存の $f をバックアップします: $backup"; \
		        mv "$dst" "$backup"; \
		elif [ -L "$dst" ] && [ "$(readlink "$dst")" != "$src" ]; then \
		        echo "🔄 シンボリックリンクを更新します: $dst"; \
		fi; \
		ln -sf "$src" "$dst"; \
		done
		@echo "✅ VSCodeの設定リンクが完了しました"

		install-supercopilot:
		@echo "🚀 SuperCopilot Framework のセットアップを開始..."
		@bash $(REPO_ROOT)/ide/vscode/setup-supercopilot.sh
		@echo "✅ SuperCopilot のセットアップが完了しました"

		.PHONY: uninstall-vscode
		uninstall-vscode:
		@echo "🧹 VSCodeの設定リンクを解除しています..."
		@if [ -L "$(VSCODE_USER_DIR)/settings.json" ]; then rm -f "$(VSCODE_USER_DIR)/settings.json"; fi
		@if [ -L "$(VSCODE_USER_DIR)/keybindings.json" ]; then rm -f "$(VSCODE_USER_DIR)/keybindings.json"; fi
		@if [ -L "$(HOME)/.vscode/supercopilot" ]; then rm -f "$(HOME)/.vscode/supercopilot"; fi
		@echo "✅ VSCodeの設定解除が完了しました"
