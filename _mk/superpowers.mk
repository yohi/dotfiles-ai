# ============================================================
# superpowers.mk: obra/superpowers の導入と統合
# ============================================================

SUPERPOWERS_REPO := https://github.com/obra/superpowers.git
SUPERPOWERS_DIR  := $(HOME)/.gemini/superpowers
GEMINI_SKILLS_DIR := $(HOME)/.gemini/skills
ANTIGRAVITY_SKILLS_DIR := $(HOME)/.gemini/antigravity/skills
AGENTS_SKILLS_DIR := $(HOME)/.agents/skills

.PHONY: setup-superpowers update-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers uninstall-superpowers

setup-superpowers: update-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers ## superpowers の導入と全エージェントへの統合を実行

update-superpowers: ## superpowers リポジトリをクローンまたは更新
	@echo "🔄 superpowers: リポジトリを更新中..."
	@if [ ! -d "$(SUPERPOWERS_DIR)" ]; then \
		git clone $(SUPERPOWERS_REPO) $(SUPERPOWERS_DIR); \
	elif [ ! -d "$(SUPERPOWERS_DIR)/.git" ]; then \
		echo "❌ ERROR: $(SUPERPOWERS_DIR) exists but is not a Git repository."; \
		echo "👉 Please manually remove or relocate the directory and try again."; \
		exit 1; \
	else \
		echo "📥 superpowers: $(SUPERPOWERS_DIR) を更新中..."; \
		git -C $(SUPERPOWERS_DIR) pull; \
	fi

link-superpowers-gemini: ## Gemini CLI へスキルをリンク
	@echo "🔗 superpowers: Gemini CLI へスキルをリンク中..."
	@mkdir -p $(GEMINI_SKILLS_DIR)
	@if command -v gemini >/dev/null 2>&1; then \
		for skill in $(SUPERPOWERS_DIR)/skills/*; do \
			if [ -d "$$skill" ]; then \
				gemini skills link "$$skill" --scope user --consent; \
			fi; \
		done; \
	else \
		echo "⚠️  gemini コマンドが見つかりません。スキップします"; \
	fi

link-superpowers-antigravity: ## Antigravity IDE へスキルを個別にリンク
	@echo "🔗 superpowers: Antigravity IDE へスキルをリンク中..."
	@mkdir -p $(ANTIGRAVITY_SKILLS_DIR)
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			target="$(ANTIGRAVITY_SKILLS_DIR)/$$base"; \
			if [ -L "$$target" ]; then \
				rm -f "$$target"; \
			elif [ -e "$$target" ]; then \
				echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
				continue; \
			fi; \
			ln -s "$$skill" "$$target"; \
		fi; \
	done
	@# ワークスペース固有のディレクトリも念のため
	@mkdir -p $(HOME)/.gemini/.agent/skills
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			target="$(HOME)/.gemini/.agent/skills/$$base"; \
			if [ -L "$$target" ]; then \
				rm -f "$$target"; \
			elif [ -e "$$target" ]; then \
				echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
				continue; \
			fi; \
			ln -s "$$skill" "$$target"; \
		fi; \
	done

link-superpowers-agents: ## Codex/汎用エージェントパスへリンク
	@echo "🔗 superpowers: 汎用エージェントパス (~/.agents/skills) へリンク中..."
	@mkdir -p $(AGENTS_SKILLS_DIR)
	@target="$(AGENTS_SKILLS_DIR)/superpowers"; \
	if [ -L "$$target" ]; then \
		rm -f "$$target"; \
	elif [ -e "$$target" ]; then \
		echo "⚠️  $$target exists and is NOT a symlink. Skipping."; \
	else \
		ln -s $(SUPERPOWERS_DIR)/skills "$$target"; \
	fi

update-gemini-md-superpowers: ## ~/.gemini/GEMINI.md にワークフロー指示を追記
	@echo "📝 superpowers: GEMINI.md を更新中..."
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		# 既存のマーカーブロックを削除 \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
		# 新しいブロックを追記 \
		printf '
## BEGIN Superpowers Workflow
# Superpowers Workflow
このプロジェクトでは [obra/superpowers](https://github.com/obra/superpowers) ワークフローを採用しています。

## 核心的ルール
- **スキル優先:** いかなるアクションの前にも必ず `using-superpowers` スキルを確認し、関連するスキルがあれば `activate_skill` で有効にしてください。
- **計画と設計:** 実装前に `brainstorming` で設計を固め、`writing-plans` で詳細なタスクリストを作成してください。
- **TDD:** すべての実装は `test-driven-development` スキルに従い、テストを先に書いてから実装してください。
- **検証:** 完了前に `verification-before-completion` を実行し、エビデンスに基づいた成功報告を行ってください。
## END Superpowers Workflow
' >> "$(HOME)/.gemini/GEMINI.md"; \
	fi

uninstall-superpowers: ## superpowers の統合を解除（リンク削除、GEMINI.md 復元）
	@echo "🧹 superpowers: 統合を解除しています..."
	@# Gemini CLI のリンク解除
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			target="$(GEMINI_SKILLS_DIR)/$$base"; \
			if [ -L "$$target" ]; then \
				rm -f "$$target"; \
			elif [ -e "$$target" ]; then \
				echo "⚠️  $$target is NOT a symlink. Skipping removal."; \
			fi; \
		fi; \
	done
	@# Antigravity IDE のシンボリックリンク削除
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			for target in "$(ANTIGRAVITY_SKILLS_DIR)/$$base" "$(HOME)/.gemini/.agent/skills/$$base"; do \
				if [ -L "$$target" ]; then \
					rm -f "$$target"; \
				elif [ -e "$$target" ]; then \
					echo "⚠️  $$target is NOT a symlink. Skipping removal."; \
				fi; \
			done; \
		fi; \
	done
	@# 汎用エージェントパスのリンク削除
	@target="$(AGENTS_SKILLS_DIR)/superpowers"; \
	if [ -L "$$target" ]; then \
		rm -f "$$target"; \
	elif [ -e "$$target" ]; then \
		echo "⚠️  $$target is NOT a symlink. Skipping removal."; \
	fi
	@# GEMINI.md からマーカーブロックのみを削除 \
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
	fi
	@echo "✅ superpowers: アンインストール完了"
