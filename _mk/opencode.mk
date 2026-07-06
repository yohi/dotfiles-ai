# ============================================================
# OpenCode (opencode): インストール・設定
# ============================================================

CONFIG_DIR ?= $(HOME_DIR)/.config
OPENCODE_HOME ?= $(HOME_DIR)/.opencode
OPENCODE_BIN ?= $(OPENCODE_HOME)/bin/opencode
OPENCODE_CONFIG_DIR ?= $(CONFIG_DIR)/opencode
OPENCODE_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/opencode.jsonc
OPENCODE_TUI_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/tui.jsonc
OPENCODE_TUI_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/tui.jsonc
OPENCODE_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/opencode.jsonc
OH_MY_OPENAGENT_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/oh-my-openagent.jsonc
OH_MY_OPENAGENT_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/oh-my-openagent.jsonc.template
OPENCODE_ANTIGRAVITY_PATH ?= $(OPENCODE_CONFIG_DIR)/antigravity.json
OPENCODE_DOTFILES_ANTIGRAVITY ?= $(REPO_ROOT)/opencode/antigravity.json
OPENCODE_AGENTS_PATH ?= $(OPENCODE_CONFIG_DIR)/AGENTS.md
OPENCODE_DOTFILES_AGENTS ?= $(REPO_ROOT)/global-rules/AGENTS.global.md
OPENCODE_COMMANDS_PATH ?= $(OPENCODE_HOME)/commands
OPENCODE_DOTFILES_COMMANDS ?= $(REPO_ROOT)/opencode/commands
OPENCODE_SKILLS_PATH ?= $(OPENCODE_HOME)/skills
OPENCODE_DOTFILES_SKILLS ?= $(RUNTIME_SKILLS_DIR)
OPENCODE_DOCS_PATH ?= $(OPENCODE_CONFIG_DIR)/docs
OPENCODE_DOTFILES_DOCS ?= $(REPO_ROOT)/opencode/docs
OPENCODE_INSTALLER_HASH ?= fc3c1b2123f49b6df545a7622e5127d21cd794b15134fc3b66e1ca49f7fb297e

OPENCODE_API_URL := https://opencode.ai/api/version
OPENCODE_INSTALL_URL := https://opencode.ai/install

define link_config
	if [ -e "$(1)" ]; then \
		if [ -e "$(2)" ] && [ ! -L "$(2)" ]; then \
			backup="$(2).bak.$$(date +%Y%m%d%H%M%S)"; \
			if [ -d "$(2)" ]; then \
				echo "⚠️  既存の $(3) ディレクトリを退避します: $$backup"; \
			else \
				if [ "$(3)" = "opencode" ]; then \
					echo "⚠️  既存の設定ファイルを退避します: $$backup"; \
				elif [ "$(3)" = "AGENTS.md" ]; then \
					echo "⚠️  既存の $(3) ファイルを退避します: $$backup"; \
				elif [ "$(3)" = "commands" ] || [ "$(3)" = "skills" ] || [ "$(3)" = "docs" ]; then \
					echo "⚠️  既存の $(3) ファイルを退避します: $$backup"; \
				else \
					echo "⚠️  既存の $(3) 設定ファイルを退避します: $$backup"; \
				fi; \
			fi; \
			mv "$(2)" "$$backup"; \
		fi; \
		ln -sfn "$(1)" "$(2)"; \
		echo "✅ 設定を適用しました: $(2)"; \
	else \
		if [ "$(3)" = "opencode" ]; then \
			echo "⚠️  設定ファイルが見つかりません: $(1)"; \
			echo "    先に dotfiles に設定ファイルを用意してください"; \
			exit 1; \
		elif [ "$(3)" = "commands" ] || [ "$(3)" = "skills" ] || [ "$(3)" = "docs" ]; then \
			echo "ℹ️  $(3) ディレクトリはスキップされました（見つかりません）"; \
		elif [ "$(3)" = "AGENTS.md" ]; then \
			echo "ℹ️  $(3) ファイルはスキップされました（見つかりません）"; \
		else \
			echo "ℹ️  $(3) 設定ファイルはスキップされました（見つかりません）"; \
		fi; \
	fi
