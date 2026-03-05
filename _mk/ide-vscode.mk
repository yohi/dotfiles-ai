export SHELL := /bin/bash

# ============================================================
# VSCode IDE セットアップ用Makefile
# VSCodeの設定、拡張機能、SuperCopilotの管理を担当
# ============================================================

.PHONY: setup-vscode install-supercopilot

setup-vscode:
	@echo "📝 VSCodeの設定をリンクしています..."
	@mkdir -p $(HOME)/.config/Code/User
	@ln -sf $(REPO_ROOT)/ide/vscode/settings.json $(HOME)/.config/Code/User/settings.json
	@ln -sf $(REPO_ROOT)/ide/vscode/keybindings.json $(HOME)/.config/Code/User/keybindings.json
	@echo "✅ VSCodeの設定リンクが完了しました"

install-supercopilot:
	@echo "🚀 SuperCopilot Framework のセットアップを開始..."
	@bash $(REPO_ROOT)/ide/vscode/setup-supercopilot.sh
	@echo "✅ SuperCopilot のセットアップが完了しました"

.PHONY: uninstall-vscode
uninstall-vscode:
	@echo "🧹 VSCodeの設定リンクを解除しています..."
	@rm -f $(HOME)/.config/Code/User/settings.json
	@rm -f $(HOME)/.config/Code/User/keybindings.json
	@rm -rf $(HOME)/.vscode/supercopilot
	@echo "✅ VSCodeの設定解除が完了しました"
