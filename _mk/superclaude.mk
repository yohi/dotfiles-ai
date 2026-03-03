# SuperClaude Framework for Claude Code セットアップ用Makefile
# Claude Code向けのSuperClaudeフレームワークのインストールと設定を管理

# SuperClaude フレームワークファイルのリスト
SUPERCLAUDE_MODES := MODE_Brainstorming.md MODE_Business_Panel.md MODE_Introspection.md \
                     MODE_Orchestration.md MODE_Task_Management.md MODE_Token_Efficiency.md

SUPERCLAUDE_MCP := MCP_Context7.md MCP_Magic.md MCP_Morphllm.md \
                   MCP_Playwright.md MCP_Sequential.md MCP_Serena.md

SUPERCLAUDE_CORE := BUSINESS_PANEL_EXAMPLES.md BUSINESS_SYMBOLS.md FLAGS.md \
                    PRINCIPLES.md RULES.md

SUPERCLAUDE_ALL_FILES := $(SUPERCLAUDE_MODES) $(SUPERCLAUDE_MCP) $(SUPERCLAUDE_CORE)

# インストール先ディレクトリ
CLAUDE_DIR := $(HOME)/.claude
DOTFILES_CLAUDE_DIR := $(CURDIR)/claude

.PHONY: check-superclaude
check-superclaude: ## SuperClaudeフレームワークのインストール状態を確認
	@echo "🔍 SuperClaude Framework のインストール状態を確認中..."
	@echo ""
	@if [ -d "$(CLAUDE_DIR)" ]; then \
		echo "✅ Claude設定ディレクトリが存在します: $(CLAUDE_DIR)"; \
		echo ""; \
		echo "📋 インストール済みSuperClaudeファイル:"; \
		for file in $(SUPERCLAUDE_ALL_FILES); do \
			if [ -f "$(CLAUDE_DIR)/$$file" ]; then \
				echo "  ✅ $$file"; \
			else \
				echo "  ❌ $$file (未インストール)"; \
			fi; \
		done; \
		echo ""; \
		if [ -L "$(CLAUDE_DIR)/CLAUDE.md" ]; then \
			echo "✅ CLAUDE.md: シンボリックリンク → $$(readlink $(CLAUDE_DIR)/CLAUDE.md)"; \
		elif [ -f "$(CLAUDE_DIR)/CLAUDE.md" ]; then \
			echo "⚠️  CLAUDE.md: 通常ファイル (シンボリックリンク推奨)"; \
		else \
			echo "❌ CLAUDE.md: 未設定"; \
		fi; \
		if [ -L "$(CLAUDE_DIR)/settings.json" ]; then \
			echo "✅ settings.json: シンボリックリンク → $$(readlink $(CLAUDE_DIR)/settings.json)"; \
		fi; \
		if [ -L "$(CLAUDE_DIR)/claude-settings.json" ]; then \
			echo "✅ claude-settings.json: シンボリックリンク → $$(readlink $(CLAUDE_DIR)/claude-settings.json)"; \
		fi; \
	else \
		echo "❌ Claude設定ディレクトリが存在しません: $(CLAUDE_DIR)"; \
		echo "ℹ️  'make install-packages-superclaude' を実行してください"; \
	fi