endef

# opencode.jsonc を apm.yml から生成する
sync-opencode: ## apm.yml (SSOT) から opencode/opencode.jsonc を生成する
	$(Q_ECHO) "🔄 opencode.jsonc を apm.yml から生成中..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python "$(REPO_ROOT)/_scripts/generate-opencode-jsonc.py"; \
	else \
		python3 "$(REPO_ROOT)/_scripts/generate-opencode-jsonc.py"; \
	fi
	$(Q_ECHO) "✅ opencode.jsonc の生成が完了しました"

# opencode.jsonc が apm.yml と同期しているか確認する (CI 用)
check-sync-opencode: ## opencode.jsonc が apm.yml と同期しているか確認する
	$(Q_ECHO) "🔍 opencode.jsonc の同期状態を確認中..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python "$(REPO_ROOT)/_scripts/generate-opencode-jsonc.py" --check; \
	else \
		python3 "$(REPO_ROOT)/_scripts/generate-opencode-jsonc.py" --check; \
	fi

# OpenCode (opencode) をインストール & 設定
opencode: sync-opencode ## OpenCode(opencode)のインストールとセットアップ
	@if [ -x "$(OPENCODE_BIN)" ] && [ -f "$(OPENCODE_DOTFILES_CONFIG)" ] && [ -L "$(OPENCODE_CONFIG_PATH)" ]; then \
		check_link() { \
			local l="$$1" expected_link="$$2" actual expected; \
			actual=$$(readlink -f "$$l" 2>/dev/null || readlink "$$l" 2>/dev/null || true); \
			expected=$$(readlink -f "$$expected_link" 2>/dev/null || readlink "$$expected_link" 2>/dev/null || true); \
			[ "$$actual" = "$$expected" ]; \
		}; \
		if check_link "$(OPENCODE_CONFIG_PATH)" "$(OPENCODE_DOTFILES_CONFIG)"; then \
			skip=1; \
			if [ -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" ]; then \
				if [ -L "$(OPENCODE_ANTIGRAVITY_PATH)" ]; then \
					if ! check_link "$(OPENCODE_ANTIGRAVITY_PATH)" "$(OPENCODE_DOTFILES_ANTIGRAVITY)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -f "$(OPENCODE_DOTFILES_AGENTS)" ]; then \
				if [ -L "$(OPENCODE_AGENTS_PATH)" ]; then \
					if ! check_link "$(OPENCODE_AGENTS_PATH)" "$(OPENCODE_DOTFILES_AGENTS)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_COMMANDS)" ]; then \
				if [ -L "$(OPENCODE_COMMANDS_PATH)" ]; then \
					if ! check_link "$(OPENCODE_COMMANDS_PATH)" "$(OPENCODE_DOTFILES_COMMANDS)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_SKILLS)" ]; then \
				if [ -L "$(OPENCODE_SKILLS_PATH)" ]; then \
					if ! check_link "$(OPENCODE_SKILLS_PATH)" "$(OPENCODE_DOTFILES_SKILLS)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_DOCS)" ]; then \
				if [ -L "$(OPENCODE_DOCS_PATH)" ]; then \
					if ! check_link "$(OPENCODE_DOCS_PATH)" "$(OPENCODE_DOTFILES_DOCS)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -f "$(OPENCODE_TUI_DOTFILES_CONFIG)" ]; then \
				if [ -L "$(OPENCODE_TUI_CONFIG_PATH)" ]; then \
					if ! check_link "$(OPENCODE_TUI_CONFIG_PATH)" "$(OPENCODE_TUI_DOTFILES_CONFIG)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ "$$skip" = "1" ]; then \
				echo "$(call IDEMPOTENCY_SKIP_MSG,opencode)"; \
				exit 0; \
			fi; \
		fi; \
	fi; \
	$(MAKE) install-packages-opencode setup-opencode


