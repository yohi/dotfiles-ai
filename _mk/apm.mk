# ============================================================
# APM (Agent Package Manager): インストール・更新・同期
# ============================================================

.PHONY: install-apm update-apm apm-install

# APM 本体のインストール
install-apm: ## Microsoft APM をインストール (ユーザー領域 ~/.local に配置し self-update を有効化)
	@if command -v apm >/dev/null 2>&1; then \
		echo "✅ APM は既にインストールされています ($$(apm --version 2>/dev/null || echo 'installed'))"; \
	else \
		INSTALL_SUCCESS=false; \
		if command -v brew >/dev/null 2>&1; then \
			echo "📦 Homebrew を使用して APM をインストール中..."; \
			if brew install apm >/dev/null 2>&1; then \
				INSTALL_SUCCESS=true; \
			else \
				echo "⚠️  Homebrew でのインストールに失敗しました。スクリプトによるインストールを試みます。"; \
			fi; \
		fi; \
		\
		if [ "$$INSTALL_SUCCESS" = "false" ]; then \
			if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then \
				echo "❌ ハッシュ検証ユーティリティ (sha256sum または shasum) が見つかりません。"; \
				exit 1; \
			fi; \
			echo "📦 APM インストールスクリプトを実行中 (--prefix $(HOME)/.local)..."; \
			INSTALL_SCRIPT=$$(mktemp /tmp/apm-install.XXXXXX.sh); \
			if curl -f --max-time 30 -sSL "$(APM_INSTALL_URL)" -o "$$INSTALL_SCRIPT"; then \
				ACTUAL_HASH=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$INSTALL_SCRIPT" | cut -d" " -f1) || shasum -a 256 "$$INSTALL_SCRIPT" | cut -d" " -f1 ); \
				if [ "$$ACTUAL_HASH" != "$(APM_INSTALLER_HASH)" ]; then \
					echo "❌ APM インストーラーのハッシュ検証に失敗しました"; \
					echo "期待値: $(APM_INSTALLER_HASH)"; \
					echo "実際の値: $$ACTUAL_HASH"; \
					rm -f "$$INSTALL_SCRIPT"; \
					exit 1; \
				fi; \
				if sh "$$INSTALL_SCRIPT" --prefix "$(HOME)/.local"; then \
					rm -f "$$INSTALL_SCRIPT"; \
				else \
					EXIT_CODE=$$?; \
					echo "❌ APM インストールスクリプトの実行に失敗しました (終了コード: $$EXIT_CODE)"; \
					echo "URL: $(APM_INSTALL_URL)"; \
					echo "ハッシュ: $(APM_INSTALLER_HASH)"; \
					rm -f "$$INSTALL_SCRIPT"; \
					exit $$EXIT_CODE; \
				fi; \
			else \
				echo "❌ インストールスクリプトのダウンロードに失敗しました"; \
				rm -f "$$INSTALL_SCRIPT"; \
				exit 1; \
			fi; \
		fi; \
		\
		if command -v apm >/dev/null 2>&1; then \
			echo "✅ APM のインストールが完了しました ($$(apm --version 2>/dev/null || echo 'installed'))"; \
		else \
			echo "❌ APM のインストールに失敗したか、PATH が通っていません。"; \
			exit 1; \
		fi; \
	fi

# APM 本体の自己更新
update-apm: ## APM を最新バージョンに自己更新 (apm self-update)
	@if command -v apm >/dev/null 2>&1; then \
		echo "🔄 APM を更新中 (apm self-update)..."; \
		apm self-update; \
	else \
		echo "❌ APM が見つかりません。先に 'make install-apm' を実行してください。"; \
		exit 1; \
	fi

# APM install と全設定の同期を実行
apm-install: sync-codex-apm-seed ## APM install と全設定の同期を実行
	$(Q_ECHO) "📦 APM install を実行中..."
	@apm install
	$(Q_ECHO) "🔄 opencode.jsonc を生成中..."
	@$(MAKE) sync-opencode
	$(Q_ECHO) "🔄 エージェントを同期中..."
	@$(MAKE) sync-agents
	$(Q_ECHO) "🔗 MCP設定を同期中..."
	@$(MAKE) sync-mcp
	$(Q_ECHO) "📝 .env 雛形を確認中..."
	@$(MAKE) setup-apm-env
	$(Q_ECHO) "🔗 OpenCode 設定を適用中..."
	@$(MAKE) setup-opencode
	$(Q_ECHO) "✅ APM install と全設定の同期が完了しました"
