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
install-packages-claude-code: ## Claude Code CLI のインストール / アップデート
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
	@if [ -z "$(OPCODE_VERSION)" ] || [ "$(OPCODE_VERSION)" = "FAILED" ]; then \
		echo "❌ 最新バージョンの取得に失敗しました。ネットワーク接続や GitHub API の制限を確認してください。"; \
		exit 1; \
	fi
	@if [[ ! "$(OPCODE_VERSION)" =~ ^[0-9]+(\.[0-9]+)*$$ ]]; then \
		echo "❌ 無効なバージョン形式です: $(OPCODE_VERSION)"; \
		exit 1; \
	fi
	@echo "📦 最新バージョン: v$(OPCODE_VERSION)"

	# 既存バージョンの確認
	@CURRENT_VERSION=$$(dpkg-query -W -f='$${Version}' opcode 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "none"); \
	if [ "$$CURRENT_VERSION" = "$(OPCODE_VERSION)" ]; then \
	        echo "✅ すでに最新バージョン (v$(OPCODE_VERSION)) がインストールされています"; \
	else \
	        echo "📥 .deb パッケージをダウンロード中..."; \
	        TEMP_DIR=$$(mktemp -d); \
	        trap 'rm -rf "$$TEMP_DIR"' EXIT; \
	        DEB_URL="https://github.com/winfunc/opcode/releases/download/v$(OPCODE_VERSION)/opcode_v$(OPCODE_VERSION)_linux_x86_64.deb"; \
	        if curl -fL --retry 3 --connect-timeout 10 --max-time 180 -o "$$TEMP_DIR/opcode.deb" "$$DEB_URL"; then \
	                EXPECTED_SHA=$$(curl -fsSL "$$DEB_URL.sha256" | awk '{print $$1}'); \
	                ACTUAL_SHA=$$(sha256sum "$$TEMP_DIR/opcode.deb" | awk '{print $$1}'); \
	                if [ "$$EXPECTED_SHA" != "$$ACTUAL_SHA" ]; then \
	                        echo "❌ チェックサム検証に失敗しました"; \
	                        exit 1; \
	                fi; \
	                if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
	                        echo "⚠️  非対話環境またはエージェント実行を検出したため、sudo を伴うインストールをスキップします。"; \
	                        cp "$$TEMP_DIR/opcode.deb" /tmp/opcode.deb; \
	                        echo "💡 手動で以下のコマンドを実行してください:"; \
	                        echo "   sudo apt-get update && sudo apt-get install -y /tmp/opcode.deb"; \
	                        exit 1; \
	                else \
	                        echo "🔧 sudo 権限を使用してインストール中..."; \
	                        if sudo apt-get update -q && sudo apt-get install -y "$$TEMP_DIR/opcode.deb"; then \
	                                echo "✅ インストール完了"; \
	                                $(create_desktop_entry); \
	                        else \
	                                echo "❌ インストールに失敗しました。権限やパッケージ依存関係を確認してください。"; \
	                                exit 1; \
	                        fi; \
	                fi; \
	        else \
	                echo "❌ ダウンロードに失敗しました: $$DEB_URL"; \
	                exit 1; \
	        fi; \
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
	@if [ -L "$(HOME_DIR)/.claude/skills" ]; then \
		target="$$(readlink "$(HOME_DIR)/.claude/skills")"; \
		if [ "$$target" = "$(RUNTIME_SKILLS_DIR)" ]; then \
			echo "[+] skills: linked to $(RUNTIME_SKILLS_DIR)"; \
		else \
			echo "[x] skills: linked to $$target, expected $(RUNTIME_SKILLS_DIR)"; \
		fi; \
	else \
		echo "[x] skills: not linked. Run 'make setup-claude'."; \
	fi

# Claude Code の起動（プロジェクト固有設定）
.PHONY: run-claude
run-claude: ## Claude Code を起動
	@if [ -f .env ]; then \
		set -a; \
		. ./.env; \
		set +a; \
	fi; \
	echo "🚀 Starting Claude Code"; \
	claude

# ========================================
# エイリアス
# ========================================

.PHONY: install-claude-code install-opcode setup-claude uninstall-claude sync-claude

install-claude-code: install-packages-claude-code  ## Claude Codeをインストール(エイリアス)

install-opcode: install-packages-opcode  ## Opcodeをインストール(エイリアス)

sync-claude: ## apm.yml (SSOT) から Claude 用設定ファイルを生成する
	$(Q_ECHO) "🔄 Claude 設定ファイルを apm.yml から生成中..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python "$(REPO_ROOT)/_scripts/generate-claude-settings.py"; \
	else \
		python3 "$(REPO_ROOT)/_scripts/generate-claude-settings.py"; \
	fi
	$(Q_ECHO) "✅ Claude 設定ファイルの生成が完了しました"