# OpenCode をインストール（公式インストーラ）

install-packages-opencode: ## OpenCode（opencode）をインストール
	@bash -c 'set -euo pipefail; \
		if ! command -v curl >/dev/null 2>&1; then \
			echo "❌ curl が見つかりません。先に curl をインストールしてください"; \
			exit 1; \
		fi; \
		echo "📦 OpenCode のバージョンを確認中..."; \
		LATEST_VERSION=$$(curl -sL --connect-timeout 10 --max-time 30 "$(OPENCODE_API_URL)" 2>/dev/null | grep -E "^[0-9]+\.[0-9]+\.[0-9]+$$" || echo "unknown"); \
		CURRENT_VERSION=$$( "$(OPENCODE_BIN)" --version 2>/dev/null || echo "none" ); \
		if [ "$$LATEST_VERSION" != "unknown" ]; then \
			if [ "$$CURRENT_VERSION" = "$$LATEST_VERSION" ]; then \
				echo "✅ OpenCode は既に最新バージョンです (バージョン: $$CURRENT_VERSION)"; \
				exit 0; \
			fi; \
			if [ "$$CURRENT_VERSION" = "none" ]; then \
				echo "📦 OpenCode を新規インストールします..."; \
			else \
				echo "🔄 OpenCode をアップデートします ($$CURRENT_VERSION -> $$LATEST_VERSION)..."; \
			fi; \
		else \
			if [ "$$CURRENT_VERSION" != "none" ]; then \
				echo "⚠️  最新バージョンの取得に失敗しました（404 またはレート制限）。現在のバージョン ($$CURRENT_VERSION) を維持します。"; \
				exit 0; \
			fi; \
			echo "📦 最新バージョンの取得に失敗しましたが、新規インストールを試みます..."; \
		fi; \
		tmp="$$(mktemp)"; \
		trap "rm -f \"$$tmp\"" EXIT; \
		curl -fsSL "$(OPENCODE_INSTALL_URL)" -o "$$tmp"; \
		expected_hash="$(OPENCODE_INSTALLER_HASH)"; \
		actual_hash=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$tmp" | cut -d" " -f1) || shasum -a 256 "$$tmp" | cut -d" " -f1 ); \
		if [ "$$actual_hash" != "$$expected_hash" ]; then \
			echo "❌ Installer checksum mismatch"; \
			exit 1; \
		fi; \
		yes | bash "$$tmp" || [ $${PIPESTATUS[1]} -eq 0 ]; \
		if [ ! -x "$(OPENCODE_BIN)" ]; then \
			echo "❌ opencode のインストールに失敗しました: $(OPENCODE_BIN) が見つかりません"; \
			exit 1; \
		fi; \
		mkdir -p "$(HOME_DIR)/.local/bin"; \
		ln -sfn "$(OPENCODE_BIN)" "$(HOME_DIR)/.local/bin/opencode"; \
		echo "✅ OpenCode（opencode）のインストールが完了しました"'
	@$(call create_marker,install-packages-opencode,$$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown))

