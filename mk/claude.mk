# ============================================================
# Claude Code / Claudia セットアップ用Makefile
# Claude Code (CLI)、Claudia (GUI) のインストール・管理を担当
# ============================================================

# Claudia (Claude Code GUI) のバージョン固定
CLAUDIA_COMMIT := 70c16d8a4910db48cd9684aeacdd431caefd7d71

# Claude Code のインストール
install-packages-claude-code:
	@echo "🤖 Claude Code のインストールを開始..."

	# Node.jsの確認
	@$(MAKE) check-nodejs

	# npmの確認
	@echo "🔍 npm の確認中..."
	@if ! command -v npm >/dev/null 2>&1; then \
		echo "❌ npm がインストールされていません"; \
		echo "ℹ️  通常はNode.jsと一緒にインストールされます"; \
		exit 1; \
	else \
		echo "✅ npm が見つかりました (バージョン: $$(npm --version))"; \
	fi

	# Claude Code のインストール確認
	@echo "🔍 既存の Claude Code インストールを確認中..."
	@if command -v claude >/dev/null 2>&1; then \
		echo "✅ Claude Code は既にインストールされています"; \
		echo "   バージョン: $$(claude --version 2>/dev/null || echo '取得できませんでした')"; \
		echo ""; \
		echo "🔄 アップデートを確認中..."; \
		npm update -g @anthropic-ai/claude-code 2>/dev/null || true; \
	else \
		echo "📦 Claude Code をインストール中..."; \
		echo "ℹ️  グローバルインストールを実行します: npm install -g @anthropic-ai/claude-code"; \
		\
		if npm install -g @anthropic-ai/claude-code; then \
			echo "✅ Claude Code のインストールが完了しました"; \
		else \
			echo "❌ Claude Code のインストールに失敗しました"; \
			echo ""; \
			echo "🔧 トラブルシューティング:"; \
			echo "1. 権限の問題: npm config set prefix $(HOME)/.local"; \
			echo "2. WSLの場合: npm config set os linux"; \
			echo "3. 強制インストール: npm install -g @anthropic-ai/claude-code --force"; \
			echo ""; \
			exit 1; \
		fi; \
	fi

	# インストール確認
	@echo "🔍 インストールの確認中..."
	@if command -v claude >/dev/null 2>&1; then \
		echo "✅ Claude Code が正常にインストールされました"; \
		echo "   実行ファイル: $$(which claude)"; \
		echo "   バージョン: $$(claude --version 2>/dev/null || echo '取得できませんでした')"; \
	else \
		echo "❌ Claude Code のインストール確認に失敗しました"; \
		echo "ℹ️  PATH の問題の可能性があります"; \
		echo "   手動確認: which claude"; \
		exit 1; \
	fi

	@echo ""
	@echo "🎉 Claude Code のセットアップガイド:"
	@echo "1. プロジェクトディレクトリに移動: cd your-project-directory"
	@echo "2. Claude Code を開始: claude"
	@echo "3. 認証方法を選択:"
	@echo "   - Anthropic Console (デフォルト)"
	@echo "   - Claude App (ProまたはMaxプラン)"
	@echo "   - エンタープライズプラットフォーム"
	@echo "4. 初回セットアップコマンド:"
	@echo "   > summarize this project"
	@echo "   > /init"
	@echo ""
	@echo "📚 詳細なドキュメント: https://docs.anthropic.com/claude-code"
	@echo "✅ Claude Code のインストールが完了しました"