setup-claude: sync-claude ## Claude Codeの設定を適用
	@echo "📝 Claude Codeの設定を適用中..."
	@# グローバル設定ディレクトリ (~/.claude) を作成
	@mkdir -p "$(HOME_DIR)/.claude"
	@# CLAUDE.md
	@if [ -e "$(HOME_DIR)/.claude/CLAUDE.md" ] && [ ! -L "$(HOME_DIR)/.claude/CLAUDE.md" ]; then \
		echo "⚠️  $(HOME_DIR)/.claude/CLAUDE.md が実体ファイルとして既に存在するため、スキップします。"; \
	else \
		ln -sf "$(REPO_ROOT)/global-rules/AGENTS.global.md" "$(HOME_DIR)/.claude/CLAUDE.md"; \
	fi
	@# .claude.json (Home root)
	@if [ -e "$(HOME_DIR)/.claude.json" ] && [ ! -L "$(HOME_DIR)/.claude.json" ]; then \
		echo "⚠️  $(HOME_DIR)/.claude.json が実体ファイルとして既に存在するため、スキップします。"; \
	else \
		ln -sf "$(REPO_ROOT)/claude/settings.json" "$(HOME_DIR)/.claude.json"; \
	fi
	@# settings.json
	@if [ -e "$(HOME_DIR)/.claude/settings.json" ] && [ ! -L "$(HOME_DIR)/.claude/settings.json" ]; then \
		echo "⚠️  $(HOME_DIR)/.claude/settings.json が実体ファイルとして既に存在するため、スキップします。"; \
	else \
		ln -sf "$(REPO_ROOT)/claude/settings.json" "$(HOME_DIR)/.claude/settings.json"; \
	fi
	@# skills/
	@if [ -e "$(HOME_DIR)/.claude/skills" ] && [ ! -L "$(HOME_DIR)/.claude/skills" ]; then \
		backup="$(HOME_DIR)/.claude/skills.bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "[!] Existing Claude skills directory is not a symlink; moving it to $$backup"; \
		mv "$(HOME_DIR)/.claude/skills" "$$backup"; \
	fi
	@ln -sfn "$(RUNTIME_SKILLS_DIR)" "$(HOME_DIR)/.claude/skills"
	@# statusline.sh
	@chmod +x "$(REPO_ROOT)/claude/statusline.sh"
	@if [ -e "$(HOME_DIR)/.claude/statusline.sh" ] && [ ! -L "$(HOME_DIR)/.claude/statusline.sh" ]; then \
		echo "⚠️  $(HOME_DIR)/.claude/statusline.sh が実体ファイルとして既に存在するため、スキップします。"; \
	else \
		ln -sf "$(REPO_ROOT)/claude/statusline.sh" "$(HOME_DIR)/.claude/statusline.sh"; \
	fi
	@echo "✅ Claude Codeの設定が完了しました"

uninstall-claude: ## Claude Codeの設定を削除
	@echo "🗑️  Claude Codeの設定を削除中..."
	@for target in "$(HOME_DIR)/.claude.json" "$(HOME_DIR)/.claude/CLAUDE.md" "$(HOME_DIR)/.claude/settings.json" "$(HOME_DIR)/.claude/statusline.sh"; do \
		if [ -L "$$target" ]; then \
			rm "$$target"; \
		elif [ -e "$$target" ]; then \
			echo "⚠️  $$target は実体ファイルのため削除をスキップしました。"; \
		fi; \
	done
	@echo "✅ Claude Codeの設定を削除しました"

.PHONY: install-claude-desktop
install-claude-desktop: ## Install Claude Desktop on Linux (Beta)
	@echo "[*] Starting installation of Claude Desktop (Linux Beta)..."
	@if [ -f /etc/apt/sources.list.d/claude-desktop.list ]; then \
		echo "[+] Claude Desktop apt repository is already registered."; \
	else \
		if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
			echo "[!] Non-interactive or agent execution environment detected. Skipping repository configuration with sudo."; \
			echo "[i] Please run the following commands manually:"; \
			echo "    sudo curl -fsSLo /usr/share/keyrings/claude-desktop-archive-keyring.asc https://downloads.claude.ai/claude-desktop/key.asc"; \
			echo "    echo \"deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main\" | sudo tee /etc/apt/sources.list.d/claude-desktop.list"; \
			echo "    sudo apt-get update && sudo apt-get install -y claude-desktop"; \
			exit 1; \
		else \
			echo "[*] Configuring apt repository using sudo..."; \
			if sudo curl -fsSLo /usr/share/keyrings/claude-desktop-archive-keyring.asc https://downloads.claude.ai/claude-desktop/key.asc && \
			   echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/claude-desktop.list; then \
				echo "[+] Repository added successfully."; \
			else \
				echo "[x] Failed to add repository."; \
				exit 1; \
			fi; \
		fi; \
	fi
	@if dpkg-query -W -f='$${Status}' claude-desktop 2>/dev/null | grep -q "ok installed"; then \
		echo "[+] claude-desktop is already installed."; \
	else \
		if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
			echo "[!] Non-interactive or agent execution environment detected. Skipping installation with sudo."; \
			echo "[i] Please run the following commands manually:"; \
			echo "    sudo apt-get update && sudo apt-get install -y claude-desktop"; \
			exit 1; \
		else \
			echo "[*] Installing claude-desktop using sudo..."; \
			if sudo apt-get update -q && sudo apt-get install -y claude-desktop; then \
				echo "[+] Installation complete."; \
			else \
				echo "[x] Installation failed."; \
				exit 1; \
			fi; \
		fi; \
	fi
	@echo "[+] Claude Desktop installation complete."

.PHONY: uninstall-claude-desktop
uninstall-claude-desktop: ## Uninstall Claude Desktop on Linux
	@echo "[*] Starting uninstallation of Claude Desktop..."
	@if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
		echo "[!] Non-interactive or agent execution environment detected. Skipping uninstallation with sudo."; \
		echo "[i] Please run the following commands manually:"; \
		echo "    sudo apt remove claude-desktop"; \
		echo "    sudo rm /etc/apt/sources.list.d/claude-desktop.list"; \
		exit 1; \
	else \
		echo "[*] Uninstalling claude-desktop using sudo..."; \
		sudo apt remove -y claude-desktop || true; \
		if [ -f /etc/apt/sources.list.d/claude-desktop.list ]; then \
			sudo rm /etc/apt/sources.list.d/claude-desktop.list || true; \
		fi; \
		echo "[+] Uninstallation complete."; \
	fi

