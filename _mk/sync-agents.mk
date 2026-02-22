# ============================================================
# sync-agents.mk: SSOT → 各エージェントへの同期・配備
# SPEC.md Features #1-#4 の実装
# ============================================================

REPO_ROOT       ?= $(CURDIR)
GLOBAL_RULES_DIR := $(REPO_ROOT)/global-rules
AGENT_SKILLS_DIR := $(REPO_ROOT)/agent-skills
META_PROMPT_SRC  := $(GLOBAL_RULES_DIR)/META_PROMPT.md
AGENT_CMDS_DIR   := $(REPO_ROOT)/agent-commands

# --- ターゲットファイル ---
GLOBAL_AGENTS_MD := $(GLOBAL_RULES_DIR)/AGENTS.md
OPENCODE_DOCS    := $(REPO_ROOT)/opencode/docs
CODEX_CONFIG     := $(REPO_ROOT)/codex/config.toml

.PHONY: sync-agents clean-legacy ai-setup \
        inject-meta-prompt-opencode inject-meta-prompt-codex \
        sync-skillport-doc link-user-agents link-agent-commands

# ============================================================
# sync-agents: メインの同期ターゲット (SPEC Feature #1, #2, #3)
# ============================================================
sync-agents: ## SSOTのスキル群を各エージェントの設定ファイルへ同期する
	@echo "🔄 sync-agents: SSOT → 各エージェントへの同期を開始..."
	@# Step 1: skillport doc でスキル一覧を instruction files へ反映
	@$(MAKE) sync-skillport-doc
	@# Step 2: ユーザーレベル AGENTS.md のシンボリックリンク配備
	@$(MAKE) link-user-agents
	@# Step 3: 共通コマンドのシンボリックリンク配備
	@$(MAKE) link-agent-commands
	@# Step 4: 各エージェントへメタプロンプトを注入
	@# NOTE: Claude / Gemini は AGENTS.md を自動参照するため個別注入不要
	@$(MAKE) inject-meta-prompt-opencode
	@$(MAKE) inject-meta-prompt-codex
	@echo "✅ sync-agents: 全エージェントへの同期が完了しました"

# ============================================================
# sync-skillport-doc: skillport doc によるスキルテーブル更新
# ============================================================
sync-skillport-doc: ## skillport doc を実行し instruction files を更新
	@echo "📝 skillport doc: スキルテーブルを更新中..."
	@if command -v skillport >/dev/null 2>&1; then \
		cd "$(REPO_ROOT)" && skillport doc --all 2>&1 || \
			echo "⚠️  skillport doc の実行に問題がありました（スキップして続行）"; \
	else \
		echo "⚠️  skillport が見つかりません。スキルテーブルの更新をスキップします"; \
		echo "   インストール: make skillport"; \
	fi

# ============================================================
# link-user-agents: ユーザーレベル AGENTS.md の存在確認
# NOTE: 各エージェントの setup ターゲット (e.g. setup-opencode) が
#       ~/.config/<agent>/AGENTS.md → global-rules/AGENTS.md を直接リンクする
# ============================================================
link-user-agents: ## global-rules/AGENTS.md の存在確認
	@if [ -f "$(GLOBAL_AGENTS_MD)" ]; then \
		echo "✅ ユーザーレベル AGENTS.md: $(GLOBAL_AGENTS_MD)"; \
	else \
		echo "⚠️  $(GLOBAL_AGENTS_MD) が見つかりません"; \
	fi

