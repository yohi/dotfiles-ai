# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository contains Cursor IDE configuration files and custom slash commands for enhanced development workflows. It serves as a centralized configuration management system for Cursor IDE settings and MCP (Model Context Protocol) server configurations.

## Architecture

### Configuration Structure

```text
ide/cursor/
├── settings.json           # Cursor IDE settings
├── keybindings.json        # Custom keybindings
├── mcp.json                # Generated MCP config (from mcp/servers.yaml)
└── commands/               # Custom slash commands
    ├── coderabbit/         # CodeRabbit CLI commands
    └── agent/              # Agent development commands
```

### MCP Server Integration

This repository manages multiple MCP server configurations:

**Generated Configuration** (`mcp.json`):

- Rendered from the repository-wide SSOT: `mcp/servers.yaml`
- Points Cursor directly at the local Docker MCP Gateway SSE endpoint
- Refreshed by `make sync-mcp`

### Custom Slash Commands

#### CodeRabbit CLI Commands (`commands/coderabbit/`)

AI-powered code review commands requiring [CodeRabbit CLI](https://docs.coderabbit.ai/cli/overview):

**Available Commands**:

- `/coderabbit-review` - Comprehensive code review (all files)
- `/quick-cr-review` - Fast review of uncommitted changes only
- `/security-cr-audit` - Security vulnerability audit
- `/performance-cr-review` - Performance optimization analysis

#### Agent Development Commands (`commands/agent/`)

Specialized commands for managing AI agents and skills:

**Available Commands**:

- `/build-skill` - Interactively design and generate `SKILL.md` files
- `/git-pr-flow` - Manage Git workflow from branch creation to PR
- `/setup-gh-actions-test-ci` - Set up GitHub Actions for CI/CD with tests

## Configuration Management

### MCP Server Configuration

**Syncing Configuration**:

```bash
# Re-render Cursor MCP config from the centralized SSOT
make sync-mcp
```

### Settings Synchronization

Key settings in `settings.json`:

- Editor: 4 spaces (Python), 2 spaces (JS/TS/JSON/YAML)
- Format on save enabled for all languages
- Font: Cica Nerd Font with Noto Sans CJK JP fallback
- Git: Smart commit enabled, auto-fetch on
- Python: Black formatter, flake8+mypy linting
- Search excludes: node_modules, .git, dist, build, .venv, __pycache__, .cursor

## Development Patterns

### CodeRabbit Integration

CodeRabbit CLI is integrated with Claude Code for autonomous development:

1. **Problem Detection**: Run CodeRabbit review commands
2. **AI Analysis**: CodeRabbit generates prompts optimized for Claude Code
3. **Automatic Fixing**: Claude Code implements fixes based on analysis
4. **Verification**: Re-run CodeRabbit to verify fixes

## Common Tasks

### Setting Up New MCP Server

```bash
# 1. Update mcp/servers.yaml
# 2. Run make sync-mcp
# 3. Restart Cursor IDE to load new configuration
```

### Running CodeRabbit Review

```bash
# Quick review before commit
/quick-cr-review

# Full project review
/coderabbit-review
```

## Notes

- MCP server configuration is centralized in `mcp/servers.yaml` and rendered via `make sync-mcp`
- CodeRabbit requires authentication and Git repository context
- Settings are optimized for Japanese development (fonts, language support)
