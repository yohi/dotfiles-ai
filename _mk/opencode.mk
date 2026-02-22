# ============================================================
# OpenCode (opencode): インストール・設定
# ============================================================

CONFIG_DIR ?= $(HOME_DIR)/.config
OPENCODE_HOME ?= $(HOME_DIR)/.opencode
OPENCODE_BIN ?= $(OPENCODE_HOME)/bin/opencode
OPENCODE_CONFIG_DIR ?= $(CONFIG_DIR)/opencode
OPENCODE_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/opencode.jsonc
OPENCODE_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/opencode.jsonc
# TODO 2026/01/26時点で.jsoncを読みに行かないので、.jsonに修正
OH_MY_OPENCODE_CONFIG_PATH ?= $(OPENCODE_CONFIG_DIR)/oh-my-opencode.json
OH_MY_OPENCODE_DOTFILES_CONFIG ?= $(REPO_ROOT)/opencode/oh-my-opencode.base.jsonc
OPENCODE_ANTIGRAVITY_PATH ?= $(OPENCODE_CONFIG_DIR)/antigravity.json
OPENCODE_DOTFILES_ANTIGRAVITY ?= $(REPO_ROOT)/opencode/antigravity.json
OPENCODE_AGENTS_PATH ?= $(OPENCODE_CONFIG_DIR)/AGENTS.md
OPENCODE_DOTFILES_AGENTS ?= $(REPO_ROOT)/global-rules/AGENTS.md
OPENCODE_COMMANDS_PATH ?= $(OPENCODE_HOME)/commands
OPENCODE_DOTFILES_COMMANDS ?= $(REPO_ROOT)/opencode/commands
OPENCODE_SKILLS_PATH ?= $(OPENCODE_HOME)/skills
OPENCODE_DOTFILES_SKILLS ?= $(REPO_ROOT)/opencode/skills
OPENCODE_DOCS_PATH ?= $(OPENCODE_CONFIG_DIR)/docs
OPENCODE_DOTFILES_DOCS ?= $(REPO_ROOT)/opencode/docs

.PHONY: opencode install-packages-opencode install-opencode opencode-update setup-opencode check-opencode

# OpenCode (opencode) をインストール & 設定
opencode: ## OpenCode(opencode)のインストールとセットアップ
	@if [ -x "$(OPENCODE_BIN)" ] && [ -f "$(OPENCODE_DOTFILES_CONFIG)" ] && [ -L "$(OPENCODE_CONFIG_PATH)" ]; then \
		actual=$$(readlink -f "$(OPENCODE_CONFIG_PATH)" 2>/dev/null || readlink "$(OPENCODE_CONFIG_PATH)" 2>/dev/null || true); \
		expected=$$(readlink -f "$(OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
		if [ "$$actual" = "$$expected" ]; then \
			skip=1; \
			if [ -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" ]; then \
				if [ -L "$(OH_MY_OPENCODE_CONFIG_PATH)" ]; then \
					actual_oh=$$(readlink -f "$(OH_MY_OPENCODE_CONFIG_PATH)" 2>/dev/null || true); \
					expected_oh=$$(readlink -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
					if [ "$$actual_oh" != "$$expected_oh" ]; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" ]; then \
				if [ -L "$(OPENCODE_ANTIGRAVITY_PATH)" ]; then \
					actual_anti=$$(readlink -f "$(OPENCODE_ANTIGRAVITY_PATH)" 2>/dev/null || true); \
					expected_anti=$$(readlink -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" 2>/dev/null || true); \
					if [ "$$actual_anti" != "$$expected_anti" ]; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -f "$(OPENCODE_DOTFILES_AGENTS)" ]; then \
				if [ -L "$(OPENCODE_AGENTS_PATH)" ]; then \
					actual_agents=$$(readlink -f "$(OPENCODE_AGENTS_PATH)" 2>/dev/null || true); \
					expected_agents=$$(readlink -f "$(OPENCODE_DOTFILES_AGENTS)" 2>/dev/null || true); \
					if [ "$$actual_agents" != "$$expected_agents" ]; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_COMMANDS)" ]; then \
				if [ -L "$(OPENCODE_COMMANDS_PATH)" ]; then \
					actual_cmds=$$(readlink -f "$(OPENCODE_COMMANDS_PATH)" 2>/dev/null || true); \
					expected_cmds=$$(readlink -f "$(OPENCODE_DOTFILES_COMMANDS)" 2>/dev/null || true); \
					if [ "$$actual_cmds" != "$$expected_cmds" ]; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_SKILLS)" ]; then \
				if [ -L "$(OPENCODE_SKILLS_PATH)" ]; then \
					actual_skills=$$(readlink -f "$(OPENCODE_SKILLS_PATH)" 2>/dev/null || true); \
					expected_skills=$$(readlink -f "$(OPENCODE_DOTFILES_SKILLS)" 2>/dev/null || true); \
					if [ "$$actual_skills" != "$$expected_skills" ]; then skip=0; fi; \
				else skip=0; fi; \
			fi; \
			if [ -d "$(OPENCODE_DOTFILES_DOCS)" ]; then \
				if [ -L "$(OPENCODE_DOCS_PATH)" ]; then \
					actual_docs=$$(readlink -f "$(OPENCODE_DOCS_PATH)" 2>/dev/null || true); \
					expected_docs=$$(readlink -f "$(OPENCODE_DOTFILES_DOCS)" 2>/dev/null || true); \
					if [ "$$actual_docs" != "$$expected_docs" ]; then skip=0; fi; \
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
	@bash -c 'set -euo pipefail; tmp="$$(mktemp)"; curl -fsSL https://opencode.ai/install -o "$$tmp"; bash "$$tmp"; rm -f "$$tmp"'
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
	@bash -c 'set -euo pipefail; tmp="$$(mktemp)"; curl -fsSL https://opencode.ai/install -o "$$tmp"; bash "$$tmp"; rm -f "$$tmp"'
	@if [ -x "$(OPENCODE_BIN)" ]; then \
		echo "✅ 更新後のバージョン: $$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown)"; \
	fi
	@$(call create_marker,opencode-update,$$($(OPENCODE_BIN) --version 2>/dev/null || echo unknown))

