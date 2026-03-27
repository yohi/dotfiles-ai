# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository contains Cursor IDE configuration files and custom slash commands for enhanced development workflows. It serves as a centralized configuration management system for Cursor IDE settings, MCP (Model Context Protocol) server configurations, and specialized development commands.

## Architecture

### Configuration Structure

```text
ide/cursor/
├── settings.json           # Cursor IDE settings
├── keybindings.json        # Custom keybindings
├── mcp.json                # Generated MCP config (from mcp/servers.yaml)
├── commands/               # Custom slash commands
│   └── coderabbit/         # CodeRabbit CLI commands
└── supercursor/            # SuperCursor framework (gitignored)
    ├── Commands/           # Framework commands
    ├── Core/               # Core framework components
    └── Hooks/              # Development hooks
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

**Common Usage Patterns**:

```bash
# Daily development cycle
/quick-cr-review              # Before commit
/coderabbit-review            # After feature completion
/security-cr-audit            # Before PR creation
/performance-cr-review        # When performance issues detected

# Commands use these CLI flags internally:
--prompt-only                 # Optimized for AI agent integration
--type uncommitted            # Only uncommitted changes
--type all                    # All changes (committed + uncommitted)
--base master                   # Compare against master branch
--plain                       # Detailed feedback mode
```

#### Kiro Spec-Driven Development (`supercursor/Commands/kiro/`)

Specification-driven development workflow commands:

**Workflow Commands**:

- `/kiro:steering` - Create/update project steering documents
- `/kiro:steering-custom` - Create custom steering for specialized contexts
- `/kiro:spec-init [description]` - Initialize new specification
- `/kiro:spec-requirements [feature]` - Generate requirements document
- `/kiro:spec-design [feature]` - Create technical design (requires requirements approval)
- `/kiro:spec-tasks [feature]` - Generate implementation tasks (requires design approval)
- `/kiro:spec-impl [feature] [task-numbers]` - Execute spec tasks using TDD
- `/kiro:spec-status [feature]` - Check specification status and progress
- `/kiro:validate-gap [feature]` - Analyze implementation gap
- `/kiro:validate-design [feature]` - Interactive technical design review

**Development Workflow**:

1. (Optional) `/kiro:steering` - Set project context
2. `/kiro:spec-init` - Initialize specification
3. `/kiro:spec-requirements` - Define requirements
4. `/kiro:spec-design` - Create technical design
5. `/kiro:spec-tasks` - Generate implementation tasks
6. `/kiro:spec-impl` - Execute tasks with TDD
7. `/kiro:spec-status` - Track progress

### SuperCursor Framework

The SuperCursor framework (gitignored but documented here for reference) provides enhanced Cursor capabilities:

**Core Commands**:

- Analysis: `/sc:analyze`, `/sc:explain`
- Development: `/sc:implement`, `/sc:refactor`, `/sc:debug`
- Design: `/sc:design`, `/sc:document`
- Testing: `/sc:test`
- Optimization: `/sc:optimize`, `/sc:review`
- Tools: `/sc:search`, `/sc:build`, `/sc:deploy`
- Support: `/sc:learn`, `/sc:plan`, `/sc:fix`

**Personas**: `@architect`, `@analyst`, `@developer`, `@tester`, `@devops`

**Installation** (if needed):

```bash
cd ide/cursor/supercursor
python -m supercursor install [--interactive|--minimal|--profile developer]
```

## Configuration Management

### MCP Server Configuration

**Syncing Configuration**:

```bash
# Re-render Cursor MCP config from the centralized SSOT
make sync-mcp
```

**Adding New MCP Servers**:

1. Update `mcp/servers.yaml`
2. Run `make sync-mcp`
3. Restart Cursor if needed

**Environment Variables**:

- Keep Gateway/runtime secrets in `.env` only when individual MCP servers need them
- Cursor itself now connects to the local Gateway without the old SSE proxy layer

### Settings Synchronization

Key settings in `settings.json`:

- Editor: 4 spaces (Python), 2 spaces (JS/TS/JSON/YAML)
- Format on save enabled for all languages
- Font: Cica Nerd Font with Noto Sans CJK JP fallback
- Git: Smart commit enabled, auto-fetch on
- Python: Black formatter, flake8+mypy linting
- Search excludes: node_modules, .git, dist, build, .venv, **pycache**, .cursor

## Development Patterns

### CodeRabbit Integration

CodeRabbit CLI is integrated with Claude Code for autonomous development:

1. **Problem Detection**: Run CodeRabbit review commands
2. **AI Analysis**: CodeRabbit generates prompts optimized for Claude Code
3. **Automatic Fixing**: Claude Code implements fixes based on analysis
4. **Verification**: Re-run CodeRabbit to verify fixes

### Specification-Driven Development

The Kiro workflow enforces phased development:

1. **Steering Phase** (Optional): Define project-wide context
2. **Requirements Phase**: Document functional and non-functional requirements
3. **Design Phase**: Create technical design (requires requirements approval)
4. **Tasks Phase**: Break down into implementation tasks (requires design approval)
5. **Implementation Phase**: Execute tasks with TDD methodology

**Approval Gates**:

- Design requires approved requirements
- Tasks require approved design
- Each phase requires human review before proceeding

## Common Tasks

### Setting Up New MCP Server

```bash
# 1. Install the MCP server (if local)
npm install -g @example/mcp-server

# 2. Add configuration to mcp.json
{
  "server-name": {
    "command": "npx",
    "args": ["-y", "@example/mcp-server"],
    "env": {
      "API_KEY": "your-key-here"
    },
    "disabled": false
  }
}

# 3. Restart Cursor IDE to load new configuration
```

### Running CodeRabbit Review

```bash
# Quick review before commit
/quick-cr-review

# Full project review
/coderabbit-review

# Security-focused audit
/security-cr-audit

# Direct CLI usage (if needed)
coderabbit --type uncommitted --prompt-only
coderabbit --base master --plain
```

### Creating New Specification

```bash
# Initialize with detailed description
/kiro:spec-init Create a REST API for user management with JWT authentication

# Follow the workflow
/kiro:spec-requirements user-api
/kiro:spec-design user-api
/kiro:spec-tasks user-api
/kiro:spec-impl user-api 1,2,3
/kiro:spec-status user-api
```

## Notes

- SuperCursor framework is gitignored but can be installed via Python
- MCP server configuration is centralized in `mcp/servers.yaml` and rendered via `make sync-mcp`
- CodeRabbit requires authentication and Git repository context
- Kiro workflow enforces approval gates between phases
- Settings are optimized for Japanese development (fonts, language support)
