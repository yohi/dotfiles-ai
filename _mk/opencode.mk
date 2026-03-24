# ============================================================
# OpenCode (opencode): インストール・設定
# ============================================================

CONFIG_DIR ?= $(HOME_DIR)/.config
OPENCODE_HOME ?= $(HOME_DIR)/.opencode
OPENCODE_BIN ?= $(OPENCODE_HOME)/bin/opencode
OPENCODE_CONFIG_DIR ?= $(CONFIG_DIR)/opencode
OPENCODE_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/opencode.jsonc
OPENCODE_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/opencode.jsonc
OH_MY_OPENCODE_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/oh-my-opencode.jsonc
OH_MY_OPENCODE_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/oh-my-opencode.jsonc
OPENCODE_ANTIGRAVITY_PATH ?= $(OPENCODE_CONFIG_DIR)/antigravity.json
OPENCODE_DOTFILES_ANTIGRAVITY ?= $(REPO_ROOT)/opencode/antigravity.json
OPENCODE_AGENTS_PATH ?= $(OPENCODE_CONFIG_DIR)/AGENTS.md
OPENCODE_DOTFILES_AGENTS ?= $(REPO_ROOT)/global-rules/AGENTS.global.md
OPENCODE_COMMANDS_PATH ?= $(OPENCODE_HOME)/commands
OPENCODE_DOTFILES_COMMANDS ?= $(REPO_ROOT)/opencode/commands
OPENCODE_SKILLS_PATH ?= $(OPENCODE_HOME)/skills
OPENCODE_DOTFILES_SKILLS ?= $(REPO_ROOT)/opencode/skills
OPENCODE_DOCS_PATH ?= $(OPENCODE_CONFIG_DIR)/docs
OPENCODE_DOTFILES_DOCS ?= $(REPO_ROOT)/opencode/docs
OPENCODE_INSTALLER_HASH ?= fc3c1b2123f49b6df545a7622e5127d21cd794b15134fc3b66e1ca49f7fb297e

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

.PHONY: opencode install-packages-opencode install-opencode opencode-update setup-opencode check-opencode

# OpenCode (opencode) をインストール & 設定
opencode: ## OpenCode(opencode)のインストールとセットアップ
	@if [ -x "$(OPENCODE_BIN)" ] && [ -f "$(OPENCODE_DOTFILES_CONFIG)" ] && [ -L "$(OPENCODE_CONFIG_PATH)" ]; then \
		check_link() { \
			local l="$$1" expected="$$2" act exp; \
			act=$$(readlink -f "$$l" 2>/dev/null || readlink "$$l" 2>/dev/null || true); \
			exp=$$(readlink -f "$$expected" 2>/dev/null || readlink "$$expected" 2>/dev/null || true); \
			[ "$$act" = "$$exp" ]; \
		}; \
		if check_link "$(OPENCODE_CONFIG_PATH)" "$(OPENCODE_DOTFILES_CONFIG)"; then \
			skip=1; \
			if [ -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" ]; then \
				if [ -L "$(OH_MY_OPENCODE_CONFIG_PATH)" ]; then \
					if ! check_link "$(OH_MY_OPENCODE_CONFIG_PATH)" "$(OH_MY_OPENCODE_DOTFILES_CONFIG)"; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
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
			if [ "$$skip" = "1" ]; then \
				echo "$(call IDEMPOTENCY_SKIP_MSG,opencode)"; \
				exit 0; \
			fi; \
		fi; \
	fi; \
	$(MAKE) install-packages-opencode setup-opencode

# OpenCode をインストール（公式インストーラ）
install-packages-opencode: ## OpenCode（opencode）をインストール
	@echo "📦 OpenCode（opencode）をインストール中..."
	@if [ -x "$(OPENCODE_BIN)" ]; then \
		echo "[SKIP] opencode is already installed: $(OPENCODE_BIN)"; \
		exit 0; \
	fi
	@if ! command -v curl >/dev/null 2>&1; then \
		echo "❌ curl が見つかりません。先に curl をインストールしてください"; \
		exit 1; \
	fi
	@bash -c 'set -euo pipefail; \
		tmp="$$(mktemp)"; \
		curl -fsSL https://opencode.ai/install -o "$$tmp"; \
		expected_hash="$(OPENCODE_INSTALLER_HASH)"; \
		actual_hash=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$tmp" | cut -d" " -f1) || shasum -a 256 "$$tmp" | cut -d" " -f1 ); \
		if [ "$$actual_hash" != "$$expected_hash" ]; then \
			echo "❌ Installer checksum mismatch"; \
			rm -f "$$tmp"; \
			exit 1; \
		fi; \
		yes | bash "$$tmp" || [ $${PIPESTATUS[1]} -eq 0 ]; \
		rm -f "$$tmp"'
	@if [ ! -x "$(OPENCODE_BIN)" ]; then \
		echo "❌ opencode のインストールに失敗しました: $(OPENCODE_BIN) が見つかりません"; \
		exit 1; \
	fi
	@echo "✅ OpenCode（opencode）のインストールが完了しました"
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
		curl -fsSL https://opencode.ai/install -o "$$tmp"; \
		expected_hash="$(OPENCODE_INSTALLER_HASH)"; \
		actual_hash=$$( (command -v sha256sum >/dev/null 2>&1 && sha256sum "$$tmp" | cut -d" " -f1) || shasum -a 256 "$$tmp" | cut -d" " -f1 ); \
		if [ "$$actual_hash" != "$$expected_hash" ]; then \
			echo "❌ Installer checksum mismatch"; \
			rm -f "$$tmp"; \
			exit 1; \
		fi; \
		yes | bash "$$tmp" || [ $${PIPESTATUS[1]} -eq 0 ]; \
		rm -f "$$tmp"'
	@if [ ! -x "$(OPENCODE_BIN)" ]; then \
		echo "❌ opencode のアップデートに失敗しました: $(OPENCODE_BIN) が見つかりません"; \
		exit 1; \
	fi
	@echo "✅ 更新後のバージョン: $$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown)"
	@$(call create_marker,opencode-update,$$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown))

