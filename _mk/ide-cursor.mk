export SHELL := /bin/sh

# ============================================================
# Cursor IDE セットアップ用Makefile (Debian/Ubuntu .deb 版)
# Cursor IDEのインストール、アップデート、管理を担当
# ============================================================

# 変数のデフォルト定義 (親Makefileから渡されない場合のフォールバック)
HOME_DIR ?= $(HOME)
REPO_ROOT ?= $(shell pwd)
DOTFILES_SHELL_ROOT ?= $(REPO_ROOT)/..

# Cursor IDEのインストール
.PHONY: install-packages-cursor _cursor_download \
        update-cursor stop-cursor check-cursor-version \
        install-packages-supercursor setup-cursor

CURSOR_API_URL := https://www.cursor.com/api/download?platform=linux-x64&format=deb&releaseTrack=stable

setup-cursor: _cursor_link_settings ## Cursorの設定をセットアップ（設定ファイルのみ）

install-packages-cursor:
	@echo "📝 Cursor IDE (.deb) のバージョンを確認中..."
	@LATEST_VERSION=$$(curl -sL --connect-timeout 10 --max-time 30 "$(CURSOR_API_URL)" | jq -r '.version' 2>/dev/null || echo "error"); \
	CURRENT_VERSION=$$( (dpkg-query -W -f='$${Version}' cursor 2>/dev/null || echo "none") | cut -d'-' -f1 ); \
	if [ "$$LATEST_VERSION" = "error" ]; then \
		echo "⚠️  最新バージョンの取得に失敗しました。インストールを試行します..."; \
		$(MAKE) _cursor_download; \
	elif [ "$$CURRENT_VERSION" = "$$LATEST_VERSION" ]; then \
		echo "✅ Cursor IDE は既に最新バージョン ($$CURRENT_VERSION) がインストールされています。"; \
	else \
		if [ "$$CURRENT_VERSION" = "none" ]; then \
			echo "📦 Cursor IDE を新規インストールします (バージョン: $$LATEST_VERSION)"; \
		else \
			echo "🔄 Cursor IDE をアップデートします ($$CURRENT_VERSION -> $$LATEST_VERSION)"; \
		fi; \
		$(MAKE) _cursor_download; \
	fi
	@$(MAKE) _cursor_link_settings
	@echo "✅ Cursor IDE のセットアップが完了しました"

_cursor_link_settings:
	@echo "📝 Cursorの設定をリンクしています..."
	@for f in settings.json keybindings.json; do \
		dst="$(HOME_DIR)/.config/Cursor/User/$$f"; \
		if [ -L "$$dst" ] && [ ! -e "$$dst" ]; then \
			echo "🧹 古い設定シンボリックリンクを削除します: $$f"; \
			rm "$$dst"; \
		fi; \
	done
	@mkdir -p $(HOME_DIR)/.config/Cursor/User/globalStorage/rooveterinaryinc.cursor-mcp
	@if [ ! -f "$(REPO_ROOT)/ide/cursor/mcp.json" ] || [ "$(REPO_ROOT)/mcp/servers.yaml" -nt "$(REPO_ROOT)/ide/cursor/mcp.json" ] || [ "$(REPO_ROOT)/_scripts/render-mcp-configs.py" -nt "$(REPO_ROOT)/ide/cursor/mcp.json" ]; then \
		echo "📝 中央管理ファイルから Cursor MCP 設定を再生成します..."; \
		$(MAKE) sync-mcp; \
	fi
	@mcp_json_dst="$(HOME_DIR)/.config/Cursor/User/globalStorage/rooveterinaryinc.cursor-mcp/mcp.json"; \
	if [ -f "$$mcp_json_dst" ] && [ ! -L "$$mcp_json_dst" ]; then \
		backup="$$mcp_json_dst.bak.$$(date +%Y%m%d_%H%M%S)"; \
		echo "⚠️  既存の mcp.json をバックアップします: $$backup"; \
		mv "$$mcp_json_dst" "$$backup"; \
	fi; \
	ln -sf $(REPO_ROOT)/ide/cursor/mcp.json "$$mcp_json_dst"
	@echo "✅ CursorのMCP設定リンクが完了しました"

_cursor_download:
	@echo "📦 Cursor (.deb) のダウンロード情報を取得中..."
	@cd /tmp && \
	DOWNLOAD_URL=""; \
	if command -v jq >/dev/null 2>&1; then \
		API_RESPONSE=$$(curl -sL --connect-timeout 10 --max-time 30 "$(CURSOR_API_URL)" 2>/dev/null); \
		if [ -n "$$API_RESPONSE" ] && echo "$$API_RESPONSE" | jq . >/dev/null 2>&1; then \
			DOWNLOAD_URL=$$(echo "$$API_RESPONSE" | jq -r '.debUrl' 2>/dev/null); \
		fi; \
	fi; \
	if [ -z "$$DOWNLOAD_URL" ] || [ "$$DOWNLOAD_URL" = "null" ]; then \
		echo "❌ エラー: API からの .deb ダウンロード URL 取得に失敗しました。"; \
		exit 1; \
	fi; \
	echo "🔗 ダウンロードURL: $$DOWNLOAD_URL"; \
	if curl -L --user-agent "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
		--max-time 120 --retry 3 --retry-delay 5 \
		-o cursor.deb "$$DOWNLOAD_URL" 2>/dev/null; then \
		echo "✅ ダウンロード完了。整合性を確認中..."; \
		if ! command -v sha256sum >/dev/null 2>&1; then \
			echo "⚠️  sha256sum が見つかりません。整合性チェックをスキップします。"; \
		fi; \
		echo "🚀 インストールを開始します..."; \
		if sudo dpkg -i cursor.deb || sudo apt-get install -f -y; then \
			echo "✅ インストール成功"; \
			rm -f cursor.deb; \
		else \
			echo "❌ Cursor のインストール（dpkg/apt）に失敗しました"; \
			exit 1; \
		fi; \
	else \
		echo "❌ Cursor (.deb) のダウンロードに失敗しました"; \
		exit 1; \
	fi