.PHONY: install-packages-superclaude
install-packages-superclaude: ## SuperClaudeフレームワークをClaude Code向けにインストール
	@BOOL_LINK_CHECK=0; if [ -L "$(CLAUDE_DIR)/CLAUDE.md" ]; then BOOL_LINK_CHECK=1; fi; \
	BOOL_SETTINGS_LINK=0; if [ -L "$(CLAUDE_DIR)/settings.json" ] && [ -L "$(CLAUDE_DIR)/claude-settings.json" ]; then BOOL_SETTINGS_LINK=1; fi; \
	BOOL_SUPERCLAUDE_CMD=0; if command -v SuperClaude >/dev/null 2>&1; then BOOL_SUPERCLAUDE_CMD=1; fi; \
	BOOL_REQUIRED_FILES=0; if [ -f "$(CLAUDE_DIR)/MODE_Brainstorming.md" ] && [ -f "$(CLAUDE_DIR)/PRINCIPLES.md" ]; then BOOL_REQUIRED_FILES=1; fi; \
	if [ "$$BOOL_LINK_CHECK" = "1" ] && [ "$$BOOL_SETTINGS_LINK" = "1" ] && [ "$$BOOL_SUPERCLAUDE_CMD" = "1" ] && [ "$$BOOL_REQUIRED_FILES" = "1" ]; then \
		echo "$(call IDEMPOTENCY_SKIP_MSG,install-packages-superclaude)"; \
		exit 0; \
	fi
	@echo "🚀 SuperClaude Framework for Claude Code のインストールを開始..."
	@echo ""
	@# Claude Codeの確認
	@if ! command -v claude >/dev/null 2>&1; then \
		echo "❌ Claude Code がインストールされていません"; \
		echo "ℹ️  先にClaude Codeをインストールしてください"; \
		exit 1; \
	fi
	@echo "✅ Claude Code が見つかりました: $$(claude --version)"
	@echo ""
	@# Python/uvの確認(SuperClaudeツール用)
	@if ! command -v python3 >/dev/null 2>&1; then \
		echo "⚠️  Python3 が見つかりません"; \
		echo "   SuperClaudeツールを使用する場合はPython3が必要です"; \
	else \
		echo "✅ Python3 が見つかりました: $$(python3 --version)"; \
	fi
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "⚠️  uv が見つかりません"; \
		echo "   SuperClaudeツールを使用する場合はuvが必要です"; \
		echo "   'make install-packages-uv' でインストールできます"; \
	else \
		echo "✅ uv が見つかりました: $$(uv --version)"; \
	fi
	@echo ""
	@# Claude設定ディレクトリの作成
	@mkdir -p $(CLAUDE_DIR)
	@echo "📁 Claude設定ディレクトリを準備しました: $(CLAUDE_DIR)"
	@echo ""
	@# SuperClaudeフレームワークファイルの確認
	@echo "📦 SuperClaudeフレームワークファイルを確認中..."
	@MISSING_FILES=0; \
	for file in $(SUPERCLAUDE_ALL_FILES); do \
		if [ ! -f "$(CLAUDE_DIR)/$$file" ]; then \
			echo "⚠️  $$file が見つかりません"; \
			MISSING_FILES=$$((MISSING_FILES + 1)); \
		fi; \
	done; \
	if [ $$MISSING_FILES -gt 0 ]; then \
		echo ""; \
		echo "⚠️  $$MISSING_FILES 個のフレームワークファイルが見つかりません"; \
		echo "   SuperClaudeツールをインストールすると自動的に追加されます"; \
	else \
		echo "✅ すべてのフレームワークファイルが存在します"; \
	fi
	@# SuperClaudeツールのインストール(オプション)
	@echo ""
	@echo "🔧 SuperClaudeツールのインストール(オプション)..."
	@if command -v uv >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then \
		if command -v SuperClaude >/dev/null 2>&1; then \
			echo "✅ SuperClaudeツールは既にインストールされています"; \
			CURRENT_VERSION=$$(SuperClaude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?' || echo "不明"); \
			echo "   バージョン: $$CURRENT_VERSION"; \
		else \
			echo "📥 SuperClaudeツールをインストール中..."; \
			if [ -x "$(CURDIR)/scripts/install_superclaude.sh" ]; then \
				bash $(CURDIR)/scripts/install_superclaude.sh || echo "⚠️  インストールに失敗しましたが続行します"; \
			else \
				echo "⚠️  skipping... (scripts/install_superclaude.shが見つかりません)"; \
			fi; \
		fi; \
	else \
		echo "⚠️  Python3またはuvが見つからないため、SuperClaudeツールのインストールをスキップします"; \
	fi
	@echo ""
	@echo "🔗 CLAUDE.md シンボリックリンクを設定中..."
	@if [ -L "$(CLAUDE_DIR)/CLAUDE.md" ]; then \
		rm -f "$(CLAUDE_DIR)/CLAUDE.md"; \
	elif [ -f "$(CLAUDE_DIR)/CLAUDE.md" ]; then \
		mv "$(CLAUDE_DIR)/CLAUDE.md" "$(CLAUDE_DIR)/CLAUDE.md.backup.$$(date +%Y%m%d_%H%M%S)"; \
		echo "📋 既存のCLAUDE.mdをバックアップしました"; \
	fi
	@ln -sf "$(DOTFILES_CLAUDE_DIR)/CLAUDE.md" "$(CLAUDE_DIR)/CLAUDE.md"
	@echo "✅ CLAUDE.md → $(DOTFILES_CLAUDE_DIR)/CLAUDE.md"
	@echo ""
	@echo "🔗 claude-settings.json シンボリックリンクを設定中..."
	@if [ -L "$(CLAUDE_DIR)/settings.json" ]; then \
		rm -f "$(CLAUDE_DIR)/settings.json"; \
	elif [ -f "$(CLAUDE_DIR)/settings.json" ]; then \
		mv "$(CLAUDE_DIR)/settings.json" "$(CLAUDE_DIR)/settings.json.backup.$$(date +%Y%m%d_%H%M%S)"; \
		echo "📋 既存の settings.json をバックアップしました"; \
	fi
	@ln -sf "$(DOTFILES_CLAUDE_DIR)/claude-settings.json" "$(CLAUDE_DIR)/settings.json"
	@ln -sf "$(DOTFILES_CLAUDE_DIR)/claude-settings.json" "$(CLAUDE_DIR)/claude-settings.json"
	@echo "✅ settings.json → $(DOTFILES_CLAUDE_DIR)/claude-settings.json"
	@echo ""
	@$(MAKE) check-superclaude

	@echo ""
	@echo "🎉 SuperClaude Framework のインストールが完了しました！"
	@echo ""
	@echo "📚 使い方:"
	@echo "   Claude Codeを起動すると、SuperClaudeフレームワークが自動的に読み込まれます"
	@echo "   ~/.claude/CLAUDE.md に記載されているモードやMCPドキュメントが利用可能です"

.PHONY: uninstall-superclaude
uninstall-superclaude: ## SuperClaudeフレームワークをアンインストール
	@echo "🗑️  SuperClaude Framework のアンインストールを開始..."
	@echo ""
	@if [ ! -d "$(CLAUDE_DIR)" ]; then \
		echo "ℹ️  Claude設定ディレクトリが存在しません"; \
		exit 0; \
	fi
	@echo "📋 以下のファイルを削除します:"
	@for file in $(SUPERCLAUDE_ALL_FILES); do \
		if [ -f "$(CLAUDE_DIR)/$$file" ]; then \
			echo "  - $$file"; \
		fi; \
	done
	@if [ -L "$(CLAUDE_DIR)/CLAUDE.md" ]; then \
		echo "  - CLAUDE.md (シンボリックリンク)"; \
	fi
	@if [ -L "$(CLAUDE_DIR)/settings.json" ]; then \
		echo "  - settings.json (シンボリックリンク)"; \
	fi
	@if [ -L "$(CLAUDE_DIR)/claude-settings.json" ]; then \
		echo "  - claude-settings.json (シンボリックリンク)"; \
	fi
	@echo ""
	@printf "本当にアンインストールしますか? [y/N]: "; read confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		for file in $(SUPERCLAUDE_ALL_FILES); do \
			rm -f "$(CLAUDE_DIR)/$$file"; \
		done; \
		rm -f "$(CLAUDE_DIR)/CLAUDE.md"; \
		rm -f "$(CLAUDE_DIR)/settings.json"; \
		rm -f "$(CLAUDE_DIR)/claude-settings.json"; \
		if command -v SuperClaude >/dev/null 2>&1; then \
			echo ""; \
			echo "🔧 SuperClaudeツールもアンインストールしますか?"; \
			printf "SuperClaudeツールをアンインストール? [y/N]: "; read confirm_tool; \
			if [ "$$confirm_tool" = "y" ] || [ "$$confirm_tool" = "Y" ]; then \
				if command -v uv >/dev/null 2>&1; then \
					uv tool uninstall SuperClaude 2>/dev/null || python3 -m pip uninstall -y SuperClaude; \
					echo "✅ SuperClaudeツールをアンインストールしました"; \
				fi; \
			fi; \
		fi; \
		echo ""; \
		echo "✅ SuperClaude Framework のアンインストールが完了しました"; \
	else \
		echo "❌ アンインストールをキャンセルしました"; \
	fi

.PHONY: update-superclaude
update-superclaude: ## SuperClaudeフレームワークを最新版に更新
	@echo "🔄 SuperClaude Framework を更新中..."
	@echo ""
	@# フレームワークファイルの更新確認
	@echo "📦 フレームワークファイルを確認中..."
	@echo "   (フレームワークファイルはSuperClaudeツールによって管理されます)"
	@# SuperClaudeツールの更新
	@if command -v SuperClaude >/dev/null 2>&1; then \
		echo ""; \
		echo "🔧 SuperClaudeツールを更新中..."; \
		if command -v uv >/dev/null 2>&1; then \
			uv tool upgrade SuperClaude 2>/dev/null || python3 -m pip install --upgrade SuperClaude; \
		else \
			python3 -m pip install --upgrade SuperClaude; \
		fi; \
		echo "✅ SuperClaudeツールを更新しました: $$(SuperClaude --version)"; \
	fi
	@echo ""
	@echo "✅ SuperClaude Framework の更新が完了しました！"

.PHONY: info-superclaude
info-superclaude: ## SuperClaudeフレームワークの情報を表示
	@echo "ℹ️  SuperClaude Framework for Claude Code"
	@echo ""
	@echo "📖 概要:"
	@echo "   Claude Code向けのSuperClaudeフレームワークは、AIとの対話を強化する"
	@echo "   複数のモード、MCP統合、ビジネスパネルなどを提供します"
	@echo ""
	@echo "📂 コンポーネント:"
	@echo "   【Behavioral Modes】"
	@for file in $(SUPERCLAUDE_MODES); do \
		echo "     - $$file"; \
	done
	@echo ""
	@echo "   【MCP Documentation】"
	@for file in $(SUPERCLAUDE_MCP); do \
		echo "     - $$file"; \
	done
	@echo ""
	@echo "   【Core Framework】"
	@for file in $(SUPERCLAUDE_CORE); do \
		echo "     - $$file"; \
	done
	@echo ""
	@echo "🔧 コマンド:"
	@echo "   make install-packages-superclaude - フレームワークをインストール"
	@echo "   make check-superclaude       - インストール状態を確認"
	@echo "   make update-superclaude      - 最新版に更新"
	@echo "   make uninstall-superclaude   - アンインストール"
	@echo "   make info-superclaude        - この情報を表示"
	@echo ""
	@echo "📚 ドキュメント:"
	@echo "   設定ファイル: ~/.claude/CLAUDE.md"
	@echo "   ソースコード: $(DOTFILES_CLAUDE_DIR)/"

# ========================================
# エイリアス
# ========================================

.PHONY: install-superclaude
install-superclaude: install-packages-superclaude  ## SuperClaudeフレームワークをインストール(メインターゲット)

.PHONY: claudecode
claudecode: install-packages-superclaude  ## Claude Code用のSuperClaudeフレームワークをインストール(エイリアス)
