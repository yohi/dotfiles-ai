REPO_ROOT ?= $(CURDIR)
.DEFAULT_GOAL := setup
include _mk/claude.mk
include _mk/gemini.mk
include _mk/codex.mk
include _mk/opencode.mk
include _mk/superclaude.mk
include _mk/skillport.mk
include _mk/mcp.mk
.PHONY: setup
setup:
	@echo "==> Setting up dotfiles-ai"