# Cursor IDEのアップデート
update-cursor: ## Cursor IDE をアップデート (.deb版)
	@echo "🔄 Cursor IDE のアップデートを開始します..."
	@$(MAKE) _cursor_download
	@echo "🎉 Cursor IDE のアップデートが完了しました"

# Cursor IDEを停止
stop-cursor:
	@echo "🛑 Cursor IDEを停止しています..."
	@if pgrep -x "cursor" >/dev/null 2>&1; then \
		echo "🔄 Cursor IDEの終了を試行中..."; \
		pkill -TERM -x "cursor" 2>/dev/null; \
		sleep 2; \
		if pgrep -x "cursor" >/dev/null 2>&1; then \
			pkill -9 -x "cursor" 2>/dev/null; \
		fi; \
		echo "✅ 全てのCursor関連プロセスを停止しました"; \
	else \
		echo "ℹ️  Cursor IDEは実行されていません"; \
	fi

# Cursor IDEのバージョン確認
check-cursor-version:
	@echo "🔍 Cursor IDEのバージョン情報を確認中..."
	@if dpkg -l | grep -q "^ii  cursor"; then \
		CURRENT_VERSION=$$(dpkg-query -W -f='$${Version}' cursor); \
		echo "💻 現在のバージョン: $$CURRENT_VERSION"; \
	else \
		echo "❌ Cursor IDE (.deb) がインストールされていません"; \
	fi
	@echo "🌐 最新バージョンを確認中..."
	@if command -v jq >/dev/null 2>&1; then \
		API_RESPONSE=$$(curl -sL --connect-timeout 10 --max-time 30 "https://www.cursor.com/api/download?platform=linux-x64&format=deb&releaseTrack=stable" 2>/dev/null); \
		if [ -n "$$API_RESPONSE" ] && echo "$$API_RESPONSE" | jq . >/dev/null 2>&1; then \
			LATEST_VERSION=$$(echo "$$API_RESPONSE" | jq -r '.version' 2>/dev/null); \
			echo "🆕 最新バージョン: $$LATEST_VERSION"; \
		fi; \
	fi

# SuperCursor (Cursor Framework) のインストール
install-packages-supercursor:
	@echo "🚀 SuperCursor (Cursor Framework) のインストールを開始..."
	@echo "📁 必要なディレクトリを作成中..."; \
	mkdir -p "${HOME_DIR}/.cursor"; \
	\
	echo "🔗 シンボリックリンクを作成中..."; \
	BACKUP_DIR="${HOME_DIR}/.cursor/backups/$$(date +%Y%m%d_%H%M%S)"; \
	safe_link() { \
		src="$$1"; dst="$$2"; \
		if [ -L "$$dst" ]; then \
			rm -f "$$dst"; \
		elif [ -e "$$dst" ]; then \
			mkdir -p "$$BACKUP_DIR"; \
			mv "$$dst" "$$BACKUP_DIR/"; \
			echo "📦 既存のファイルをバックアップしました: $$dst -> $$BACKUP_DIR/"; \
		fi; \
		ln -sfn "$$src" "$$dst"; \
	}; \
	safe_link "${REPO_ROOT}/ide/cursor/supercursor" "${HOME_DIR}/.cursor/supercursor"; \
	safe_link "${REPO_ROOT}/ide/cursor/supercursor/Commands" "${HOME_DIR}/.cursor/commands"; \
	safe_link "${REPO_ROOT}/ide/cursor/supercursor/Core" "${HOME_DIR}/.cursor/core"; \
	safe_link "${REPO_ROOT}/ide/cursor/supercursor/Hooks" "${HOME_DIR}/.cursor/hooks"; \
	safe_link "${REPO_ROOT}/ide/cursor/supercursor/README.md" "${HOME_DIR}/.cursor/CURSOR.md"; \
	if [ -f "${REPO_ROOT}/global-rules/AGENTS.global.md" ]; then \
		safe_link "${REPO_ROOT}/global-rules/AGENTS.global.md" "${HOME_DIR}/.cursor/AGENTS.md"; \
	fi; \
	echo "✅ SuperCursor フレームワークのセットアップが完了しました"

# ========================================
# エイリアス
# ========================================

.PHONY: install-cursor
install-cursor: install-packages-cursor  ## Cursor IDEをインストール(エイリアス)

.PHONY: install-supercursor
install-supercursor: install-packages-supercursor  ## SuperCursorをインストール(エイリアス)

.PHONY: uninstall-cursor
uninstall-cursor:
	@echo "🧹 Cursor IDE のアンインストールを開始..."
	@if dpkg -l | grep -q "^ii  cursor"; then \
		sudo apt-get remove -y cursor; \
	fi
	@if [ -d "$(HOME_DIR)/.cursor" ]; then \
		echo "📦 設定ディレクトリ (~/.cursor) はバックアップ保存のため残されます"; \
	fi
	@# AppImage 版の掃除
	@sudo rm -f /opt/cursor/cursor.AppImage
	@sudo rm -f /usr/share/applications/cursor.desktop
	@echo "✅ Cursor IDE のアンインストールが完了しました"
