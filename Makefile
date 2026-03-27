override REPO_ROOT := $(CURDIR)
.DEFAULT_GOAL := setup

include _mk/variables.mk
include _mk/idempotency.mk
include _mk/claude.mk
include _mk/gemini.mk
include _mk/codex.mk
include _mk/opencode.mk
include _mk/antigravity.mk
include _mk/superclaude.mk
include _mk/skillport.mk
include _mk/sync-agents.mk
include _mk/mcp.mk
include _mk/superpowers.mk
include _mk/ide-cursor.mk
include _mk/ide-vscode.mk



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

setup: setup-agents setup-ides ## Setup all AI agents and IDE configurations

setup-agents:
	@echo "==> Setting up dotfiles-ai agent configurations"
	@if [ ! -d node_modules ]; then \
		if [ -f package-lock.json ]; then \
			npm ci; \
		else \
			npm install; \
		fi \
	fi
	$(MAKE) setup-claude
	$(MAKE) setup-supergemini
	$(MAKE) setup-codex
	$(MAKE) setup-opencode
	$(MAKE) setup-antigravity
	$(MAKE) setup-docker-mcp
	$(MAKE) install-packages-superclaude
	$(MAKE) setup-superpowers
	$(MAKE) sync-agents
	$(MAKE) sync-mcp

setup-ides:
	@echo "==> Setting up dotfiles-ai IDE configurations"
	$(MAKE) setup-cursor
	$(MAKE) setup-vscode

mcp-render:
	@sed "s|__HOME__|$(HOME)|g" mcp/catalogs/custom.yaml.template > mcp/catalogs/custom.yaml

link:
	@echo "==> Linking dotfiles-ai (Handled in setup targets)"

clean:
	@echo "==> Cleaning up dotfiles-ai"
	-$(MAKE) uninstall-superclaude
	-$(MAKE) uninstall-claude
	-$(MAKE) uninstall-gemini
	-$(MAKE) uninstall-codex
	-$(MAKE) uninstall-opencode
	-$(MAKE) uninstall-antigravity
	-$(MAKE) uninstall-skillport
	-$(MAKE) uninstall-mcp
	-$(MAKE) uninstall-superpowers
	-$(MAKE) uninstall-cursor FORCE=true
	-$(MAKE) uninstall-vscode FORCE=true

lint:
	@echo "==> Running Ruff and Mypy on scripts/"
	ruff check scripts/
	mypy scripts/
