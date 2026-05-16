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
GLOBAL_AGENTS_MD := $(GLOBAL_RULES_DIR)/AGENTS.global.md
OPENCODE_DOCS    := $(REPO_ROOT)/opencode/docs
CODEX_CONFIG     := $(REPO_ROOT)/codex/config.toml

.PHONY: sync-agents clean-sync-artifacts ai-setup \
        inject-meta-prompt-opencode inject-meta-prompt-codex \
        sync-skillport-doc link-user-agents link-agent-commands \
        install-external-skills uninstall-superpowers clean-legacy \
        sync-skills-to-agents

# ============================================================
# install-external-skills: 外部スキルのセットアップ
# ============================================================
install-external-skills: ## apm 未対応環境向けに git clone で外部スキルを取得する
	@set -e; \
	echo "📦 git clone で外部スキルを取得中..."; \
	mkdir -p "$(AGENT_SKILLS_DIR)/anthropics"; \
	mkdir -p "$(AGENT_SKILLS_DIR)/superpowers"; \
	if [ ! -d "$(AGENT_SKILLS_DIR)/anthropics/ai-api" ]; then \
		tmpdir=$$(mktemp -d); \
		trap 'rm -rf "$$tmpdir"' EXIT; \
		git init "$$tmpdir" >/dev/null; \
		git -C "$$tmpdir" remote add origin https://github.com/anthropics/skills; \
		git -C "$$tmpdir" fetch --depth 1 origin 5128e1865d670f5d6c9cef000e6dfc4e951fb5b9 >/dev/null 2>&1; \
		git -C "$$tmpdir" checkout FETCH_HEAD >/dev/null 2>&1; \
		if [ -d "$$tmpdir/skills" ]; then cp -r "$$tmpdir/skills/"* "$(AGENT_SKILLS_DIR)/anthropics/"; fi; \
		rm -rf "$$tmpdir"; \
	fi; \
	if [ ! -d "$(AGENT_SKILLS_DIR)/superpowers/brainstorming" ]; then \
		tmpdir=$$(mktemp -d); \
		trap 'rm -rf "$$tmpdir"' EXIT; \
		git init "$$tmpdir" >/dev/null; \
		git -C "$$tmpdir" remote add origin https://github.com/obra/superpowers; \
		git -C "$$tmpdir" fetch --depth 1 origin 6efe32c9e2dd002d0c394e861e0529675d1ab32e >/dev/null 2>&1; \
		git -C "$$tmpdir" checkout FETCH_HEAD >/dev/null 2>&1; \
		if [ -d "$$tmpdir/skills" ]; then cp -r "$$tmpdir/skills/"* "$(AGENT_SKILLS_DIR)/superpowers/"; fi; \
		rm -rf "$$tmpdir"; \
	fi
	@echo "✅ 外部スキルの準備が完了しました"

uninstall-superpowers: ## 外部スキル (superpowers) を削除する
	@echo "🗑️  外部スキル (superpowers) を削除中..."
	rm -rf "$(AGENT_SKILLS_DIR)/superpowers"
	@echo "✅ 削除が完了しました"

# ============================================================
# sync-agents: メインの同期ターゲット (SPEC Feature #1, #2, #3)
sync-agents: ## SSOTのスキル群を各エージェントの設定ファイルへ同期する
	@echo "🔄 sync-agents: SSOT → 各エージェントへの同期を開始..."
	@$(MAKE) clean-sync-artifacts
	@$(MAKE) sync-skillport-doc
	@$(MAKE) link-user-agents
	@$(MAKE) link-agent-commands
	@$(MAKE) inject-meta-prompt-opencode
	@$(MAKE) inject-meta-prompt-codex
	@$(MAKE) sync-skills-to-agents
	@touch "$(REPO_ROOT)/.last_sync"
	@echo "✅ sync-agents: 全エージェントへの同期が完了しました"

sync-skills-to-agents: ## agent-skills/ から .agents/skills/ へのシンボリックリンクを作成
	@echo "→ Syncing skills to .agents/skills/..."
	@mkdir -p "$(REPO_ROOT)/.agents/skills"
	@for dir in "$(AGENT_SKILLS_DIR)"/*/; do \
		[ -d "$$dir" ] || continue; \
		name=$$(basename "$$dir"); \
		target="$(REPO_ROOT)/.agents/skills/$$name"; \
		if [ -f "$${dir}SKILL.md" ]; then \
			if [ -L "$$target" ] || [ ! -e "$$target" ]; then \
				rm -f "$$target"; \
				ln -s "$${dir%/}" "$$target" && \
				echo "  Linked: $$name"; \
			else \
				echo "  [SKIP] $$name (exists as directory)"; \
			fi; \
		fi; \
	done
	@for subdir in "$(AGENT_SKILLS_DIR)"/*/*/; do \
		[ -d "$$subdir" ] || continue; \
		ns=$$(basename "$$(dirname "$$subdir")"); \
		name=$$(basename "$$subdir"); \
		mkdir -p "$(REPO_ROOT)/.agents/skills/$$ns"; \
		target="$(REPO_ROOT)/.agents/skills/$$ns/$$name"; \
		if [ -f "$${subdir}SKILL.md" ]; then \
			if [ -L "$$target" ] || [ ! -e "$$target" ]; then \
				rm -f "$$target"; \
				ln -s "$${subdir%/}" "$$target" && \
				echo "  Linked: $$name"; \
			else \
				echo "  [SKIP] $$name (exists as directory)"; \
			fi; \
		fi; \
	done
	@echo "✓ Skills synced to .agents/skills/"

