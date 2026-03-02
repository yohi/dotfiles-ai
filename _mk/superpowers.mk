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
	@if [ ! -d "$(SUPERPOWERS_DIR)/.git" ]; then \
		echo "🚀 superpowers: $(SUPERPOWERS_DIR) を再作成してクローンします..."; \
		rm -rf $(SUPERPOWERS_DIR); \
		git clone $(SUPERPOWERS_REPO) $(SUPERPOWERS_DIR); \
	else \
		echo "📥 superpowers: $(SUPERPOWERS_DIR) を更新中..."; \
		git -C $(SUPERPOWERS_DIR) pull; \
	fi

link-superpowers-gemini: ## Gemini CLI へスキルをリンク
	@echo "🔗 superpowers: Gemini CLI へスキルをリンク中..."
	@mkdir -p $(GEMINI_SKILLS_DIR)
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			gemini skills link "$$skill" --scope user --consent; \
		fi; \
	done

link-superpowers-antigravity: ## Antigravity IDE へスキルを個別にリンク
	@echo "🔗 superpowers: Antigravity IDE へスキルをリンク中..."
	@mkdir -p $(ANTIGRAVITY_SKILLS_DIR)
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			ln -sfn "$$skill" "$(ANTIGRAVITY_SKILLS_DIR)/$$base"; \
		fi; \
	done
	@# ワークスペース固有のディレクトリも念のため
	@mkdir -p $(HOME)/.gemini/.agent/skills
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			ln -sfn "$$skill" "$(HOME)/.gemini/.agent/skills/$$base"; \
		fi; \
	done

link-superpowers-agents: ## Codex/汎用エージェントパスへリンク
	@echo "🔗 superpowers: 汎用エージェントパス (~/.agents/skills) へリンク中..."
	@mkdir -p $(AGENTS_SKILLS_DIR)
	@ln -sfn $(SUPERPOWERS_DIR)/skills $(AGENTS_SKILLS_DIR)/superpowers

update-gemini-md-superpowers: ## ~/.gemini/GEMINI.md にワークフロー指示を追記
	@echo "📝 superpowers: GEMINI.md を更新中..."
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if ! grep -q "Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			printf '
# Superpowers Workflow
このプロジェクトでは [obra/superpowers](https://github.com/obra/superpowers) ワークフローを採用しています。

## 核心的ルール
- **スキル優先:** いかなるアクションの前にも必ず `using-superpowers` スキルを確認し、関連するスキルがあれば `activate_skill` で有効にしてください。
- **計画と設計:** 実装前に `brainstorming` で設計を固め、`writing-plans` で詳細なタスクリストを作成してください。
- **TDD:** すべての実装は `test-driven-development` スキルに従い、テストを先に書いてから実装してください。
- **検証:** 完了前に `verification-before-completion` を実行し、エビデンスに基づいた成功報告を行ってください。
' >> "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
	fi

uninstall-superpowers: ## superpowers の統合を解除（リンク削除、GEMINI.md 復元）
	@echo "🧹 superpowers: 統合を解除しています..."
	@# Gemini CLI のリンク解除
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			rm -rf $(GEMINI_SKILLS_DIR)/$$base; \
		fi; \
	done
	@# Antigravity IDE のシンボリックリンク削除
	@for skill in $(SUPERPOWERS_DIR)/skills/*; do \
		if [ -d "$$skill" ]; then \
			base=$$(basename "$$skill"); \
			rm -f "$(ANTIGRAVITY_SKILLS_DIR)/$$base"; \
			rm -f "$(HOME)/.gemini/.agent/skills/$$base"; \
		fi; \
	done
	@# 汎用エージェントパスのリンク削除
	@rm -f $(AGENTS_SKILLS_DIR)/superpowers
	@# GEMINI.md からセクションを削除 (簡易的に sed で特定のパターンから最後までを削除)
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		sed -i '/# Superpowers Workflow/Q' "$(HOME)/.gemini/GEMINI.md"; \
	fi
	@echo "✅ superpowers: アンインストール完了"
