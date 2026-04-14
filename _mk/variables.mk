# Global Variables
REQUIRE_NODEJS := 1
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON := uv run --with-requirements requirements.txt

# Verbosity control
QUIET ?= 0

# Helper for conditional echo
ifeq ($(QUIET),1)
  Q_ECHO = @:
else
  Q_ECHO = @echo
endif

# Macro to show guide from Markdown file
# Usage: $(call show-guide,_docs/guides/xxx.md)
define show-guide
	@if [ -f "$(1)" ]; then \
		cat "$(1)"; \
	else \
		echo "⚠️  ガイドファイルが見つかりません: $(1)"; \
	fi
endef

# Common paths
HOME_DIR := $(HOME)
REPO_ROOT := $(CURDIR)
GLOBAL_RULES_DIR := $(REPO_ROOT)/global-rules
AGENT_SKILLS_DIR := $(REPO_ROOT)/agent-skills
