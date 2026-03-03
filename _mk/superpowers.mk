# ============================================================
# superpowers.mk: obra/superpowers の導入と統合 (SkillPort 管理版)
# ============================================================

SUPERPOWERS_REPO := obra/superpowers
# リポジトリ内のスキルディレクトリ
LOCAL_SUPERPOWERS_DIR := $(REPO_ROOT)/agent-skills/superpowers

GEMINI_SKILLS_DIR := $(HOME)/.gemini/skills
ANTIGRAVITY_SKILLS_DIR := $(HOME)/.gemini/antigravity/skills
AGENTS_SKILLS_DIR := $(HOME)/.agents/skills

.PHONY: setup-superpowers update-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers uninstall-superpowers

setup-superpowers: update-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers ## superpowers の導入と全エージェントへの統合を実行

update-superpowers: ## skillport を使用して superpowers をインポート/更新
	@echo "🔄 superpowers: skillport を使用してインポート/更新中..."
	@if command -v uvx >/dev/null 2>&1; then \
		uvx skillport add $(SUPERPOWERS_REPO) skills/ --namespace superpowers --yes --force; \
		HASH=$$(git ls-remote https://github.com/$(SUPERPOWERS_REPO).git HEAD | awk '{print $$1}'); \
		DATE=$$(date +%Y-%m-%d); \
		bash scripts/update-skill-manifest.sh "superpowers" "https://github.com/$(SUPERPOWERS_REPO)" "$$HASH" "$$DATE"; \
	else \
		echo "❌ uvx が見つかりません。先に uv をインストールしてください"; \
		exit 1; \
	fi

link-superpowers-gemini: ## Gemini CLI へスキルをリンク
	@echo "🔗 superpowers: Gemini CLI へスキルをリンク中..."
	@mkdir -p "$(GEMINI_SKILLS_DIR)"
	@if command -v gemini >/dev/null 2>&1; then \
		for skill in "$(LOCAL_SUPERPOWERS_DIR)"/*; do \
			if [ -d "$$skill" ]; then \
				gemini skills link "$$skill" --scope user --consent; \
			fi; \
		done; \
	else \
		echo "⚠️  gemini コマンドが見つかりません。スキップします"; \
	fi

link-superpowers-antigravity: ## Antigravity IDE へスキルを個別にリンク
	@echo "🔗 superpowers: Antigravity IDE へスキルをリンク中..."
	@mkdir -p "$(ANTIGRAVITY_SKILLS_DIR)"
	@if [ -d "$(LOCAL_SUPERPOWERS_DIR)" ]; then \
		for skill in "$(LOCAL_SUPERPOWERS_DIR)"/*; do \
			if [ -d "$$skill" ]; then \
				base=$$(basename "$$skill"); \
				target="$(ANTIGRAVITY_SKILLS_DIR)/$$base"; \
				if [ -L "$$target" ] || [ ! -e "$$target" ]; then \
					ln -sfn "$$skill" "$$target"; \
				else \
					echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
				fi; \
			fi; \
		done; \
	fi
	@mkdir -p "$(HOME)/.gemini/.agent/skills"
	@if [ -d "$(LOCAL_SUPERPOWERS_DIR)" ]; then \
		for skill in "$(LOCAL_SUPERPOWERS_DIR)"/*; do \
			if [ -d "$$skill" ]; then \
				base=$$(basename "$$skill"); \
				target="$(HOME)/.gemini/.agent/skills/$$base"; \
				if [ -L "$$target" ] || [ ! -e "$$target" ]; then \
					ln -sfn "$$skill" "$$target"; \
				else \
					echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
				fi; \
			fi; \
		done; \
	fi

link-superpowers-agents: ## Codex/汎用エージェントパスへリンク
	@echo "🔗 superpowers: 汎用エージェントパス (~/.agents/skills) へリンク中..."
	@mkdir -p "$(AGENTS_SKILLS_DIR)"
	@target="$(AGENTS_SKILLS_DIR)/superpowers"; \
	if [ -L "$$target" ] || [ ! -e "$$target" ]; then \
		ln -sfn "$(LOCAL_SUPERPOWERS_DIR)" "$$target"; \
	else \
		echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
	fi

update-gemini-md-superpowers: ## ~/.gemini/GEMINI.md にワークフロー指示を追記
	@echo "📝 superpowers: GEMINI.md を更新中..."
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
		printf '\n## BEGIN Superpowers Workflow\n# Superpowers Workflow\nこのプロジェクトでは [obra/superpowers](https://github.com/obra/superpowers) ワークフローを採用しています。\n\n## 核心的ルール\n- **スキル優先:** いかなるアクションの前にも必ず `using-superpowers` スキルを確認し、関連するスキルがあれば `activate_skill` で有効にしてください。\n- **計画と設計:** 実装前に `brainstorming` で設計を固め、`writing-plans` で詳細なタスクリストを作成してください。\n- **TDD:** すべての実装は `test-driven-development` スキルに従い、テストを先に書いてから実装してください。\n- **検証:** 完了前に `verification-before-completion` を実行し、エビデンスに基づいた成功報告を行ってください。\n## END Superpowers Workflow\n' >> "$(HOME)/.gemini/GEMINI.md"; \
	fi

uninstall-superpowers: ## superpowers の統合を解除（リンク削除、GEMINI.md 復元）
	@echo "🧹 superpowers: 統合を解除しています..."
	@for dir in "$(GEMINI_SKILLS_DIR)" "$(ANTIGRAVITY_SKILLS_DIR)" "$(HOME)/.gemini/.agent/skills" "$(AGENTS_SKILLS_DIR)"; do \
		if [ -d "$$dir" ]; then \
			for item in "$$dir"/*; do \
				if [ -L "$$item" ]; then \
					target=$$(readlink "$$item"); \
					case "$$target" in \
						"$(LOCAL_SUPERPOWERS_DIR)"*) \
							rm -f "$$item"; \
							;; \
					esac; \
				fi; \
			done; \
		fi; \
	done
	@rm -rf "$(LOCAL_SUPERPOWERS_DIR)"
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
	fi
	@echo "✅ superpowers: アンインストール完了"
