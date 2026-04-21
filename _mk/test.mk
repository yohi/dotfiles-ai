## [Test] Integrity & Regression Checks
.PHONY: test-integrity
test-integrity: ## Run configuration and rules integrity tests
	@echo "Running configuration integrity tests..."
	@python3 _scripts/test_configs_integrity.py
	@echo "All integrity checks passed!"

.PHONY: test-all
test-all: test-integrity ## Run all tests in the project
	@echo "Running all tests..."
	@# Add other test commands here if needed
	@ls _scripts/test_*.py | xargs -n 1 python3
	@ls _scripts/test-*.sh | xargs -n 1 bash