# Claudia (Claude Code GUI) のインストール
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
		export PATH="$$HOME/.bun/bin:$$PATH"; \
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
	@echo "📥 Claudia をクローン中 (Commit: $(CLAUDIA_COMMIT))..."
	@CLAUDIA_DIR="/tmp/claudia-build" && \
	rm -rf "$$CLAUDIA_DIR" 2>/dev/null || true && \
	if git clone --depth 1 https://github.com/getAsterisk/claudia.git "$$CLAUDIA_DIR" && \
	   git -C "$$CLAUDIA_DIR" fetch --depth=1 origin $(CLAUDIA_COMMIT) && \
	   git -C "$$CLAUDIA_DIR" checkout $(CLAUDIA_COMMIT); then \
		echo "✅ Claudia のクローンが完了しました"; \
		cd "$$CLAUDIA_DIR" && \
		\
		echo "📦 フロントエンド依存関係をインストール中..."; \
		export PATH="$$HOME/.bun/bin:$$PATH"; \
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
				echo "📝 デスクトップエントリーを作成中..."; \
				echo "[Desktop Entry]" | sudo tee /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Name=Claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Comment=A powerful GUI app and Toolkit for Claude Code" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Exec=/opt/claudia/claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "TryExec=/opt/claudia/claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Icon=applications-development" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Terminal=false" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Type=Application" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "Categories=Development;IDE;Utility;" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				echo "StartupWMClass=claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
				sudo chmod +x /usr/share/applications/claudia.desktop; \
				sudo update-desktop-database 2>/dev/null || true; \
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
					echo "📝 デスクトップエントリーを作成中..."; \
					echo "[Desktop Entry]" | sudo tee /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Name=Claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Comment=A powerful GUI app and Toolkit for Claude Code" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Exec=/opt/claudia/claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "TryExec=/opt/claudia/claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Icon=applications-development" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Terminal=false" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Type=Application" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "Categories=Development;IDE;Utility;" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					echo "StartupWMClass=claudia" | sudo tee -a /usr/share/applications/claudia.desktop > /dev/null; \
					sudo chmod +x /usr/share/applications/claudia.desktop; \
					sudo update-desktop-database 2>/dev/null || true; \
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

	@echo ""
	@echo "🎉 Claudia のセットアップが完了しました！"
	@echo ""
	@echo "🚀 使用方法:"
	@echo "1. アプリケーションメニューから 'Claudia' を起動"
	@echo "2. または、ターミナルから: /opt/claudia/claudia"
	@echo "3. 初回起動時にClaude Codeディレクトリ（~/.claude）が自動検出されます"
	@echo ""
	@echo "✨ Claudia の主要機能:"
	@echo "- 📁 プロジェクト & セッション管理（~/.claude/projects/）"
	@echo "- 🤖 カスタムAIエージェント作成・実行"
	@echo "- 📊 使用状況分析ダッシュボード（コスト・トークン追跡）"
	@echo "- 🔌 MCP サーバー管理（Model Context Protocol）"
	@echo "- ⏰ タイムライン & チェックポイント（セッション履歴）"
	@echo "- 📝 CLAUDE.md ファイル管理・編集"
	@echo ""
	@echo "📚 詳細なドキュメント: https://github.com/getAsterisk/claudia"
	@echo "🔗 公式サイト: https://claudiacode.com"
	@echo ""
	@echo "💡 次のステップ:"
	@echo "- Claude Code でプロジェクトを作成してから Claudia で管理"
	@echo "- カスタムエージェントを作成して開発タスクを自動化"
	@echo "✅ Claudia のインストールが完了しました"