# OpenCode の設定を適用（XDG config へシンボリックリンク）
setup-opencode: ## OpenCode（opencode）の設定ファイルを適用
	@echo "🔧 OpenCode（opencode）の設定を適用中..."
	@mkdir -p "$(OPENCODE_CONFIG_DIR)"
	@mkdir -p "$(OPENCODE_HOME)"
	@# opencode.jsonc の設定
	@$(call link_config,$(OPENCODE_DOTFILES_CONFIG),$(OPENCODE_CONFIG_PATH),opencode)
	@# oh-my-opencode.jsonc の設定
	@$(call link_config,$(OH_MY_OPENCODE_DOTFILES_CONFIG),$(OH_MY_OPENCODE_CONFIG_PATH),oh-my-opencode)
	@# antigravity.json の設定
	@$(call link_config,$(OPENCODE_DOTFILES_ANTIGRAVITY),$(OPENCODE_ANTIGRAVITY_PATH),antigravity)
	@# AGENTS.md の設定
	@$(call link_config,$(OPENCODE_DOTFILES_AGENTS),$(OPENCODE_AGENTS_PATH),AGENTS.md)
	@# commands/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_COMMANDS),$(OPENCODE_COMMANDS_PATH),commands)
	@# skills/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_SKILLS),$(OPENCODE_SKILLS_PATH),skills)
	@# docs/ の設定
	@$(call link_config,$(OPENCODE_DOTFILES_DOCS),$(OPENCODE_DOCS_PATH),docs)
	@$(call create_marker,setup-opencode,1)

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
	@if [ -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" ]; then \
		if [ -L "$(OH_MY_OPENCODE_CONFIG_PATH)" ]; then \
			actual=$$(readlink -f "$(OH_MY_OPENCODE_CONFIG_PATH)" 2>/dev/null || readlink "$(OH_MY_OPENCODE_CONFIG_PATH)" 2>/dev/null || true); \
			expected=$$(readlink -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || readlink "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
			if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
				echo "✅ oh-my-config: $(OH_MY_OPENCODE_CONFIG_PATH) -> $(OH_MY_OPENCODE_DOTFILES_CONFIG)"; \
			else \
				echo "⚠️  oh-my-config: $(OH_MY_OPENCODE_CONFIG_PATH) points to $$actual (expected $$expected)"; \
			fi; \
		elif [ -e "$(OH_MY_OPENCODE_CONFIG_PATH)" ]; then \
			echo "⚠️  oh-my-config: $(OH_MY_OPENCODE_CONFIG_PATH) exists but is not a symlink"; \
		else \
			echo "⚠️  oh-my-config: $(OH_MY_OPENCODE_CONFIG_PATH) is not configured"; \
		fi; \
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