# OpenCode を更新（公式インストーラ再実行）
opencode-update: ## OpenCode（opencode）をアップデート
	@echo "📦 OpenCode（opencode）をアップデート中..."
	@if ! command -v curl >/dev/null 2>&1; then \
		echo "❌ curl が見つかりません。先に curl をインストールしてください"; \
		exit 1; \
	fi
	@bash -c 'set -euo pipefail; \
		tmp="$$(mktemp)"; \
		trap "rm -f \"$$tmp\"" EXIT; \
		curl -fsSL "$(OPENCODE_INSTALL_URL)" -o "$$tmp"; \
		expected_hash="$(OPENCODE_INSTALLER_HASH)"; \
		actual_hash=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$tmp" | cut -d" " -f1) || shasum -a 256 "$$tmp" | cut -d" " -f1 ); \
		if [ "$$actual_hash" != "$$expected_hash" ]; then \
			echo "❌ Installer checksum mismatch"; \
			exit 1; \
		fi; \
		yes | bash "$$tmp" || [ $${PIPESTATUS[1]} -eq 0 ]'
	@if [ ! -x "$(OPENCODE_BIN)" ]; then \
		echo "❌ opencode のアップデートに失敗しました: $(OPENCODE_BIN) が見つかりません"; \
		exit 1; \
	fi
	@mkdir -p "$(HOME_DIR)/.local/bin"
	@ln -sfn "$(OPENCODE_BIN)" "$(HOME_DIR)/.local/bin/opencode"
	@echo "✅ 更新後のバージョン: $$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown)"
	@$(call create_marker,opencode-update,$$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown))

# OpenCode の設定を適用（XDG config へシンボリックリンク）
setup-opencode: sync-opencode ## OpenCode（opencode）の設定ファイルを適用
	@echo "🔧 OpenCode（opencode）の設定を適用中..."
	@mkdir -p "$(OPENCODE_CONFIG_DIR)"
	@mkdir -p "$(OPENCODE_HOME)"
	@# opencode.jsonc の設定
	@$(call link_config,$(OPENCODE_DOTFILES_CONFIG),$(OPENCODE_CONFIG_PATH),opencode)
	@# antigravity.json の設定
	@$(call link_config,$(OPENCODE_DOTFILES_ANTIGRAVITY),$(OPENCODE_ANTIGRAVITY_PATH),antigravity)
	@# AGENTS.md の設定

	@$(call link_config,$(OPENCODE_DOTFILES_AGENTS),$(OPENCODE_AGENTS_PATH),AGENTS.md)
	@# commands/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_COMMANDS),$(OPENCODE_COMMANDS_PATH),commands)
	@# skills/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_SKILLS),$(OPENCODE_SKILLS_PATH),skills)
	@# _docs/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_DOCS),$(OPENCODE_DOCS_PATH),docs)
	@# tui.jsonc の設定
	@$(call link_config,$(OPENCODE_TUI_DOTFILES_CONFIG),$(OPENCODE_TUI_CONFIG_PATH),tui)
	@$(call create_marker,setup-opencode,1)
	$(Q_ECHO) "✅ OpenCode（opencode）の設定を適用しました"
	$(Q_ECHO) "💡 使い方を確認するには 'make help-opencode' を実行してください。"
	@# Load .env from .zshrc for MCP_GATEWAY_TOKEN etc.
	@if [ -f "$(REPO_ROOT)/.env" ]; then \
		RC="$$HOME/.zshrc"; \
		MARKER="# dotfiles-ai .env"; \
		BLOCK='if [ -f "$(REPO_ROOT)/.env" ]; then set -a; . "$(REPO_ROOT)/.env"; set +a; fi'; \
		if [ -f "$$RC" ] && ! grep -q "$$MARKER" "$$RC" 2>/dev/null; then \
			echo "" >> "$$RC"; \
			echo "$$MARKER" >> "$$RC"; \
			echo "$$BLOCK" >> "$$RC"; \
			echo "Added .env to $$RC"; \
			echo "💡 Run 'source $$RC' to apply changes to the current session."; \
		fi; \
	fi

.PHONY: opencode install-packages-opencode install-opencode opencode-update setup-opencode check-opencode uninstall-opencode opencode-personal opencode-work sync-opencode check-sync-opencode help-opencode install-opencode-desktop uninstall-opencode-desktop
help-opencode: ## OpenCode の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/opencode.md)

# User-friendly alias

install-opencode: install-packages-opencode

