export SHELL := /bin/bash

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
        setup-cursor

CURSOR_API_URL := https://cursor.com/api/download?platform=linux-x64&format=deb&releaseTrack=stable
CURSOR_USER_AGENT := Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36

setup-cursor: _cursor_link_settings ## Cursorの設定をセットアップ（設定ファイルのみ）

install-packages-cursor:
	@echo "📝 Cursor IDE (.deb) のバージョンを確認中..."
	@LATEST_VERSION=$$(curl -sL -A "$(CURSOR_USER_AGENT)" --connect-timeout 10 --max-time 30 "$(CURSOR_API_URL)" | jq -r '.version' 2>/dev/null || echo "error"); \
	CURRENT_VERSION=$$( (dpkg-query -W -f='$${Version}' cursor 2>/dev/null || echo "none") | cut -d'-' -f1 ); \
	if [ "$$LATEST_VERSION" = "error" ] || [ -z "$$LATEST_VERSION" ] || [ "$$LATEST_VERSION" = "null" ]; then \
		echo "⚠️  最新バージョンの取得に失敗しました (API応答が正しくない可能性があります)。"; \
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
	@if [ ! -f "$(REPO_ROOT)/ide/cursor/mcp.json" ] || [ "$(REPO_ROOT)/apm.yml" -nt "$(REPO_ROOT)/ide/cursor/mcp.json" ]; then \
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
		API_RESPONSE=$$(curl -sL -A "$(CURSOR_USER_AGENT)" --connect-timeout 10 --max-time 30 "$(CURSOR_API_URL)" 2>/dev/null); \
		if [ -n "$$API_RESPONSE" ] && echo "$$API_RESPONSE" | jq . >/dev/null 2>&1; then \
			DOWNLOAD_URL=$$(echo "$$API_RESPONSE" | jq -r '.debUrl' 2>/dev/null); \
		fi; \
	fi; \
	if [ -z "$$DOWNLOAD_URL" ] || [ "$$DOWNLOAD_URL" = "null" ]; then \
		echo "❌ エラー: API からの .deb ダウンロード URL 取得に失敗しました。"; \
		if [ -n "$$API_RESPONSE" ]; then echo "⚠️ APIレスポンス: $$API_RESPONSE"; else echo "⚠️ APIレスポンスが空です。"; fi; \
		exit 1; \
	fi; \
	echo "🔗 ダウンロードURL: $$DOWNLOAD_URL"; \
	if curl -L -A "$(CURSOR_USER_AGENT)" \
		--fail --max-time 120 --retry 3 --retry-delay 5 \
		-o cursor.deb "$$DOWNLOAD_URL"; then \
		echo "✅ ダウンロード完了。整合性を確認中..."; \
		SHA256_CMD=$$( (command -v sha256sum >/dev/null 2>&1 && echo "sha256sum") || (command -v shasum >/dev/null 2>&1 && echo "shasum -a 256") || echo ""); \
		if [ -z "$$SHA256_CMD" ]; then \
			echo "❌ エラー: sha256sum または shasum が見つかりません。整合性検証を中断します。"; \
			rm -f cursor.deb; exit 1; \
		fi; \
		SHA256_URL=$$(echo "$$DOWNLOAD_URL" | sed 's/$$/.sha256/'); \
		EXPECTED_HASH=$$(curl -sLf --connect-timeout 5 --max-time 10 "$$SHA256_URL" 2>/dev/null | awk '{print $$1}'); \
		if [ -z "$$EXPECTED_HASH" ] && [ -n "$$CURSOR_SHA256" ]; then \
			EXPECTED_HASH="$$CURSOR_SHA256"; \
			echo "ℹ️  外部 .sha256 が見つからなかったため、環境変数 CURSOR_SHA256 を使用します。"; \
		fi; \
		if [ -n "$$EXPECTED_HASH" ]; then \
			ACTUAL_HASH=$$($$SHA256_CMD cursor.deb | awk '{print $$1}'); \
			if [ "$$EXPECTED_HASH" != "$$ACTUAL_HASH" ]; then \
				echo "❌ ハッシュ不一致エラー: 整合性を確認できませんでした。"; \
				echo "   期待値: $$EXPECTED_HASH"; \
				echo "   実際値: $$ACTUAL_HASH"; \
				rm -f cursor.deb; exit 1; \
			else \
				echo "✅ ハッシュ検証に成功しました。"; \
			fi; \
		else \
			echo "⚠️  【警告】信頼できるハッシュ値が見つからなかったため、整合性検証をスキップします。"; \
			echo "     インストールを中止するには Ctrl-C を押してください。5秒後に続行します..."; \
			sleep 5; \
		fi; \
		echo "🚀 インストールを開始します..."; \
		if sudo dpkg -i cursor.deb; then \
			INSTALL_SUCCESS=1; \
		else \
			echo "⚠️  依存関係の解決を試みています..."; \
			sudo apt-get install -f -y && sudo dpkg -i cursor.deb; \
			if [ $$? -eq 0 ]; then INSTALL_SUCCESS=1; else INSTALL_SUCCESS=0; fi; \
		fi; \
		if [ "$$INSTALL_SUCCESS" = "1" ] && dpkg -s cursor >/dev/null 2>&1; then \
			echo "✅ インストール成功"; \
			rm -f cursor.deb; \
		else \
			echo "❌ Cursor のインストール（dpkg/apt）に失敗しました。パッケージが確認できません。"; \
			rm -f cursor.deb; \
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
	@if dpkg-query -W -f='$${Status}' cursor 2>/dev/null | grep -q "ok installed"; then \
		CURRENT_VERSION=$$(dpkg-query -W -f='$${Version}' cursor); \
		echo "💻 現在のバージョン: $$CURRENT_VERSION"; \
	else \
		echo "❌ Cursor IDE (.deb) がインストールされていません"; \
	fi
	@echo "🌐 最新バージョンを確認中..."
	@if command -v jq >/dev/null 2>&1; then \
		API_RESPONSE=$$(curl -sLf -A "$(CURSOR_USER_AGENT)" --connect-timeout 10 --max-time 30 "$(CURSOR_API_URL)" 2>/dev/null); \
		if [ $$? -ne 0 ]; then \
			echo "⚠️ 警告: Cursor API に接続できません"; \
		elif [ -z "$$API_RESPONSE" ]; then \
			echo "⚠️ 警告: Cursor バージョン情報が取得できません: 応答が空です"; \
		elif ! echo "$$API_RESPONSE" | jq . >/dev/null 2>&1; then \
			echo "⚠️ 警告: Cursor バージョン情報が取得できません: 不正なJSONです"; \
		else \
			LATEST_VERSION=$$(echo "$$API_RESPONSE" | jq -r '.version' 2>/dev/null); \
			if [ -z "$$LATEST_VERSION" ] || [ "$$LATEST_VERSION" = "null" ]; then \
				echo "⚠️ 警告: Cursor バージョン情報が取得できません: .versionがnullです"; \
			else \
				echo "🆕 最新バージョン: $$LATEST_VERSION"; \
			fi; \
		fi; \
	else \
		echo "⚠️ 警告: jqコマンドがないため確認をスキップします"; \
	fi

# Cursor の起動
.PHONY: run-cursor
run-cursor: ## Cursor IDE を起動
	@if [ -f .env ]; then \
		export $$(grep -v '^#' .env | xargs); \
	fi; \
	echo "🚀 Starting Cursor..."; \
	cursor &

# ========================================
# エイリアス
# ========================================

.PHONY: install-cursor

install-cursor: install-packages-cursor  ## Cursor IDEをインストール(エイリアス)

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
	@echo "URL: $(CURSOR_API_URL)"
