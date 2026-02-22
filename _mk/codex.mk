.PHONY: codex install-packages-codex install-codex codex-update codex-setup

codex: ## Install and setup Codex CLI
	@if command -v codex >/dev/null 2>&1 && [ -L "$(HOME_DIR)/.codex" ] && [ -f "$(REPO_ROOT)/codex/config.toml" ]; then \
		echo "$(call IDEMPOTENCY_SKIP_MSG,codex)"; \
		exit 0; \
	fi
	@$(MAKE) install-packages-codex codex-setup

install-packages-codex: ## Install Codex CLI using npm
	@echo "Uninstalling existing Codex CLI (if any)..."
	@npm uninstall -g @openai/codex 2>/dev/null || true
	@echo "Installing Codex CLI via npm..."
	@npm install -g @openai/codex

codex-update: ## Update Codex CLI using npm
	@echo "Updating Codex CLI via npm..."
	@npm update -g @openai/codex

codex-setup: ## Setup Codex CLI configuration
	@echo "Setting up Codex CLI configuration..."
	@mkdir -p $(REPO_ROOT)/codex
	@if [ ! -f "$(REPO_ROOT)/codex/config.toml" ]; then \
		echo "Creating default config file at $(REPO_ROOT)/codex/config.toml"; \
		printf '%s\n' \
			'# OpenAI Codex CLI Configuration' \
			'#' \
			'# For more information on configuration options, see the official documentation.' \
			'' \
			'# Set the default model to use for requests.' \
			'# model = "gpt-5"' \
			'' \
			'# Set the approval mode. Options are: suggest, auto-edit, full-auto' \
			'# approval_policy = "on-request"' \
			'' \
			'# You can also configure a different model provider, like Ollama' \
			'# model_provider = "ollama"' \
			> $(REPO_ROOT)/codex/config.toml; \
	fi
	@echo "Creating symbolic link: $(HOME_DIR)/.codex -> $(REPO_ROOT)/codex"
	@if [ -d "$(HOME_DIR)/.codex" ] && [ ! -L "$(HOME_DIR)/.codex" ]; then \
		backup_dir="$(HOME_DIR)/.codex.backup.$$(date +%s)"; \
		echo "Moving existing directory to backup: $$backup_dir"; \
		mv "$(HOME_DIR)/.codex" "$$backup_dir"; \
	fi
	@ln -sfn $(REPO_ROOT)/codex $(HOME_DIR)/.codex
	@echo "Codex CLI setup complete."

# User-friendly alias
install-codex: install-packages-codex


