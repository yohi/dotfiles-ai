# ============================================================
# Claude Code / Opcode セットアップ用Makefile
# Claude Code (CLI)、Opcode (GUI) のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)

define create_desktop_entry
	echo "📝 デスクトップエントリーを作成中..."; \
	printf "[Desktop Entry]\nName=Opcode\nComment=A powerful GUI app and Toolkit for Claude Code\nExec=/opt/opcode/opcode\nTryExec=/opt/opcode/opcode\nIcon=applications-development\nTerminal=false\nType=Application\nCategories=Development;IDE;Utility;\nStartupWMClass=opcode\n" | sudo tee /usr/share/applications/opcode.desktop > /dev/null && \
	sudo chmod +x /usr/share/applications/opcode.desktop && \
	(sudo update-desktop-database 2>/dev/null || true)
endef

# Opcode (Claude Code GUI) のバージョンは _mk/variables.mk で定義されています

# Claude Code のインストール
.PHONY: install-packages-claude-code
install-packages-claude-code:
	@echo "🤖 Claude Code のバージョンを確認中..."
	@if ! command -v npm >/dev/null 2>&1; then \
		echo "❌ npm が見つかりません。先に Node.js/npm をインストールしてください"; \
		exit 1; \
	fi
	@LATEST_VERSION=$$(npm show @anthropic-ai/claude-code version 2>/dev/null || echo "error"); \
	CURRENT_VERSION=$$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
	if [ "$$LATEST_VERSION" = "error" ]; then \
		echo "⚠️  最新バージョンの取得に失敗しました。インストールを試行します..."; \
		npm install -g @anthropic-ai/claude-code; \
	elif [ "$$CURRENT_VERSION" = "$$LATEST_VERSION" ]; then \
		echo "✅ Claude Code は既に最新バージョン ($$CURRENT_VERSION) がインストールされています。"; \
	else \
		if [ "$$CURRENT_VERSION" = "none" ]; then \
			echo "📦 Claude Code を新規インストールします (バージョン: $$LATEST_VERSION)"; \
		else \
			echo "🔄 Claude Code をアップデートします ($$CURRENT_VERSION -> $$LATEST_VERSION)"; \
		fi; \
		if ! npm install -g @anthropic-ai/claude-code; then \
			echo "❌ Claude Code のインストールに失敗しました"; \
			exit 1; \
		fi; \
	fi
	@# インストール確認
	@if ! command -v claude >/dev/null 2>&1; then \
		echo "❌ Claude Code のインストール確認に失敗しました。PATH を確認してください。"; \
		exit 1; \
	fi

	$(Q_ECHO) "✅ Claude Code のインストールが完了しました"
	$(Q_ECHO) "💡 使い方を確認するには 'make help-claude' を実行してください。"

.PHONY: help-claude
help-claude: ## Claude Code の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/claude.md)

# Opcode (Claude Code GUI) のインストール
.PHONY: install-packages-opcode
install-packages-opcode: ## Opcode (Claude Code GUI) をインストール
	@echo "🖥️  Opcode (Claude Code GUI) のインストールを開始..."
	@if [ -z "$(OPCODE_VERSION)" ]; then echo "❌ 最新バージョンの取得に失敗しました"; exit 1; fi
	@echo "📦 最新バージョン: v$(OPCODE_VERSION)"

	# 既存バージョンの確認
	@CURRENT_VERSION=$$(/opt/opcode/opcode --version 2>/dev/null || echo "none"); \
	if [ "$$CURRENT_VERSION" = "$(OPCODE_VERSION)" ]; then \
		echo "✅ すでに最新バージョン (v$(OPCODE_VERSION)) がインストールされています"; \
	else \
		echo "📥 .deb パッケージをダウンロード中..."; \
		TEMP_DIR=$$(mktemp -d); \
		trap 'rm -rf "$$TEMP_DIR"' EXIT; \
		DEB_URL="https://github.com/winfunc/opcode/releases/download/v$(OPCODE_VERSION)/opcode_$(OPCODE_VERSION)_amd64.deb"; \
		if curl -L -o "$$TEMP_DIR/opcode.deb" "$$DEB_URL"; then \
			echo "🔧 インストール中 (sudo権限が必要です)..."; \
			sudo apt-get update -q && sudo apt-get install -y "$$TEMP_DIR/opcode.deb"; \
			echo "✅ インストール完了"; \
			$(create_desktop_entry); \
		else \
			echo "❌ ダウンロードに失敗しました: $$DEB_URL"; \
			exit 1; \
		fi \
	fi

	@echo "✅ Opcode のインストールが完了しました"
	@echo "💡 使い方を確認するには 'make help-claude' を実行してください。"

