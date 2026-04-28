# ============================================================
# Claude Code / Claudia セットアップ用Makefile
# Claude Code (CLI)、Claudia (GUI) のインストール・管理を担当
# ============================================================

HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(CURDIR)

define create_desktop_entry
	echo "📝 デスクトップエントリーを作成中..."; \
	printf "[Desktop Entry]\nName=Claudia\nComment=A powerful GUI app and Toolkit for Claude Code\nExec=/opt/claudia/claudia\nTryExec=/opt/claudia/claudia\nIcon=applications-development\nTerminal=false\nType=Application\nCategories=Development;IDE;Utility;\nStartupWMClass=claudia\n" | sudo tee /usr/share/applications/claudia.desktop > /dev/null; \
	sudo chmod +x /usr/share/applications/claudia.desktop; \
	sudo update-desktop-database 2>/dev/null || true
endef

# Claudia (Claude Code GUI) のバージョン固定
CLAUDIA_COMMIT := 70c16d8a4910db48cd9684aeacdd431caefd7d71

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

# Claudia (Claude Code GUI) のインストール
.PHONY: install-packages-claudia
install-packages-claudia:
	@echo "🖥️  Claudia (Claude Code GUI) のインストールを開始..."
	@echo "ℹ️  注意: ClaudiaはまだRelease版が公開されていないため、ソースからビルドします"
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

	# Claudia のクローンとビルド
	@echo "📥 Claudia をクローン中 (Commit: $(CLAUDIA_COMMIT)). GEAR 🚀"
	@CLAUDIA_DIR="/tmp/claudia-build" && \
	rm -rf "$$CLAUDIA_DIR" 2>/dev/null || true && \
	if git clone --depth 1 https://github.com/getAsterisk/claudia.git "$$CLAUDIA_DIR" && \
	   git -C "$$CLAUDIA_DIR" fetch --depth=1 origin $(CLAUDIA_COMMIT) && \
	   git -C "$$CLAUDIA_DIR" checkout $(CLAUDIA_COMMIT); then \
		echo "✅ Claudia のクローンが完了しました"; \
		cd "$$CLAUDIA_DIR" && \
		\
		echo "📦 フロントエンド依存関係をインストール中..."; \
		if command -v bun >/dev/null 2>&1; then \
			bun install; \
		else \
			echo "❌ Bun が見つかりません。新しいターミナルセッションで再実行してください"; \
			exit 1; \
		fi; \
		\
		echo "🔨 Claudia をビルド中..."; \
		echo "ℹ️  この処理には数分かかる場合があります..."; \
		export PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:$$PKG_CONFIG_PATH"; \
		if bun run tauri build; then \
			echo "✅ Claudia のビルドが完了しました"; \
			\
			echo "📁 実行ファイルをインストール中..."; \
			BIN_PATH=""; \
			for candidate in src-tauri/target/release/claudia* src-tauri/target/release/opcode*; do \
				if [ -f "$$candidate" ] && [ -x "$$candidate" ]; then \
					case "$$(basename "$$candidate")" in \
						claudia*|opcode*) \
							BIN_PATH="$$candidate"; \
							break ;; \
					esac; \
				fi; \
			done; \
			if [ -n "$$BIN_PATH" ] && [ -f "$$BIN_PATH" ] && [ -x "$$BIN_PATH" ]; then \
				echo "✅ 選択された実行ファイル: $$BIN_PATH"; \
				sudo mkdir -p /opt/claudia; \
				sudo cp "$$BIN_PATH" /opt/claudia/claudia; \
				sudo chmod +x /opt/claudia/claudia; \
				\
				$(create_desktop_entry); \
				\
				echo "✅ Claudia が /opt/claudia にインストールされました"; \
			else \
				echo "⚠️  主要バイナリが見つかりません。代替候補を検索中..."; \
				ALT_BIN=""; \
				for alt_candidate in $$(find src-tauri/target/release -maxdepth 1 -type f -executable -name "claudia*" -o -name "opcode*" 2>/dev/null | sort -V); do \
					case "$$(basename "$$alt_candidate")" in \
						claudia*|opcode*) \
							ALT_BIN="$$alt_candidate"; \
							break ;; \
					esac; \
				done; \
				if [ -n "$$ALT_BIN" ] && [ -f "$$ALT_BIN" ] && [ -x "$$ALT_BIN" ]; then \
					echo "✅ 代替実行ファイルを発見: $$ALT_BIN"; \
					sudo mkdir -p /opt/claudia; \
					sudo cp "$$ALT_BIN" /opt/claudia/claudia; \
					sudo chmod +x /opt/claudia/claudia; \
					$(create_desktop_entry); \
					echo "✅ Claudia が /opt/claudia にインストールされました（代替実行ファイル使用）"; \
				else \
					echo "❌ ビルドされた実行ファイルが見つかりません"; \
					exit 1; \
				fi; \
			fi; \
		else \
			echo "❌ Claudia のビルドに失敗しました"; \
			echo "🔧 トラブルシューティング:"; \
			echo "1. 依存関係の確認: すべてのシステム依存関係がインストールされているか"; \
			echo "2. メモリ不足: ビルドには十分なRAMが必要"; \
			echo "3. 手動ビルド: cd /tmp/claudia-build && bun run tauri build --debug"; \
			exit 1; \
		fi; \
	else \
		echo "❌ Claudia のクローンに失敗しました"; \
		echo "ℹ️  インターネット接続を確認してください"; \
		exit 1; \
	fi

	# クリーンアップ
	@echo "🧹 一時ファイルをクリーンアップ中..."
	@rm -rf /tmp/claudia-build 2>/dev/null || true

	@echo "✅ Claudia のインストールが完了しました"
	@echo "💡 使い方を確認するには 'make help-claude' を実行してください。"

# Claude Code エコシステム一括インストール
.PHONY: install-claude-ecosystem
install-claude-ecosystem:
	@echo "🌟 Claude Code エコシステム一括インストールを開始..."
	@echo "ℹ️  以下の2つのツールを順次インストールします:"
	@echo "   1. Claude Code (AI コードエディタ・CLI)"
	@echo "   2. Claudia (Claude Code GUI アプリ)"
	@echo ""

	# Step 1: Claude Code のインストール
	@echo "📋 Step 1/2: Claude Code をインストール中..."
	@$(MAKE) install-packages-claude-code
	@echo "✅ Claude Code のインストールが完了しました"
	@echo ""

	# Step 2: Claudia のインストール
	@echo "📋 Step 2/2: Claudia をインストール中..."
	@$(MAKE) install-packages-claudia
	@echo "✅ Claudia のインストールが完了しました"
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

# ========================================
# エイリアス
# ========================================

.PHONY: install-claude-code install-claudia setup-claude uninstall-claude

install-claude-code: install-packages-claude-code  ## Claude Codeをインストール(エイリアス)

install-claudia: install-packages-claudia  ## Claudiaをインストール(エイリアス)

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
