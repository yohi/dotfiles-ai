# Load environment variables from .env if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

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

# APM Installation
APM_INSTALL_URL := https://aka.ms/apm-unix
APM_INSTALLER_HASH := bdc06da2875547a55167bcb3eecb6aa7e5bdf264c4799e72be91d7641940aee7

# Opcode (Claude Code GUI) Version Detection
# Uses GitHub API to get the latest tag name (vX.Y.Z) and strips the 'v'
OPCODE_LATEST_TAG = $(shell curl -fS --max-time 10 --retry 3 https://api.github.com/repos/winfunc/opcode/releases/latest 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/' || echo "$${ENV_OPC_TAG:-v0.2.0}")
OPCODE_VERSION = $(shell echo $(OPCODE_LATEST_TAG) | sed 's/^v//')

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
AGENT_CUSTOM_SKILLS_DIR := $(AGENT_SKILLS_DIR)/custom
RUNTIME_SKILLS_DIR := $(REPO_ROOT)/.agents/skills
RUNTIME_CUSTOM_SKILLS_DIR := $(RUNTIME_SKILLS_DIR)/custom