# OpenCode の設定を適用（XDG config へシンボリックリンク）
setup-opencode: ## OpenCode（opencode）の設定ファイルを適用
	@echo "🔧 OpenCode（opencode）の設定を適用中..."
	@mkdir -p "$(OPENCODE_CONFIG_DIR)"
	@# opencode.jsonc の設定
	@if [ ! -f "$(OPENCODE_DOTFILES_CONFIG)" ]; then \
		echo "⚠️  設定ファイルが見つかりません: $(OPENCODE_DOTFILES_CONFIG)"; \
		echo "    先に dotfiles に設定ファイルを用意してください"; \
		exit 1; \
	fi
	@if [ -e "$(OPENCODE_CONFIG_PATH)" ] && [ ! -L "$(OPENCODE_CONFIG_PATH)" ]; then \
		backup="$(OPENCODE_CONFIG_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "⚠️  既存の設定ファイルを退避します: $$backup"; \
		mv "$(OPENCODE_CONFIG_PATH)" "$$backup"; \
	fi
	@ln -sfn "$(OPENCODE_DOTFILES_CONFIG)" "$(OPENCODE_CONFIG_PATH)"
	@echo "✅ 設定を適用しました: $(OPENCODE_CONFIG_PATH)"
	@# oh-my-opencode.jsonc の設定
	@if [ -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" ]; then \
		if [ -e "$(OH_MY_OPENCODE_CONFIG_PATH)" ] && [ ! -L "$(OH_MY_OPENCODE_CONFIG_PATH)" ]; then \
			backup="$(OH_MY_OPENCODE_CONFIG_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "⚠️  既存の oh-my-opencode 設定ファイルを退避します: $$backup"; \
			mv "$(OH_MY_OPENCODE_CONFIG_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" "$(OH_MY_OPENCODE_CONFIG_PATH)"; \
		echo "✅ 設定を適用しました: $(OH_MY_OPENCODE_CONFIG_PATH)"; \
	else \
		echo "ℹ️  oh-my-opencode 設定ファイルはスキップされました（見つかりません）"; \
	fi
	@# antigravity.json の設定
	@if [ -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" ]; then \
		if [ -e "$(OPENCODE_ANTIGRAVITY_PATH)" ] && [ ! -L "$(OPENCODE_ANTIGRAVITY_PATH)" ]; then \
			backup="$(OPENCODE_ANTIGRAVITY_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "⚠️  既存の antigravity 設定ファイルを退避します: $$backup"; \
			mv "$(OPENCODE_ANTIGRAVITY_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OPENCODE_DOTFILES_ANTIGRAVITY)" "$(OPENCODE_ANTIGRAVITY_PATH)"; \
		echo "✅ 設定を適用しました: $(OPENCODE_ANTIGRAVITY_PATH)"; \
	else \
		echo "ℹ️  antigravity 設定ファイルはスキップされました（見つかりません）"; \
	fi
	@# AGENTS.md の設定
	@if [ -f "$(OPENCODE_DOTFILES_AGENTS)" ]; then \
		if [ -e "$(OPENCODE_AGENTS_PATH)" ] && [ ! -L "$(OPENCODE_AGENTS_PATH)" ]; then \
			backup="$(OPENCODE_AGENTS_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			echo "⚠️  既存の AGENTS.md ファイルを退避します: $$backup"; \
			mv "$(OPENCODE_AGENTS_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OPENCODE_DOTFILES_AGENTS)" "$(OPENCODE_AGENTS_PATH)"; \
		echo "✅ 設定を適用しました: $(OPENCODE_AGENTS_PATH)"; \
	else \
		echo "ℹ️  AGENTS.md ファイルはスキップされました（見つかりません）"; \
	fi
	@# commands/ の設定
	@if [ -d "$(OPENCODE_DOTFILES_COMMANDS)" ]; then \
		mkdir -p "$(OPENCODE_HOME)"; \
		if [ -e "$(OPENCODE_COMMANDS_PATH)" ] && [ ! -L "$(OPENCODE_COMMANDS_PATH)" ]; then \
			backup="$(OPENCODE_COMMANDS_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			if [ -d "$(OPENCODE_COMMANDS_PATH)" ]; then \
				echo "⚠️  既存の commands ディレクトリを退避します: $$backup"; \
			else \
				echo "⚠️  既存の commands ファイルを退避します: $$backup"; \
			fi; \
			mv "$(OPENCODE_COMMANDS_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OPENCODE_DOTFILES_COMMANDS)" "$(OPENCODE_COMMANDS_PATH)"; \
		echo "✅ 設定を適用しました: $(OPENCODE_COMMANDS_PATH)"; \
	else \
		echo "ℹ️  commands ディレクトリはスキップされました（見つかりません）"; \
	fi
	@# skills/ の設定
	@if [ -d "$(OPENCODE_DOTFILES_SKILLS)" ]; then \
		mkdir -p "$(OPENCODE_HOME)"; \
		if [ -e "$(OPENCODE_SKILLS_PATH)" ] && [ ! -L "$(OPENCODE_SKILLS_PATH)" ]; then \
			backup="$(OPENCODE_SKILLS_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			if [ -d "$(OPENCODE_SKILLS_PATH)" ]; then \
				echo "⚠️  既存の skills ディレクトリを退避します: $$backup"; \
			else \
				echo "⚠️  既存の skills ファイルを退避します: $$backup"; \
			fi; \
			mv "$(OPENCODE_SKILLS_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OPENCODE_DOTFILES_SKILLS)" "$(OPENCODE_SKILLS_PATH)"; \
		echo "✅ 設定を適用しました: $(OPENCODE_SKILLS_PATH)"; \
	else \
		echo "ℹ️  skills ディレクトリはスキップされました（見つかりません）"; \
	fi
	@# docs/ の設定
	@if [ -d "$(OPENCODE_DOTFILES_DOCS)" ]; then \
		mkdir -p "$(OPENCODE_CONFIG_DIR)"; \
		if [ -e "$(OPENCODE_DOCS_PATH)" ] && [ ! -L "$(OPENCODE_DOCS_PATH)" ]; then \
			backup="$(OPENCODE_DOCS_PATH).bak.$$(date +%Y%m%d%H%M%S)"; \
			if [ -d "$(OPENCODE_DOCS_PATH)" ]; then \
				echo "⚠️  既存の docs ディレクトリを退避します: $$backup"; \
			else \
				echo "⚠️  既存の docs ファイルを退避します: $$backup"; \
			fi; \
			mv "$(OPENCODE_DOCS_PATH)" "$$backup"; \
		fi; \
		ln -sfn "$(OPENCODE_DOTFILES_DOCS)" "$(OPENCODE_DOCS_PATH)"; \
		echo "✅ 設定を適用しました: $(OPENCODE_DOCS_PATH)"; \
	else \
		echo "ℹ️  docs ディレクトリはスキップされました（見つかりません）"; \
	fi
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
		expected=$$(readlink -f "$(OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OH_MY_OPENCODE_DOTFILES_CONFIG)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_ANTIGRAVITY)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_AGENTS)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_COMMANDS)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_SKILLS)" 2>/dev/null || true); \
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
			expected=$$(readlink -f "$(OPENCODE_DOTFILES_DOCS)" 2>/dev/null || true); \
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