# ============================================================
# link-agent-commands: 共通コマンドを各エージェントへ配備
# - OpenCode: .md シンボリックリンク
# - Claude Code: .md シンボリックリンク
# - Gemini CLI: .md → .toml 変換
# ============================================================
link-agent-commands: ## agent-commands/ のコマンドを各エージェントへ配備
	@echo "🔗 共通コマンドの配備中..."
	@if [ ! -d "$(AGENT_CMDS_DIR)" ]; then \
		echo "⚠️  $(AGENT_CMDS_DIR) が見つかりません。スキップします"; \
		exit 0; \
	fi
	@# --- OpenCode: .md シンボリックリンク ---
	@mkdir -p "$(REPO_ROOT)/opencode/commands"
	@for cmd in $(AGENT_CMDS_DIR)/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd"); \
		target="$(REPO_ROOT)/opencode/commands/$$base"; \
		if [ -L "$$target" ] && [ "$$(readlink "$$target" 2>/dev/null || true)" = "../../agent-commands/$$base" ]; then \
			echo "  [SKIP] opencode/commands/$$base"; \
		else \
			rm -f "$$target"; \
			ln -sfn "../../agent-commands/$$base" "$$target"; \
			echo "  ✅ opencode/commands/$$base"; \
		fi; \
	done
	@# --- Claude Code: .md シンボリックリンク ---
	@mkdir -p "$(REPO_ROOT)/claude/commands"
	@for cmd in $(AGENT_CMDS_DIR)/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd"); \
		target="$(REPO_ROOT)/claude/commands/$$base"; \
		if [ -L "$$target" ] && [ "$$(readlink "$$target" 2>/dev/null || true)" = "../../agent-commands/$$base" ]; then \
			echo "  [SKIP] claude/commands/$$base"; \
		else \
			rm -f "$$target"; \
			ln -sfn "../../agent-commands/$$base" "$$target"; \
			echo "  ✅ claude/commands/$$base"; \
		fi; \
	done
	@# --- Gemini CLI: .md → .toml 変換 ---
	@mkdir -p "$(REPO_ROOT)/gemini/commands"
	@for cmd in $(AGENT_CMDS_DIR)/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd" .md); \
		target="$(REPO_ROOT)/gemini/commands/$$base.toml"; \
		if [ -f "$$target" ] && [ "$$target" -nt "$$cmd" ]; then \
			echo "  [SKIP] gemini/commands/$$base.toml (up-to-date)"; \
		else \
			desc=$$(awk '/^---$$/{n++; next} n==1 && /^description:/{sub(/^description: */, ""); print; exit}' "$$cmd" | sed 's/"/\\"/g'); \
			body=$$(awk 'BEGIN{n=0} /^---$$/{n++; next} n>=2{print}' "$$cmd" | sed 's/\\/\\\\/g; s/"""/\\"\\"\\"/g'); \
			printf 'description = "%s"\n\nprompt = """\n%s\n"""\n' "$$desc" "$$body" > "$$target"; \
			echo "  ✅ gemini/commands/$$base.toml (generated from .md)"; \
		fi; \
	done

# ============================================================
# inject-meta-prompt-opencode: OpenCode docs への参照リンク作成
# ============================================================
inject-meta-prompt-opencode: ## OpenCode の docs/ に global-rules/ へのシンボリックリンクを作成
	@echo "📌 OpenCode: global-rules への参照リンクを作成中..."
	@mkdir -p "$(OPENCODE_DOCS)"
	@if [ -L "$(OPENCODE_DOCS)/global-rules" ]; then \
		actual=$$(readlink -f "$(OPENCODE_DOCS)/global-rules" 2>/dev/null || readlink "$(OPENCODE_DOCS)/global-rules" 2>/dev/null || true); \
		expected=$$(readlink -f "$(GLOBAL_RULES_DIR)" 2>/dev/null || readlink "$(GLOBAL_RULES_DIR)" 2>/dev/null || true); \
		if [ -n "$$actual" ] && [ "$$actual" = "$$expected" ]; then \
			echo "  [SKIP] 既にリンク済み: $(OPENCODE_DOCS)/global-rules -> $(GLOBAL_RULES_DIR)"; \
			exit 0; \
		fi; \
	fi
	@ln -sfn "../../global-rules" "$(OPENCODE_DOCS)/global-rules"
	@echo "✅ OpenCode: $(OPENCODE_DOCS)/global-rules -> ../../global-rules"

# ============================================================
# inject-meta-prompt-codex: Codex config.toml へのコメント注入
# ============================================================
inject-meta-prompt-codex: ## Codex の config.toml にメタプロンプト参照コメントを追記
	@echo "📌 Codex: メタプロンプト参照を注入中..."
	@if [ ! -f "$(CODEX_CONFIG)" ]; then \
		echo "⚠️  $(CODEX_CONFIG) が見つかりません。スキップします"; \
		exit 0; \
	fi
	@if grep -q "UAACS:META-PROMPT" "$(CODEX_CONFIG)" 2>/dev/null; then \
		echo "  [SKIP] 既にメタプロンプト参照が存在します"; \
	else \
		printf '\n# UAACS:META-PROMPT\n# 拡張スキル: ../agent-skills/ (各 SKILL.md を参照)\n# コーディングルール: ../global-rules/ (MARKDOWN.md, SHELL.md, DOCS_STYLE.md, GIT_STANDARDS.md)\n' >> "$(CODEX_CONFIG)"; \
		echo "✅ Codex: メタプロンプト参照を追記しました"; \
	fi

# ============================================================
# clean-legacy: レガシー設定ファイルのクリーンアップ (SPEC Feature #4)
# ============================================================
clean-legacy: ## 統合後に不要となった古いルールファイルを削除する
	@echo "🧹 clean-legacy: レガシーファイルのクリーンアップを開始..."
	@# opencode/docs/rules/ の重複ファイル
	@for f in MARKDOWN.md SHELL.md; do \
		src="$(OPENCODE_DOCS)/rules/$$f"; \
		ssot="$(GLOBAL_RULES_DIR)/$$f"; \
		if [ -f "$$src" ] && [ -f "$$ssot" ]; then \
			if diff -q "$$src" "$$ssot" >/dev/null 2>&1; then \
				echo "  🗑  削除: $$src (SSOTと同一)"; \
				rm -f "$$src"; \
			else \
				echo "  ⚠️  スキップ: $$src (SSOTと差異あり — 手動確認してください)"; \
			fi; \
		fi; \
	done
	@# opencode/docs/global/ の重複ファイル
	@for f in DOCS_STYLE.md GIT_STANDARDS.md; do \
		src="$(OPENCODE_DOCS)/global/$$f"; \
		ssot="$(GLOBAL_RULES_DIR)/$$f"; \
		if [ -f "$$src" ] && [ -f "$$ssot" ]; then \
			if diff -q "$$src" "$$ssot" >/dev/null 2>&1; then \
				echo "  🗑  削除: $$src (SSOTと同一)"; \
				rm -f "$$src"; \
			else \
				echo "  ⚠️  スキップ: $$src (SSOTと差異あり — 手動確認してください)"; \
			fi; \
		fi; \
	done
	@# 空になったディレクトリを削除
	@for d in "$(OPENCODE_DOCS)/rules" "$(OPENCODE_DOCS)/global"; do \
		if [ -d "$$d" ] && [ -z "$$(ls -A "$$d" 2>/dev/null)" ]; then \
			echo "  🗑  空ディレクトリを削除: $$d"; \
			rmdir "$$d"; \
		fi; \
	done
	@echo "✅ clean-legacy: クリーンアップが完了しました"

# ============================================================
# ai-setup: 一括実行 (SPEC API Definition)
# ============================================================
ai-setup: ## クリーンアップ・同期を一括実行し、全エージェントの開発環境を最新にする
	@echo "🚀 ai-setup: 全エージェント環境の一括セットアップを開始..."
	@$(MAKE) clean-legacy
	@$(MAKE) sync-agents
	@echo ""
	@echo "🎉 ai-setup: 全エージェントの開発環境が最新になりました"
	@echo ""
	@echo "📋 実行された処理:"
	@echo "  1. clean-legacy  — レガシーファイルのクリーンアップ"
	@echo "  2. sync-agents   — SSOT → 各エージェントへの同期"
	@echo ""
	@echo "📝 次のステップ:"
	@echo "  - make check-skillport  で skillport の状態を確認"
	@echo "  - skillport list        で登録スキルを確認"
	@echo "  - skillport lint        でスキルを検証"
