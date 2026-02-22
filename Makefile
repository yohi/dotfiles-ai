REPO_ROOT ?= $(CURDIR)
.DEFAULT_GOAL := setup

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
include _mk/claude.mk
include _mk/gemini.mk
include _mk/codex.mk
include _mk/opencode.mk
include _mk/superclaude.mk
include _mk/skillport.mk
include _mk/sync-agents.mk
include _mk/mcp.mk

.PHONY: setup clean link

setup:
	@echo "==> Setting up dotfiles-ai"
	$(MAKE) claude
	$(MAKE) gemini
	$(MAKE) codex
	$(MAKE) opencode
	$(MAKE) superclaude
	$(MAKE) skillport
	$(MAKE) mcp
	$(MAKE) sync-agents

link:
	@echo "==> Linking dotfiles-ai (Handled in setup targets)"

clean:
	@echo "==> Cleaning up dotfiles-ai"
	-$(MAKE) uninstall-superclaude
	-$(MAKE) uninstall-claude
	-$(MAKE) uninstall-gemini
	-$(MAKE) uninstall-codex
	-$(MAKE) uninstall-opencode
	-$(MAKE) uninstall-skillport
	-$(MAKE) uninstall-mcp
