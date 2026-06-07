## [Test] Integrity & Regression Checks
.PHONY: test-integrity
test-integrity: ## Run configuration and rules integrity tests
	@echo "Running configuration integrity tests..."
	@if command -v uv > /dev/null 2>&1; then \
		uv run python3 _scripts/test_configs_integrity.py; \
	else \
		python3 _scripts/test_configs_integrity.py; \
	fi
	@echo "All integrity checks passed!"

.PHONY: test-mcp-connectivity
test-mcp-connectivity: ## Check MCP connectivity for all CLI tools
	@chmod +x _scripts/test-mcp-connectivity.sh
	@./_scripts/test-mcp-connectivity.sh

.PHONY: test-all
test-all: test-integrity ## Run all tests in the project
	@echo "Running all tests..."
	@bash -c 'shopt -s nullglob; \
		PYTHON_CMD="python3"; \
		if command -v uv > /dev/null 2>&1; then PYTHON_CMD="$(PYTHON) python3"; fi; \
		for f in _scripts/test_*.py; do \
			[[ "$$f" == "_scripts/test_configs_integrity.py" ]] && continue; \
			echo "Running python test: $$f"; \
			$$PYTHON_CMD "$$f" || exit 1; \
		done; \
		# This glob picks up _scripts/test-skill-adapters.sh automatically. \
		for f in _scripts/test-*.sh; do \
			[[ "$$f" == "_scripts/test-mcp-connectivity.sh" ]] && continue; \
			echo "Running bash test: $$f"; \
			bash "$$f" || exit 1; \
		done'
	@echo "Running pytest suite..."
	@if command -v uv > /dev/null 2>&1; then \
		PYTHONPATH=. uv run pytest tests/ || exit 1; \
	else \
		PYTHONPATH=. pytest tests/ || exit 1; \
	fi
	@echo "✅ All tests passed!"

install-hooks: ## Install git hooks (pre-push)
	@echo "Installing git hooks..."
	@chmod +x _scripts/pre-push.sh
	@ln -sfn ../../_scripts/pre-push.sh .git/hooks/pre-push
	@echo "Git hooks installed successfully."
