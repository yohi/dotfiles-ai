.PHONY: init-env setup-apm-env

setup-apm-env: ## .env ファイルの雛形作成（初回のみ）
	@if [ ! -f .env ]; then \
		cp .env.example .env && \
		chmod 600 .env && \
		echo "✓ Created .env from .env.example"; \
	else \
		echo "✓ .env already exists"; \
	fi

init-env: ## Interactive setup for .env file based on .env.example
	@python3 _scripts/setup_env.py

.PHONY: install-ollama
install-ollama: ## Install Ollama using official script
	@echo "🦙 Installing Ollama..."
	@tmpfile=$$(mktemp); \
	curl -fsSL https://ollama.com/install.sh -o "$$tmpfile"; \
	sh "$$tmpfile"; \
	rm -f "$$tmpfile"
