REPO_ROOT ?= $(CURDIR)
.DEFAULT_GOAL := setup

REQUIRE_NODEJS := 1
include _mk/idempotency.mk
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
include _mk/superpowers.mk
include _mk/ide-cursor.mk
include _mk/ide-vscode.mk

.PHONY: setup install clean link install-agents install-ides setup-agents setup-ides

install: install-agents install-ides ## Install all AI agents and IDE binaries

install-agents:
	@echo "==> Installing dotfiles-ai agent binaries"
	$(MAKE) install-packages-claude-code
	$(MAKE) install-packages-gemini-cli
	$(MAKE) install-packages-codex
	$(MAKE) install-packages-opencode

install-ides:
	@echo "==> Installing dotfiles-ai IDE tools"
	$(MAKE) install-packages-cursor
	$(MAKE) install-supercopilot

setup: setup-agents setup-ides ## Setup all AI agents and IDE configurations

setup-agents:
	@echo "==> Setting up dotfiles-ai agent configurations"
	$(MAKE) setup-claude
	$(MAKE) setup-supergemini
	$(MAKE) setup-codex
	$(MAKE) setup-opencode
	$(MAKE) setup-docker-mcp
	$(MAKE) setup-superpowers
	$(MAKE) sync-agents

setup-ides:
	@echo "==> Setting up dotfiles-ai IDE configurations"
	$(MAKE) setup-cursor
	$(MAKE) setup-vscode

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
	-$(MAKE) uninstall-superpowers
	-$(MAKE) uninstall-cursor
	-$(MAKE) uninstall-vscode
