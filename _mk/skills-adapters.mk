# ============================================================
# Skill directory adapters
# ============================================================

SKILL_ADAPTER_TARGETS := \
	$(HOME_DIR)/.opencode/skills \
	$(HOME_DIR)/.claude/skills \
	$(HOME_DIR)/.skillport/skills

.PHONY: setup-skill-adapters check-skill-adapters sync-skills-to-agents

define link_skill_adapter
	@if [ -e "$(1)" ] && [ ! -L "$(1)" ]; then \
		backup="$(1).bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "[!] Existing skill directory is not a symlink; moving it to $$backup"; \
		mv "$(1)" "$$backup"; \
	fi; \
	mkdir -p "$$(dirname "$(1)")"; \
	ln -sfn "$(RUNTIME_SKILLS_DIR)" "$(1)"; \
	echo "[+] Linked $(1) -> $(RUNTIME_SKILLS_DIR)"
endef

setup-skill-adapters: ## Link native skill directories to .agents/skills
	@if [ ! -d "$(RUNTIME_SKILLS_DIR)" ]; then \
		echo "[x] Runtime skills directory not found: $(RUNTIME_SKILLS_DIR)"; \
		echo "[i] Run 'apm install' before setting up skill adapters."; \
		exit 1; \
	fi
	$(call link_skill_adapter,$(HOME_DIR)/.opencode/skills)
	$(call link_skill_adapter,$(HOME_DIR)/.claude/skills)
	$(call link_skill_adapter,$(HOME_DIR)/.skillport/skills)

sync-skills-to-agents: setup-skill-adapters ## Backward-compatible alias for native skill adapters

check-skill-adapters: ## Verify native skill directories point at .agents/skills
	@bash _scripts/test-skill-adapters.sh
