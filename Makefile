REPO_ROOT ?= $(CURDIR)
.DEFAULT_GOAL := setup
include mk/claude.mk
include mk/gemini.mk
include mk/codex.mk
include mk/opencode.mk
include mk/superclaude.mk
include mk/skillport.mk
include mk/mcp.mk
.PHONY: setup
setup:
	@echo "==> Setting up dotfiles-ai"