# Claude Code エコシステム一括インストール
install-claude-ecosystem:
	@echo "🌟 Claude Code エコシステム一括インストールを開始..."
	@echo "ℹ️  以下の3つのツールを順次インストールします:"
	@echo "   1. Claude Code (AI コードエディタ・CLI)"
	@echo "   2. SuperClaude (Claude Code フレームワーク)"
	@echo "   3. Claudia (Claude Code GUI アプリ)"
	@echo ""

	# Step 1: Claude Code のインストール
	@echo "📋 Step 1/3: Claude Code をインストール中..."
	@$(MAKE) install-packages-claude-code
	@echo "✅ Claude Code のインストールが完了しました"
	@echo ""

	# Step 2: SuperClaude のインストール
	@echo "📋 Step 2/3: SuperClaude をインストール中..."
	@if [ "$${SKIP_SUPERCLAUDE:-0}" = "1" ]; then \
		echo "⚠️  SuperClaude のインストールはスキップされています (SKIP_SUPERCLAUDE=1)"; \
		echo "   手動インストール例: make install-superclaude"; \
		echo "   有効化方法: SKIP_SUPERCLAUDE=0 make install-claude-ecosystem"; \
	else \
		echo "📦 SuperClaude をインストール中..."; \
		$(MAKE) install-packages-superclaude || (echo "❌ SuperClaude インストールに失敗しました"; exit 1); \
		echo "✅ SuperClaude のインストールが完了しました"; \
	fi
	@echo ""

	# Step 3: Claudia のインストール
	@echo "📋 Step 3/3: Claudia をインストール中..."
	@$(MAKE) install-packages-claudia
	@echo "✅ Claudia のインストールが完了しました"
	@echo ""

	# 最終確認
	@echo "🔍 インストール結果の確認中..."
	@export PATH="$$HOME/.local/bin:$$PATH"; \
	if command -v claude >/dev/null 2>&1; then \
		echo "Claude Code: ✅ $$(claude --version 2>/dev/null)"; \
	else \
		echo "Claude Code: ❌ 未確認"; \
	fi; \
	if command -v SuperClaude >/dev/null 2>&1; then \
		echo "SuperClaude: ✅ $$(SuperClaude --version 2>/dev/null)"; \
	else \
		echo "SuperClaude: ❌ 未確認"; \
	fi

	@echo ""
	@echo "🎉 Claude Code エコシステムのインストールが完了しました！"
	@echo ""
	@echo "🚀 使用開始ガイド:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "💻 Claude Code (CLI):"
	@echo "  コマンド: claude"
	@echo "  使用例: プロジェクトディレクトリで 'claude' を実行"
	@echo ""
	@echo "🚀 SuperClaude (フレームワーク):"
	@echo "  Claude Code内で以下のコマンドが利用可能:"
	@echo "    /sc:implement <機能>     - 機能実装"
	@echo "    /sc:design <UI>          - UI/UXデザイン"
	@echo "    /sc:analyze <コード>     - コード分析"
	@echo "    /sc:test <テスト>        - テストスイート"
	@echo "    /sc:improve <コード>     - コード改善"
	@echo ""
	@echo "🖥️  Claudia (GUI):"
	@echo "  起動方法: アプリケーションメニューから 'Claudia' を選択"
	@echo "  または: /opt/claudia/claudia"
	@echo "  機能: プロジェクト管理、使用状況分析、MCPサーバー管理等"
	@echo ""
	@echo "🎭 利用可能なペルソナ (SuperClaude):"
	@echo "  🏗️  architect - システム設計"
	@echo "  🎨 frontend  - UI/UX開発"
	@echo "  ⚙️  backend   - API/インフラ"
	@echo "  🔍 analyzer  - デバッグ・分析"
	@echo "  🛡️  security  - セキュリティ"
	@echo "  ✍️  scribe    - ドキュメント"
	@echo ""
	@echo "📚 ドキュメント:"
	@echo "  Claude Code: https://docs.anthropic.com/claude-code"
	@echo "  SuperClaude: https://superclaude-org.github.io/"
	@echo "  Claudia: https://github.com/getAsterisk/claudia"
	@echo ""
	@echo "✨ おすすめワークフロー:"
	@echo "  1. 'claude' でプロジェクトを開始"
	@echo "  2. '/sc:implement' で機能を実装"
	@echo "  3. Claudia でプロジェクト管理・分析"
	@echo ""
	@echo "✅ Claude Code エコシステムの一括インストールが完了しました"

# ========================================
# エイリアス
# ========================================

.PHONY: install-claude-code
install-claude-code: install-packages-claude-code  ## Claude Codeをインストール(エイリアス)

.PHONY: install-claudia
install-claudia: install-packages-claudia  ## Claudiaをインストール(エイリアス)