# ============================================================
# clean-sync-artifacts: 同期状態のリセット
# ============================================================
clean-sync-artifacts: ## 同期マーカーおよび生成されたリンク・コマンドファイルを削除する
	@echo "🧹 clean-sync-artifacts: 同期状態をリセット中..."
	rm -f "$(REPO_ROOT)/.last_sync"
	@# OpenCode/Claude/Cursor 等のシンボリックリンクをクリーンアップ
	rm -rf "$(REPO_ROOT)/opencode/commands"
	rm -rf "$(REPO_ROOT)/claude/commands"
	rm -rf "$(REPO_ROOT)/ide/cursor/commands/agent"
	find "$(REPO_ROOT)/.cursor/rules" -maxdepth 1 -type l -name "*.md" -delete 2>/dev/null || true
	rm -rf "$(REPO_ROOT)/gemini/commands"
	rm -rf "$(REPO_ROOT)/codex/skills"
	@echo "✅ clean-sync-artifacts: 同期状態がリセットされました"

# ============================================================
# sync-skillport-doc: skillport doc の実行と各 AGENTS への直接反映
# ============================================================
sync-skillport-doc: ## _scripts/sync_agents.sh を実行し、agent-skills/ から AGENTS 群のスキル一覧を更新する
	@echo "📝 skillport doc: agent-skills/ から AGENTS 群のスキル一覧を更新中..."
	@bash "$(REPO_ROOT)/_scripts/sync_agents.sh"

# ============================================================
# link-user-agents: ユーザーレベル AGENTS.global.md の存在確認
# NOTE: 各エージェントの setup ターゲット (e.g. setup-opencode) が
#       ~/.config/<agent>/AGENTS.md → global-rules/AGENTS.global.md を直接リンクする
# ============================================================
link-user-agents: ## global-rules/AGENTS.global.md の存在確認
	@if [ -f "$(GLOBAL_AGENTS_MD)" ]; then \
		echo "✅ ユーザーレベル AGENTS.global.md: $(GLOBAL_AGENTS_MD)"; \
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
	@for cmd in "$(AGENT_CMDS_DIR)"/*.md; do \
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
	@for cmd in "$(AGENT_CMDS_DIR)"/*.md; do \
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
	@# --- Cursor IDE: .md シンボリックリンク ---
	@mkdir -p "$(REPO_ROOT)/ide/cursor/commands/agent"
	@mkdir -p "$(REPO_ROOT)/.cursor/rules"
	@for cmd in "$(AGENT_CMDS_DIR)"/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd"); \
		target="$(REPO_ROOT)/ide/cursor/commands/agent/$$base"; \
		if [ -L "$$target" ] && [ "$$(readlink "$$target" 2>/dev/null || true)" = "../../../../agent-commands/$$base" ]; then \
			echo "  [SKIP] ide/cursor/commands/agent/$$base"; \
		else \
			rm -f "$$target"; \
			ln -sfn "../../../../agent-commands/$$base" "$$target"; \
			echo "  ✅ ide/cursor/commands/agent/$$base"; \
		fi; \
		rule_target="$(REPO_ROOT)/.cursor/rules/$$base"; \
		if [ -L "$$rule_target" ] && [ "$$(readlink "$$rule_target" 2>/dev/null || true)" = "../../agent-commands/$$base" ]; then \
			echo "  [SKIP] .cursor/rules/$$base"; \
		else \
			rm -f "$$rule_target"; \
			ln -sfn "../../agent-commands/$$base" "$$rule_target"; \
			echo "  ✅ .cursor/rules/$$base"; \
		fi; \
	done
	@# --- Cursor IDE: coderabbit コマンドのルール同期 ---
	@for cmd in "$(REPO_ROOT)"/ide/cursor/commands/coderabbit/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd"); \
		[ "$$base" = "README.md" ] && continue; \
		rule_target="$(REPO_ROOT)/.cursor/rules/$$base"; \
		if [ -L "$$rule_target" ] && [ "$$(readlink "$$rule_target" 2>/dev/null || true)" = "../../ide/cursor/commands/coderabbit/$$base" ]; then \
			echo "  [SKIP] .cursor/rules/$$base (coderabbit)"; \
		else \
			rm -f "$$rule_target"; \
			ln -sfn "../../ide/cursor/commands/coderabbit/$$base" "$$rule_target"; \
			echo "  ✅ .cursor/rules/$$base (coderabbit)"; \
		fi; \
	done
	@# --- Gemini CLI: .md → .toml 変換 ---
	@mkdir -p "$(REPO_ROOT)/gemini/commands"
	@for cmd in "$(AGENT_CMDS_DIR)"/*.md; do \
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
	@# --- Codex CLI: .md → SKILL.md 変換 ---
	@mkdir -p "$(REPO_ROOT)/codex/skills"
	@for cmd in "$(AGENT_CMDS_DIR)"/*.md; do \
		[ -f "$$cmd" ] || continue; \
		base=$$(basename "$$cmd" .md); \
		target="$(REPO_ROOT)/codex/skills/$$base.md"; \
		if [ -f "$$target" ] && [ "$$target" -nt "$$cmd" ]; then \
			echo "  [SKIP] codex/skills/$$base.md (up-to-date)"; \
		else \
			name=$$(echo "$$base" | sed 's/-/ /g; s/\b\(.\)/\u\1/g'); \
			desc=$$(awk '/^---$$/{n++; next} n==1 && /^description:/{sub(/^description: */, ""); print; exit}' "$$cmd" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g"); \
			body=$$(awk 'BEGIN{n=0} /^---$$/{n++; next} n>=2{print}' "$$cmd"); \
			printf -- "---\nname: %s\ndescription: \"%s\"\n---\n\n# %s\n\n%s\n" "$$base" "$$desc" "$$name" "$$body" > "$$target"; \
			echo "  ✅ codex/skills/$$base.md (generated from .md)"; \
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