# Claude Code エコシステム一括インストール
.PHONY: install-claude-ecosystem
install-claude-ecosystem:
	@echo "🌟 Claude Code エコシステム一括インストールを開始..."
	@echo "ℹ️  以下の2つのツールを順次インストールします:"
	@echo "   1. Claude Code (AI コードエディタ・CLI)"
	@echo "   2. Opcode (Claude Code GUI アプリ)"
	@echo ""

	# Step 1: Claude Code のインストール
	@echo "📋 Step 1/2: Claude Code をインストール中..."
	@$(MAKE) install-packages-claude-code
	@echo "✅ Claude Code のインストールが完了しました"
	@echo ""

	# Step 2: Opcode のインストール
	@echo "📋 Step 2/2: Opcode をインストール中..."
	@$(MAKE) install-packages-opcode
	@echo ""

	# 最終確認
	@echo "🔍 インストール結果の確認中..."
	@if command -v claude >/dev/null 2>&1; then \
		echo "Claude Code: ✅ $$(claude --version 2>/dev/null)"; \
	else \
		echo "Claude Code: ❌ 未確認"; \
	fi

	@echo ""
	@echo "🎉 Claude Code エコシステムのインストールが完了しました！"
	@echo "💡 使い方を確認するには 'make help-claude' を実行してください。"

.PHONY: check-claude
check-claude: ## Claude Code の診断を実行
	@echo "🩺 Claude Code の診断を開始..."
	@if command -v claude >/dev/null 2>&1; then \
		echo "✅ Claude Code: $$(claude --version 2>/dev/null)"; \
	else \
		echo "❌ Claude Code が見つかりません。'make install-packages-claude-code' を実行してください。"; \
	fi
	@if [ -L "$(HOME_DIR)/.claude/CLAUDE.md" ]; then \
		echo "✅ CLAUDE.md: リンク済み ($$(readlink "$(HOME_DIR)/.claude/CLAUDE.md"))"; \
	else \
		echo "❌ CLAUDE.md がリンクされていません。'make setup-claude' を実行してください。"; \
	fi
	@if [ -f "$(HOME_DIR)/.claude/settings.json" ]; then \
		echo "✅ settings.json: 存在します"; \
	else \
		echo "❌ settings.json が見つかりません。'make setup-claude' を実行してください。"; \
	fi

# ========================================
# エイリアス
# ========================================

.PHONY: install-claude-code install-opcode setup-claude uninstall-claude

install-claude-code: install-packages-claude-code  ## Claude Codeをインストール(エイリアス)

install-opcode: install-packages-opcode  ## Opcodeをインストール(エイリアス)

setup-claude: ## Claude Codeの設定を適用
	@echo "📝 Claude Codeの設定を適用中..."
	@mkdir -p "$(HOME_DIR)/.claude"
	@ln -sf "$(REPO_ROOT)/global-rules/AGENTS.global.md" "$(HOME_DIR)/.claude/CLAUDE.md"
	@ln -sf "$(REPO_ROOT)/claude/settings.json" "$(HOME_DIR)/.claude/settings.json"
	@chmod +x "$(REPO_ROOT)/claude/statusline.sh"
	@ln -sf "$(REPO_ROOT)/claude/statusline.sh" "$(HOME_DIR)/.claude/statusline.sh"
	@echo "✅ Claude Codeの設定が完了しました"

uninstall-claude: ## Claude Codeの設定を削除
	@echo "🗑️  Claude Codeの設定を削除中..."
	@if [ -L "$(HOME_DIR)/.claude/CLAUDE.md" ]; then rm -f "$(HOME_DIR)/.claude/CLAUDE.md"; fi
	@if [ -L "$(HOME_DIR)/.claude/settings.json" ]; then rm -f "$(HOME_DIR)/.claude/settings.json"; fi
	@if [ -L "$(HOME_DIR)/.claude/statusline.sh" ]; then rm -f "$(HOME_DIR)/.claude/statusline.sh"; fi
	@echo "✅ Claude Codeの設定を削除しました"
