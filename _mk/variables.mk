# Global Variables
REQUIRE_NODEJS := 1
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON := uv run --with-requirements requirements.txt

# Path Configuration
export PATH := $(HOME)/.npm-global/bin:$(HOME)/.bun/bin:$(HOME)/.local/bin:$(PATH)
export NPM_CONFIG_PREFIX := $(HOME)/.npm-global

# Verbosity control
QUIET ?= 0

# OS detection
OS_NAME := $(shell uname -s)

# Helper for conditional echo
ifeq ($(QUIET),1)
  Q_ECHO = @:
else
  Q_ECHO = @echo
endif

# Macro to show guide from Markdown file
# Usage: $(call show-guide,path,fallback_message)
define show-guide
	@if [ -f "$(1)" ]; then \
		cat "$(1)"; \
	else \
		msg="$(2)"; \
		echo "$${msg:-⚠️  ガイドファイルが見つかりません: $(1)}"; \
	fi
endef

# Common paths
HOME_DIR := $(HOME)
REPO_ROOT := $(CURDIR)
GLOBAL_RULES_DIR := $(REPO_ROOT)/global-rules
AGENT_SKILLS_DIR := $(REPO_ROOT)/agent-skills
