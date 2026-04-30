# ============================================================
# Claude Code / Opcode セットアップ用Makefile
# Claude Code (CLI)、Opcode (GUI) のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)

define create_desktop_entry
	echo "📝 デスクトップエントリーを作成中..."; \
	printf "[Desktop Entry]\nName=Opcode\nComment=A powerful GUI app and Toolkit for Claude Code\nExec=/opt/opcode/opcode\nTryExec=/opt/opcode/opcode\nIcon=applications-development\nTerminal=false\nType=Application\nCategories=Development;IDE;Utility;\nStartupWMClass=opcode\n" | sudo tee /usr/share/applications/opcode.desktop > /dev/null; \
	sudo chmod +x /usr/share/applications/opcode.desktop; \
	sudo update-desktop-database 2>/dev/null || true
endef

# Opcode (Claude Code GUI) のバージョン固定
OPCODE_COMMIT := 70c16d8a4910db48cd9684aeacdd431caefd7d71

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
	@echo "ℹ️  注意: OpcodeはまだRelease版が公開されていないため、ソースからビルドします"
	@echo "⏱️  ビルドには10-15分かかる場合があります（システム環境により変動）"
	@echo ""

	# Claude Code の確認
	@echo "🔍 Claude Code の確認中..."
	@if ! command -v claude >/dev/null 2>&1; then \
		echo "❌ Claude Code がインストールされていません"; \
		echo "ℹ️  先に 'make install-packages-claude-code' を実行してください"; \
		exit 1; \
	else \
		echo "✅ Claude Code が見つかりました: $$(claude --version 2>/dev/null)"; \
	fi

	# Rust の確認 (Homebrew版を使用)
	@echo "🔍 Rust の確認中..."
	@if ! command -v rustc >/dev/null 2>&1; then \
		echo "❌ Rust がインストールされていません"; \
		echo "📥 Homebrewでインストールしてください: brew install rust"; \
		echo "💡 または公式のrustupでインストール: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"; \
		exit 1; \
	else \
		RUST_VERSION=$$(rustc --version | grep -o '[0-9]\+\.[0-9]\+' | head -1); \
		echo "✅ Rust が見つかりました: $$(rustc --version)"; \
		MAJOR=$$(echo "$$RUST_VERSION" | cut -d'.' -f1); \
		MINOR=$$(echo "$$RUST_VERSION" | cut -d'.' -f2); \
		if [ "$$MAJOR" -lt 1 ] || { [ "$$MAJOR" -eq 1 ] && [ "$$MINOR" -lt 70 ]; }; then \
			echo "⚠️  Rust 1.70.0+ が推奨されています (現在: $$RUST_VERSION)"; \
			echo "💡 アップデート: rustup update または brew upgrade rust"; \
		fi; \
	fi

	# システム依存関係のインストール (Linux)
	@echo "📦 システム依存関係をインストール中..."
	@if command -v apt-get >/dev/null 2>&1; then \
		echo "🔧 Linux向けの依存関係をインストール中..."; \
		sudo apt update -q 2>/dev/null || echo "⚠️  パッケージリストの更新で問題が発生しましたが、処理を続行します"; \
		sudo DEBIAN_FRONTEND=noninteractive apt install -y \
			libwebkit2gtk-4.1-dev \
			libgtk-3-dev \
			libayatana-appindicator3-dev \
			librsvg2-dev \
			patchelf \
			build-essential \
			curl \
			wget \
			file \
			libssl-dev \
			libxdo-dev \
			libsoup-3.0-dev \
			libjavascriptcoregtk-4.1-dev || \
		echo "⚠️  一部の依存関係のインストールに失敗しましたが、処理を続行します"; \
	else \
		echo "ℹ️  Linuxではないため、システム依存関係のインストールをスキップします"; \
	fi

	# Bun のインストール
	@echo "🔍 Bun の確認中..."
	@if ! command -v bun >/dev/null 2>&1; then \
		echo "📦 Bun をインストール中..."; \
		curl -fsSL https://bun.sh/install | bash; \
		echo "🔄 Bunのパスを更新中..."; \
		if ! command -v bun >/dev/null 2>&1; then \
			echo "⚠️  Bunのインストールが完了しましたが、現在のセッションで認識されていません"; \
			echo "   新しいターミナルセッションで再実行するか、以下を実行してください:"; \
			echo "   source $$HOME/.bashrc"; \
			echo "   source $$HOME/.zshrc (zshの場合)"; \
		fi; \
	else \
		echo "✅ Bun が見つかりました: $$(bun --version)"; \
	fi

	# Opcode のクローンとビルド
	@echo "📥 Opcode をクローン中 (Commit: $(OPCODE_COMMIT)). GEAR 🚀"
	@OPCODE_DIR="/tmp/opcode-build" && \
	rm -rf "$$OPCODE_DIR" 2>/dev/null || true && \
	if git clone --depth 1 https://github.com/winfunc/opcode.git "$$OPCODE_DIR" && \
	   git -C "$$OPCODE_DIR" fetch --depth=1 origin $(OPCODE_COMMIT) && \
	   git -C "$$OPCODE_DIR" checkout $(OPCODE_COMMIT); then \
		echo "✅ Opcode のクローンが完了しました"; \
		cd "$$OPCODE_DIR" && \
		\
		echo "📦 フロントエンド依存関係をインストール中..."; \
		if command -v bun >/dev/null 2>&1; then \
			bun install; \
		else \
			echo "❌ Bun が見つかりません。新しいターミナルセッションで再実行してください"; \
			exit 1; \
		fi; \
		\
		echo "🔨 Opcode をビルド中..."; \
		echo "ℹ️  この処理には数分かかる場合があります..."; \
		export PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:$$PKG_CONFIG_PATH"; \
		if bun run tauri build; then \
			echo "✅ Opcode のビルドが完了しました"; \
			\
			echo "📁 実行ファイルをインストール中..."; \
			BIN_PATH=""; \
			for candidate in src-tauri/target/release/opcode*; do \
				if [ -f "$$candidate" ] && [ -x "$$candidate" ]; then \
					BIN_PATH="$$candidate"; \
					break; \
				fi; \
			done; \
			if [ -n "$$BIN_PATH" ] && [ -f "$$BIN_PATH" ] && [ -x "$$BIN_PATH" ]; then \
				echo "✅ 選択された実行ファイル: $$BIN_PATH"; \
				sudo mkdir -p /opt/opcode; \
				sudo cp "$$BIN_PATH" /opt/opcode/opcode; \
				sudo chmod +x /opt/opcode/opcode; \
				\
				$(create_desktop_entry); \
				\
				echo "✅ Opcode が /opt/opcode にインストールされました"; \
			else \
				echo "❌ ビルドされた実行ファイルが見つかりません"; \
				exit 1; \
			fi; \
		else \
			echo "❌ Opcode のビルドに失敗しました"; \
			echo "🔧 トラブルシューティング:"; \
			echo "1. 依存関係の確認: すべてのシステム依存関係がインストールされているか"; \
			echo "2. メモリ不足: ビルドには十分なRAMが必要"; \
			echo "3. 手動ビルド: cd /tmp/opcode-build && bun run tauri build --debug"; \
			exit 1; \
		fi; \
	else \
		echo "❌ Opcode のクローンに失敗しました"; \
		echo "ℹ️  インターネット接続を確認してください"; \
		exit 1; \
	fi

	# クリーンアップ
	@echo "🧹 一時ファイルをクリーンアップ中..."
	@rm -rf /tmp/opcode-build 2>/dev/null || true

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
