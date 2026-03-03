# ============================================================
# superpowers.mk: obra/superpowers の導入と統合 (Lock-file 管理版)
# ============================================================

SUPERPOWERS_REPO := https://github.com/obra/superpowers.git
SUPERPOWERS_NS   := superpowers
# リポジトリ内のスキルディレクトリ
LOCAL_SUPERPOWERS_DIR := $(REPO_ROOT)/agent-skills/superpowers

GEMINI_SKILLS_DIR := $(HOME)/.gemini/skills
ANTIGRAVITY_SKILLS_DIR := $(HOME)/.gemini/antigravity/skills
AGENTS_SKILLS_DIR := $(HOME)/.agents/skills

MANIFEST_FILE := $(REPO_ROOT)/agent-skills/EXTERNAL_SKILLS.md

.PHONY: setup-superpowers update-superpowers pin-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers uninstall-superpowers

setup-superpowers: update-superpowers link-superpowers-gemini link-superpowers-antigravity link-superpowers-agents update-gemini-md-superpowers ## superpowers の導入と全エージェントへの統合を実行

update-superpowers: ## マニフェスト(Lock-file)に記載されたハッシュを使用して superpowers をインストール
	@echo "🔄 superpowers: ロックファイルからバージョンを確認中..."
	@HASH=$$(awk -F'|' '$$2 ~ /^[[:space:]]*$(SUPERPOWERS_NS)[[:space:]]*$$/ { gsub(/^[[:space:]]+|[[:space:]]+$$/, "", $$4); print $$4 }' "$(MANIFEST_FILE)"); \
	if [ -z "$$HASH" ] || [ "$$HASH" = "-" ]; then \
		echo "⚠️  マニフェストにハッシュが見つかりません。最新版を取得して Pin します..."; \
		$(MAKE) pin-superpowers; \
	else \
		echo "📥 superpowers: バージョン $$HASH をインストール中..."; \
		TMP_DIR=$$(mktemp -d); \
		trap 'rm -rf "$$TMP_DIR"' EXIT; \
		git clone "$(SUPERPOWERS_REPO)" "$$TMP_DIR" --quiet && \
		(cd "$$TMP_DIR" && git checkout "$$HASH" --quiet) && \
		uvx skillport add "$$TMP_DIR/skills/" --namespace $(SUPERPOWERS_NS) --yes --force && \
		echo "✅ superpowers: バージョン $$HASH の展開が完了しました"; \
	fi

pin-superpowers: ## 現在の最新 HEAD をマニフェスト(Lock-file)に固定する
	@echo "📌 superpowers: 最新の HEAD をロックファイルに固定中..."
	@HASH=$$(git ls-remote "$(SUPERPOWERS_REPO)" HEAD | awk '{print $$1}'); \
	DATE=$$(date +%Y-%m-%d); \
	TMP_DIR=$$(mktemp -d); \
	trap 'rm -rf "$$TMP_DIR"' EXIT; \
	git clone "$(SUPERPOWERS_REPO)" "$$TMP_DIR" --quiet && \
	(cd "$$TMP_DIR" && git checkout "$$HASH" --quiet) && \
	uvx skillport add "$$TMP_DIR/skills/" --namespace $(SUPERPOWERS_NS) --yes --force && \
	bash "$(REPO_ROOT)/scripts/update-skill-manifest.sh" "$(SUPERPOWERS_NS)" "https://github.com/obra/superpowers" "$$HASH" "$$DATE" && \
	echo "✅ superpowers: バージョン $$HASH を $(MANIFEST_FILE) に固定しました"

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
