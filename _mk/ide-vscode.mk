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

.PHONY: setup-vscode

setup-vscode:
	@echo "📝 VSCodeの設定をリンクしています..."
	@mkdir -p "$(VSCODE_USER_DIR)"

	@echo "✅ VSCodeの設定リンクが完了しました"

.PHONY: uninstall-vscode
uninstall-vscode:
	@echo "🧹 VSCodeの設定リンクを解除しています..."
	# @if [ -L "$(VSCODE_USER_DIR)/settings.json" ]; then rm -f "$(VSCODE_USER_DIR)/settings.json"; fi # Moved to dotfiles-ide
	# @if [ -L "$(VSCODE_USER_DIR)/keybindings.json" ]; then rm -f "$(VSCODE_USER_DIR)/keybindings.json"; fi # Moved to dotfiles-ide
	@if [ -L "$(HOME)/.vscode/supercopilot" ]; then rm -f "$(HOME)/.vscode/supercopilot"; fi
	@echo "✅ VSCodeの設定解除が完了しました"
