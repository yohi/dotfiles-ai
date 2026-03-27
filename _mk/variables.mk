# Global Variables
REQUIRE_NODEJS := 1
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON := uv run --with-requirements requirements.txt

# Phony Targets
.PHONY: all help setup install clean link install-agents install-ides setup-agents setup-ides mcp-render test lint