# OpenCode の状態確認
check-opencode: ## OpenCode（opencode）の状態を確認
	@echo "🔍 OpenCode（opencode）の状態確認..."
	@if [ -x "$(OPENCODE_BIN)" ]; then \
		echo "✅ opencode: $$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown)"; \
	else \
		echo "⚠️  opencode が見つかりません: $(OPENCODE_BIN)"; \
	fi
	@if [ -L "$(OPENCODE_CONFIG_PATH)" ]; then \
		actual=$$(readlink -f "$(OPENCODE_CONFIG_PATH)" 2>/dev/null || readlink "$(OPENCODE_CONFIG_PATH)" 2>/dev/null || true); \
		expected=$$(readlink -f "$(OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
		if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
			echo "✅ config: $(OPENCODE_CONFIG_PATH) -> $(OPENCODE_DOTFILES_CONFIG)"; \
		else \
			echo "⚠️  config: $(OPENCODE_CONFIG_PATH) points to $$actual (expected $$expected)"; \
		fi; \
	elif [ -e "$(OPENCODE_CONFIG_PATH)" ]; then \
		echo "⚠️  config: $(OPENCODE_CONFIG_PATH) exists but is not a symlink"; \
	else \
		echo "⚠️  config: $(OPENCODE_CONFIG_PATH) is not configured"; \
	fi
	@if [ -f "$(OH_MY_OPENAGENT_DOTFILES_CONFIG)" ]; then \
		echo "✅ template: $(OH_MY_OPENAGENT_DOTFILES_CONFIG) exists"; \
	else \
		echo "⚠️  template: $(OH_MY_OPENAGENT_DOTFILES_CONFIG) not found"; \
	fi
	@if [ -f "$(REPO_ROOT)/_scripts/opencode-wrapper.sh" ]; then \
		echo "✅ wrapper: $(REPO_ROOT)/_scripts/opencode-wrapper.sh exists"; \
	else \
		echo "⚠️  wrapper: $(REPO_ROOT)/_scripts/opencode-wrapper.sh not found"; \
	fi
	@if [ -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" ]; then \
		if [ -L "$(OPENCODE_ANTIGRAVITY_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_ANTIGRAVITY_PATH)" 2>/dev/null || readlink "$(OPENCODE_ANTIGRAVITY_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_ANTIGRAVITY)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ antigravity: $(OPENCODE_ANTIGRAVITY_PATH) -> $(OPENCODE_DOTFILES_ANTIGRAVITY)"; \
			else \
				echo "⚠️  antigravity: $(OPENCODE_ANTIGRAVITY_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_ANTIGRAVITY_PATH)" ]; then \
			echo "⚠️  antigravity: $(OPENCODE_ANTIGRAVITY_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  antigravity: $(OPENCODE_ANTIGRAVITY_PATH) is not configured"; \
		fi; \
	fi
	@if [ -f "$(OPENCODE_DOTFILES_AGENTS)" ]; then \
		if [ -L "$(OPENCODE_AGENTS_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_AGENTS_PATH)" 2>/dev/null || readlink "$(OPENCODE_AGENTS_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_AGENTS)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_AGENTS)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ agents: $(OPENCODE_AGENTS_PATH) -> $(OPENCODE_DOTFILES_AGENTS)"; \
			else \
				echo "⚠️  agents: $(OPENCODE_AGENTS_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_AGENTS_PATH)" ]; then \
			echo "⚠️  agents: $(OPENCODE_AGENTS_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  agents: $(OPENCODE_AGENTS_PATH) is not configured"; \
		fi; \
	fi
	@if [ -d "$(OPENCODE_DOTFILES_COMMANDS)" ]; then \
		if [ -L "$(OPENCODE_COMMANDS_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_COMMANDS_PATH)" 2>/dev/null || readlink "$(OPENCODE_COMMANDS_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_COMMANDS)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_COMMANDS)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ commands: $(OPENCODE_COMMANDS_PATH) -> $(OPENCODE_DOTFILES_COMMANDS)"; \
			else \
				echo "⚠️  commands: $(OPENCODE_COMMANDS_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_COMMANDS_PATH)" ]; then \
			echo "⚠️  commands: $(OPENCODE_COMMANDS_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  commands: $(OPENCODE_COMMANDS_PATH) is not configured"; \
		fi; \
	fi
	@if [ -d "$(OPENCODE_DOTFILES_SKILLS)" ]; then \
		if [ -L "$(OPENCODE_SKILLS_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_SKILLS_PATH)" 2>/dev/null || readlink "$(OPENCODE_SKILLS_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_SKILLS)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_SKILLS)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ skills: $(OPENCODE_SKILLS_PATH) -> $(OPENCODE_DOTFILES_SKILLS)"; \
			else \
				echo "⚠️  skills: $(OPENCODE_SKILLS_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_SKILLS_PATH)" ]; then \
			echo "⚠️  skills: $(OPENCODE_SKILLS_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  skills: $(OPENCODE_SKILLS_PATH) is not configured"; \
		fi; \
	fi
	@if [ -d "$(OPENCODE_DOTFILES_DOCS)" ]; then \
		if [ -L "$(OPENCODE_DOCS_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_DOCS_PATH)" 2>/dev/null || readlink "$(OPENCODE_DOCS_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_DOCS)" 2>/dev/null || readlink "$(OPENCODE_DOTFILES_DOCS)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ docs: $(OPENCODE_DOCS_PATH) -> $(OPENCODE_DOTFILES_DOCS)"; \
			else \
				echo "⚠️  docs: $(OPENCODE_DOCS_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_DOCS_PATH)" ]; then \
			echo "⚠️  docs: $(OPENCODE_DOCS_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  docs: $(OPENCODE_DOCS_PATH) is not configured"; \
		fi; \
	fi
	@if [ -f "$(OPENCODE_TUI_DOTFILES_CONFIG)" ]; then \
		if [ -L "$(OPENCODE_TUI_CONFIG_PATH)" ]; then \
			actual=$$(readlink -f "$(OPENCODE_TUI_CONFIG_PATH)" 2>/dev/null || readlink "$(OPENCODE_TUI_CONFIG_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OPENCODE_TUI_DOTFILES_CONFIG)" 2>/dev/null || readlink "$(OPENCODE_TUI_DOTFILES_CONFIG)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ tui: $(OPENCODE_TUI_CONFIG_PATH) -> $(OPENCODE_TUI_DOTFILES_CONFIG)"; \
			else \
				echo "⚠️  tui: $(OPENCODE_TUI_CONFIG_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OPENCODE_TUI_CONFIG_PATH)" ]; then \
			echo "⚠️  tui: $(OPENCODE_TUI_CONFIG_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  tui: $(OPENCODE_TUI_CONFIG_PATH) is not configured"; \
		fi; \
	fi

# OpenCode の起動
uninstall-opencode: ## OpenCode（opencode）のアンインストール
	@echo "🗑️  OpenCode（opencode）をアンインストール中..."
	@# 防護策: 変数が空、または危険なパス（/ や HOME）を指している場合は中断する
	@if [ -z "$(OPENCODE_HOME)" ] || [ "$(OPENCODE_HOME)" = "/" ] || [ "$(OPENCODE_HOME)" = "$(HOME)" ]; then \
		echo "❌ エラー: OPENCODE_HOME ($(OPENCODE_HOME)) が設定されていないか、削除するには危険なパスです。中断します。"; \
		exit 1; \
	fi
	@if [ -z "$(OPENCODE_CONFIG_DIR)" ] || [ "$(OPENCODE_CONFIG_DIR)" = "/" ] || [ "$(OPENCODE_CONFIG_DIR)" = "$(HOME)" ]; then \
		echo "❌ エラー: OPENCODE_CONFIG_DIR ($(OPENCODE_CONFIG_DIR)) が設定されていないか、削除するには危険なパスです。中断します。"; \
		exit 1; \
	fi
	@rm -rf "$(OPENCODE_HOME)"
	@rm -rf "$(OPENCODE_CONFIG_DIR)"
	@rm -f "$(MARKER_DIR)/install-packages-opencode"*
	@rm -f "$(MARKER_DIR)/opencode-update"*
	@rm -f "$(MARKER_DIR)/setup-opencode"*
	@echo "✅ OpenCode（opencode）のアンインストールが完了しました"

opencode-personal: opencode ## OpenCode の personal プロファイルを適用して起動
	@bash _scripts/opencode-wrapper.sh personal

opencode-work: opencode ## OpenCode の work プロファイルを適用して起動
	@bash _scripts/opencode-wrapper.sh work

.PHONY: install-opencode-desktop
install-opencode-desktop: ## Install OpenCode Desktop GUI on Linux
	@echo "[*] Starting installation of OpenCode Desktop..."
	@if dpkg-query -W -f='$${Status}' opencode-desktop 2>/dev/null | grep -q "ok installed"; then \
		echo "[+] opencode-desktop is already installed."; \
	elif dpkg-query -W -f='$${Status}' opencode 2>/dev/null | grep -q "ok installed"; then \
		echo "[+] opencode package is already installed."; \
	else \
		if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
			echo "[!] Non-interactive or agent execution environment detected. Skipping installation with sudo."; \
			echo "[i] Please run the following commands manually:"; \
			echo '    TEMP_DIR=$$(mktemp -d)'; \
			echo '    curl -fL -o "$$TEMP_DIR/opencode.deb" "https://opencode.ai/ja/download/stable/linux-x64-deb"'; \
			echo '    sudo apt-get update && sudo apt-get install -y "$$TEMP_DIR/opencode.deb"'; \
			echo '    rm -rf "$$TEMP_DIR"'; \
			exit 1; \
		else \
			echo "[*] Downloading OpenCode Desktop deb package..."; \
			TEMP_DIR=$$(mktemp -d); \
			trap 'rm -rf "$$TEMP_DIR"' EXIT; \
			if curl -fL --retry 3 --connect-timeout 10 --max-time 180 -o "$$TEMP_DIR/opencode.deb" "https://opencode.ai/ja/download/stable/linux-x64-deb"; then \
				echo "[*] Installing OpenCode Desktop using sudo..."; \
				if sudo apt-get update -q && sudo apt-get install -y "$$TEMP_DIR/opencode.deb"; then \
					echo "[+] Installation complete."; \
				else \
					echo "[x] Installation failed."; \
					exit 1; \
				fi; \
			else \
				echo "[x] Failed to download OpenCode Desktop package."; \
				exit 1; \
			fi; \
		fi; \
	fi

.PHONY: uninstall-opencode-desktop
uninstall-opencode-desktop: ## Uninstall OpenCode Desktop GUI on Linux
	@echo "[*] Starting uninstallation of OpenCode Desktop..."
	@if [ -n "$$CI" ] || [ -n "$$AGENT_MODE" ] || ! [ -t 0 ]; then \
		echo "[!] Non-interactive or agent execution environment detected. Skipping uninstallation with sudo."; \
		echo "[i] Please run the following commands manually:"; \
		echo "    sudo apt-get remove -y opencode-desktop || sudo apt-get remove -y opencode"; \
		exit 1; \
	else \
		echo "[*] Uninstalling OpenCode Desktop using sudo..."; \
		if dpkg-query -W -f='$${Status}' opencode-desktop 2>/dev/null | grep -q "ok installed"; then \
			sudo apt-get remove -y opencode-desktop || true; \
			echo "[+] Uninstallation complete."; \
		elif dpkg-query -W -f='$${Status}' opencode 2>/dev/null | grep -q "ok installed"; then \
			sudo apt-get remove -y opencode || true; \
			echo "[+] Uninstallation complete."; \
		else \
			echo "[i] opencode-desktop / opencode is not installed. Nothing to do."; \
		fi; \
	fi
