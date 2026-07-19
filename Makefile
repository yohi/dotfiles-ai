SHELL := /bin/bash

# 1. Base Rules (Provided by parent or local)
-include _mk/core.mk
-include _mk/help.mk

# 2. Variables & Idempotency
-include _mk/variables.mk
-include _mk/setup.mk
-include _mk/idempotency.mk

# 3. Orchestrator (Main Workflow)
include _mk/main.mk

# 4. Component Modules
-include _mk/claude.mk
-include _mk/gemini.mk
-include _mk/codex.mk
-include _mk/opencode.mk
-include _mk/antigravity.mk
-include _mk/skillport.mk
-include _mk/skills-adapters.mk
-include _mk/sync-agents.mk
-include _mk/mcp.mk
-include _mk/ide-cursor.mk
-include _mk/ide-vscode.mk
-include _mk/test.mk
# -include _mk/test-ide-cursor.mk

.PHONY: test sync-agents sync-agents-run
test: lint test-all ## Run all tests

sync-agents: ## Run APM install, compile, generate Antigravity config, and sync agents
	@python3 _scripts/generate_atlassian_auth.py
	@$(MAKE) sync-agents-run

sync-agents-run:
	@if [ -f .env ]; then \
		set -a && . ./.env && set +a && uv run apm install; \
	 else \
		uv run apm install; \
	 fi
	@$(MAKE) setup-skill-adapters
	@if [ -f .env ]; then \
		set -a && . ./.env && set +a && uv run apm compile; \
	 else \
		uv run apm compile; \
	 fi
	@$(MAKE) setup-antigravity
	@$(MAKE) sync-claude
	@$(MAKE) setup-opencode
	@$(MAKE) sync-agents-core
