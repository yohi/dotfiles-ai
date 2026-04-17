# ============================================================
# SkillPort (skillport): インストール・設定
# ============================================================

SKILLPORT_SKILLS_DIR ?= $(HOME)/.skillport/skills
AGENT_SKILLS_REPO_ROOT ?= $(REPO_ROOT)/agent-skills

.PHONY: skillport install-skillport setup-skillport check-skillport check-skillport-version

# SkillPort のインストールとセットアップ
skillport: ## SkillPortのインストールとセットアップ
	@$(MAKE) install-skillport
	@$(MAKE) setup-skillport

SKILLPORT_VERSION ?= 1.1.1
SKILLPORT_MCP_VERSION ?= 1.1.0

# SkillPort および SkillPort MCP サーバーのインストール
install-skillport: ## SkillPort と SkillPort MCP をインストール
	@echo "📦 SkillPort のインストール状態を確認中..."
	@CURRENT_SP=$$(skillport --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "none"); \
	CURRENT_MCP=$$(uv tool list 2>/dev/null | grep -A 1 "skillport-mcp" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || echo "none"); \
	if [ "$$CURRENT_SP" = "$(SKILLPORT_VERSION)" ] && [ "$$CURRENT_MCP" = "$(SKILLPORT_MCP_VERSION)" ]; then \
		echo "✅ SkillPort ($$CURRENT_SP) および skillport-mcp ($$CURRENT_MCP) は既に最新バージョンがインストールされています。"; \
		exit 0; \
	fi; \
	\
	if [ "$$CURRENT_SP" = "none" ]; then \
		echo "📦 SkillPort をインストール中..."; \
	else \
		echo "🔄 SkillPort をアップデート中 ($$CURRENT_SP -> $(SKILLPORT_VERSION))..."; \
	fi; \
	\
	if command -v uv >/dev/null 2>&1; then \
		uv tool install skillport@$(SKILLPORT_VERSION) --force; \
		uv tool install skillport-mcp@$(SKILLPORT_MCP_VERSION) --force; \
	else \
		echo "❌ uv が見つかりません。先に uv をインストールしてください"; \
		exit 1; \
	fi; \
	echo "✅ SkillPort のインストールが完了しました"
# SkillPort の設定（ディレクトリ作成とリンク）
setup-skillport: ## SkillPort のディレクトリ構成をセットアップ
	@if $(call check_marker,setup-skillport); then \
		echo "$(call IDEMPOTENCY_SKIP_MSG,setup-skillport)"; \
		exit 0; \
	fi
	@echo "🚀 SkillPort のセットアップを開始中..."
	@mkdir -p "$(AGENT_SKILLS_REPO_ROOT)"
	@mkdir -p "$(HOME)/.skillport"
	@if [ -e "$(SKILLPORT_SKILLS_DIR)" ] && [ ! -L "$(SKILLPORT_SKILLS_DIR)" ]; then \
		backup="$(SKILLPORT_SKILLS_DIR).bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "⚠️  既存の skills ディレクトリを退避します: $$backup"; \
		mv "$(SKILLPORT_SKILLS_DIR)" "$$backup"; \
	fi
	@ln -sfn "$(AGENT_SKILLS_REPO_ROOT)" "$(SKILLPORT_SKILLS_DIR)"
	@echo "✅ セットアップが完了しました: $(SKILLPORT_SKILLS_DIR) -> $(AGENT_SKILLS_REPO_ROOT)"
	$(Q_ECHO) "💡 使い方を確認するには 'make help-skillport' を実行してください。"
	@$(call create_marker,setup-skillport,1)

.PHONY: help-skillport
help-skillport: ## SkillPort の使い方を表示
	$(call show-guide,$(REPO_ROOT)/_docs/guides/skillport.md)

# SkillPort の状態確認
check-skillport: ## SkillPort の状態確認
	@$(MAKE) check-skillport-version || true
	@echo "🔍 SkillPort の状態確認..."
	@if command -v skillport >/dev/null 2>&1; then \
		echo "✅ skillport: $$(skillport --version 2>/dev/null || echo installed)"; \
	else \
		echo "⚠️  skillport が見つかりません"; \
	fi
	@if command -v skillport-mcp >/dev/null 2>&1; then \
		echo "✅ skillport-mcp: installed"; \
	else \
		echo "⚠️  skillport-mcp が見つかりません"; \
	fi
	@if [ -L "$(SKILLPORT_SKILLS_DIR)" ]; then \
		get_realpath() { \
			if command -v realpath >/dev/null 2>&1; then \
				realpath "$$1"; \
			elif command -v uv >/dev/null 2>&1; then \
				uv run python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$$1"; \
			elif command -v python3 >/dev/null 2>&1; then \
				python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$$1"; \
			else \
				readlink -f "$$1" 2>/dev/null || readlink "$$1" 2>/dev/null || echo "$$1"; \
			fi; \
		}; \
		actual=$$(get_realpath "$(SKILLPORT_SKILLS_DIR)"); \
		expected=$$(get_realpath "$(AGENT_SKILLS_REPO_ROOT)"); \
		if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
			echo "✅ skills: $(SKILLPORT_SKILLS_DIR) -> $(AGENT_SKILLS_REPO_ROOT)"; \
		else \
			echo "⚠️  skills: $(SKILLPORT_SKILLS_DIR) points to $$actual (expected $$expected)"; \
		fi; \
	else \
		echo "⚠️  skills: $(SKILLPORT_SKILLS_DIR) is not a symlink"; \
	fi

.PHONY: stats-skillport status-skillport
stats-skillport: ## SkillPort の統計情報と MCP の起動状況を表示
	@if command -v skillport >/dev/null 2>&1; then \
		MCP_GATEWAY_STATUS=$$(systemctl --user is-active docker-mcp-gateway.service 2>/dev/null || echo "not-running"); \
		SKILLPORT_MCP_VERSION=$$(uv tool list 2>/dev/null | grep -A 1 "skillport-mcp" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || echo "not-installed"); \
		if [ "$$MCP_GATEWAY_STATUS" = "active" ] && command -v yq >/dev/null 2>&1 && yq '.gateway.enabled_servers[]' mcp/config.yaml 2>/dev/null | grep -qx "skillport"; then \
			SKILLPORT_MCP_STATUS="active (Gateway)"; \
		elif pgrep -f "skillport-mcp" >/dev/null 2>&1; then \
			SKILLPORT_MCP_STATUS="active (local)"; \
		else \
			SKILLPORT_MCP_STATUS="inactive"; \
		fi; \		export MCP_GATEWAY_STATUS; \
		export SKILLPORT_MCP_VERSION; \
		export SKILLPORT_MCP_STATUS; \
		skillport list --json | python3 _scripts/skillport_stats.py; \
	else \
		echo "❌ skillport が見つかりません"; \
		exit 1; \
	fi

status-skillport: stats-skillport ## stats-skillport のエイリアス


# SkillPort のバージョン確認 (GHCR vs PyPI)
check-skillport-version: ## SkillPort のコンテナと PyPI のバージョンを比較
	@echo "🔍 SkillPort のバージョン比較を確認中..."
	@bash _scripts/check-skillport-version.sh
