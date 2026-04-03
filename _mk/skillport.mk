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

# SkillPort および SkillPort MCP サーバーのインストール
install-skillport: ## SkillPort と SkillPort MCP をインストール
	@echo "📦 SkillPort のバージョンを確認中..."
	@CURRENT_SP=$$(skillport --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "none"); \
	CURRENT_MCP=$$(skillport-mcp --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "none"); \
	if [ "$$CURRENT_SP" = "1.1.1" ] && [ "$$CURRENT_MCP" = "1.1.0" ]; then \
		echo "✅ SkillPort (1.1.1) および skillport-mcp (1.1.0) は既にインストールされています。"; \
	else \
		echo "📦 SkillPort をインストール/アップデート中..."; \
		if command -v uv >/dev/null 2>&1; then \
			uv tool install skillport@1.1.1 --force; \
			uv tool install skillport-mcp@1.1.0 --force; \
		else \
			echo "❌ uv が見つかりません。先に uv をインストールしてください"; \
			exit 1; \
		fi; \
		echo "✅ SkillPort のインストールが完了しました"; \
	fi
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
	@$(call create_marker,setup-skillport,1)

# SkillPort の状態確認
check-skillport: ## SkillPort の状態を確認
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

# SkillPort のバージョン確認 (GHCR vs PyPI)
check-skillport-version: ## SkillPort のコンテナと PyPI のバージョンを比較
	@echo "🔍 SkillPort のバージョン比較を確認中..."
	@bash _scripts/check-skillport-version.sh
