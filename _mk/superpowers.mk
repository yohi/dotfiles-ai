# ============================================================
# superpowers.mk: obra/superpowers の導入と統合 (Lock-file 管理版)
# ============================================================

SUPERPOWERS_REPO := https://github.com/obra/superpowers.git
SUPERPOWERS_NS   := superpowers
# リポジトリ内のスキルディレクトリ
LOCAL_SUPERPOWERS_DIR := $(REPO_ROOT)/agent-skills/superpowers

GEMINI_SKILLS_DIR := $(HOME)/.gemini/skills
ANTIGRAVITY_SKILLS_DIR := $(HOME)/.gemini/antigravity/skills
GEMINI_AGENT_SKILLS_DIR := $(HOME)/.gemini/.agent/skills
AGENTS_SKILLS_DIR := $(HOME)/.agents/skills

MANIFEST_FILE := $(REPO_ROOT)/agent-skills/EXTERNAL_SKILLS.md

.PHONY: setup-superpowers update-superpowers pin-superpowers update-gemini-md-superpowers uninstall-superpowers

setup-superpowers: update-superpowers update-gemini-md-superpowers ## superpowers の導入と全エージェントへの統合を実行

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
	bash "$(REPO_ROOT)/_scripts/update-skill-manifest.sh" "$(SUPERPOWERS_NS)" "https://github.com/obra/superpowers" "$$HASH" "$$DATE" && \
	echo "✅ superpowers: バージョン $$HASH を $(MANIFEST_FILE) に固定しました"

update-gemini-md-superpowers: ## ~/.gemini/GEMINI.md にワークフロー指示を追記
	@echo "📝 superpowers: GEMINI.md を更新中..."
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
		printf '\n## BEGIN Superpowers Workflow\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf '# Superpowers Workflow\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf 'このプロジェクトでは [obra/superpowers](https://github.com/obra/superpowers) ワークフローを採用しています。\n\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf '## 核心的ルール\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf -- '- **スキル優先:** いかなるアクションの前にも必ず `using-superpowers` スキルを確認し、関連するスキルがあれば `activate_skill` で有効にしてください。\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf -- '- **計画と設計:** 実装前に `brainstorming` で設計を固め、`writing-plans` で詳細なタスクリストを作成してください。\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf -- '- **TDD:** すべての実装は `test-driven-development` スキルに従い、テストを先に書いてから実装してください。\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf -- '- **検証:** 完了前に `verification-before-completion` を実行し、エビデンスに基づいた成功報告を行ってください。\n' >> "$(HOME)/.gemini/GEMINI.md"; \
		printf '## END Superpowers Workflow\n' >> "$(HOME)/.gemini/GEMINI.md"; \
	fi


uninstall-superpowers: ## superpowers の統合を解除（GEMINI.md 復元）
	@echo "🧹 superpowers: 統合を解除しています..."
	@# インストールされたスキルの削除
	@echo "📦 インストールされたスキルを削除中 (Namespace: $(SUPERPOWERS_NS))..."
	@LIST_OUTPUT=$$(uvx skillport list --namespace $(SUPERPOWERS_NS) 2>&1); \
	LIST_STATUS=$$?; \
	if [ $$LIST_STATUS -eq 0 ]; then \
		SKILLS=$$(echo "$$LIST_OUTPUT" | awk '/^- / {print $$2}'); \
		if [ -n "$$SKILLS" ]; then \
			for skill in $$SKILLS; do \
				echo "  - $$skill を削除中..."; \
				if ! uvx skillport remove "$$skill" --namespace $(SUPERPOWERS_NS) >/dev/null 2>&1; then \
					echo "  ⚠️  $$skill の削除に失敗しました"; \
				fi; \
			done; \
		else \
			echo "  ℹ️  削除対象のスキルは見つかりませんでした"; \
		fi; \
	else \
		echo "❌ スキル一覧の取得に失敗しました (exit $$LIST_STATUS):"; \
		echo "$$LIST_OUTPUT"; \
		exit 1; \
	fi
	@rm -rf "$(LOCAL_SUPERPOWERS_DIR)"
	@if [ -f "$(HOME)/.gemini/GEMINI.md" ]; then \
		if grep -q "## BEGIN Superpowers Workflow" "$(HOME)/.gemini/GEMINI.md"; then \
			sed '/## BEGIN Superpowers Workflow/,/## END Superpowers Workflow/d' "$(HOME)/.gemini/GEMINI.md" > "$(HOME)/.gemini/GEMINI.md.tmp" && mv "$(HOME)/.gemini/GEMINI.md.tmp" "$(HOME)/.gemini/GEMINI.md"; \
		fi; \
	fi
	@echo "✅ superpowers: アンインストール完了"
