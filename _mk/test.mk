## [Test] Integrity & Regression Checks
.PHONY: test-integrity
test-integrity: ## Run configuration and rules integrity tests
	@echo "Running configuration integrity tests..."
	@python3 _scripts/test_configs_integrity.py
	@echo "All integrity checks passed!"

.PHONY: test-all
test-all: test-integrity ## Run all tests in the project
	@echo "Running all tests..."
	@bash -c 'shopt -s nullglob; \
	for f in _scripts/test_*.py; do \
		[[ "$$f" == "_scripts/test_configs_integrity.py" ]] && continue; \
		echo "Running python test: $$f"; \
		python3 "$$f" || exit 1; \
	done; \
	for f in _scripts/test-*.sh; do \
		echo "Running bash test: $$f"; \
		bash "$$f" || exit 1; \
	done'
.PHONY: install-hooks
install-hooks: ## Install git hooks (pre-push)
	@echo "Installing git hooks..."
	@chmod +x _scripts/pre-push.sh
	@ln -sfn ../../_scripts/pre-push.sh .git/hooks/pre-push
	@echo "Git hooks installed successfully."
