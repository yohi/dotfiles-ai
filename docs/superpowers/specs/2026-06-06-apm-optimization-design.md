---
name: apm-optimization
title: APM Configuration and Workflow Optimization
date: 2026-06-06
status: approved
---

# APM Configuration and Workflow Optimization Design Spec

## 1. Background & Objectives
Currently, the `dotfiles-ai` repository manages AI agent configurations using both APM (Agent Package Manager) and a legacy set of Makefile targets/custom shell scripts. This dual setup leads to redundant copies of external skills, complex build steps, and potential desynchronization between different agent configurations (Claude Code, Gemini, Cursor, OpenCode, Codex).

The goal of this optimization is to fully leverage APM's capabilities to manage agent dependencies, compile target configurations, and orchestrate build steps, thereby simplifying the codebase and ensuring high portability and reproducibility.

## 2. Architecture & Detailed Design

### 2.1 Skill Management and Synchronization Flow
* **APM-Centric Deployment**:
  * External skills (e.g., `obra/superpowers`, `anthropics/skills`) listed in `apm.yml` will be installed directly by APM to their respective target directories (e.g., `.agents/skills/` and agent-specific runtime directories).
  * The custom scripts/make targets that copy external skills from `apm_modules/` to `agent-skills/` will be removed.
* **Role of `agent-skills/`**:
  * The [agent-skills/](file:///home/y_ohi/dotfiles/components/dotfiles-ai/agent-skills) directory will strictly house local custom skills (under `agent-skills/custom/`).
  * Legacy folders for external skills (e.g., `agent-skills/anthropics/`, `agent-skills/superpowers/`) will be cleaned up.
* **Skillport MCP Integration**:
  * The `skillport` MCP configuration in `apm.yml` will point `SKILLPORT_SKILLS_DIR` to `${env:PWD}/.agents/skills` instead of `agent-skills`.
  * This allows the Skillport MCP to scan and load both external skills and local custom skills dynamically from a single deployment target.

### 2.2 Compilation and Target Integration
* **APM Target Compilation**:
  * Leverage APM's `targets` compilation (`apm compile`) to generate agent settings.
  * Define post-install/post-compile hooks in `apm.yml` to trigger custom conversion scripts (such as converting markdown commands to Gemini `.toml` files or Codex `.md` rules) automatically.
* **Antigravity Workaround Hook**:
  * Since Antigravity is not natively supported as a compilation target by APM yet, implement a custom post-compile script (`_scripts/sync_antigravity.sh`) that parses the resolved MCP configurations from `apm.lock.yaml` (or `apm.yml`) and outputs the Antigravity-specific [antigravity/mcp_config.json](file:///home/y_ohi/dotfiles/components/dotfiles-ai/antigravity/mcp_config.json).
  * This script will be invoked as a post-compile hook via the Makefile wrapper right after `apm compile`.
* **Instruction Merging**:
  * Use `apm.yml`'s `instructions` and `exports.instructions` configuration to automatically bundle `global-rules/AGENTS.global.md` during agent configuration compilation, avoiding manual symlink creation.

### 2.3 Makefile Simplification
* **Cleanup of Redundant Targets**:
  * Delete `install-external-skills`, `sync-skills-to-agents`, and `uninstall-superpowers` from [_mk/sync-agents.mk](file:///home/y_ohi/dotfiles/components/dotfiles-ai/_mk/sync-agents.mk).
* **Wrapper Implementation**:
  * Redefine `make setup` and `make sync-agents` to run `apm install && apm compile` as the core build sequence.
  * Adjust `clean-sync-artifacts` to purge leftover dual-management files.

## 3. Verification & Testing Plan
* **Dry-Run Installation**:
  * Run `apm install` and verify files are correctly deployed under `.agents/skills/`.
* **Skillport Verification**:
  * Run `skillport list` and check if both custom and external skills are properly scanned and listed.
* **Target Configuration Verification**:
  * Confirm that configurations for Claude Code (`.claude/`), Gemini (`gemini/`), Cursor (`.cursor/rules/`), and OpenCode (`opencode/`) are successfully compiled and functional.
  * Confirm that `antigravity/mcp_config.json` is correctly generated and populated with matching MCP server configurations.
