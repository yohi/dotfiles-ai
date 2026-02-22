REPO_ROOT ?= $(CURDIR)
.DEFAULT_GOAL := setup
include _mk/claude.mk
include _mk/gemini.mk
include _mk/codex.mk
include _mk/opencode.mk
include _mk/superclaude.mk
include _mk/skillport.mk
include _mk/sync-agents.mk
include _mk/mcp.mk

.PHONY: setup
setup:
	@echo "==> Setting up dotfiles-ai"
	$(MAKE) -f _mk/claude.mk claude
	$(MAKE) -f _mk/gemini.mk gemini
	$(MAKE) -f _mk/codex.mk codex
	$(MAKE) -f _mk/opencode.mk opencode
	$(MAKE) -f _mk/superclaude.mk superclaude
	$(MAKE) -f _mk/skillport.mk skillport
	$(MAKE) -f _mk/mcp.mk mcp
	$(MAKE) sync-agents

.PHONY: link
link:
	@echo "==> Linking dotfiles-ai (Handled in setup targets)"
