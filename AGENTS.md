# PROJECT KNOWLEDGE BASE

**Repository:** dotfiles-ai
**Role:** AI agent configuration — Claude Code, OpenAI Codex, Gemini CLI, Opencode, MCP servers, and agent skill definitions

## STRUCTURE

```text
dotfiles-ai/
├── _mk/                         # Makefile sub-targets
│   ├── claude.mk               # Claude Code setup
│   ├── codex.mk                # OpenAI Codex setup
│   ├── gemini.mk               # Gemini CLI setup
│   ├── mcp.mk                  # MCP server setup
│   ├── opencode.mk             # Opencode setup
│   ├── skillport.mk            # Skill port targets
│   ├── superclaude.mk          # SuperClaude framework
│   └── sync-agents.mk          # SSOT sync & meta-prompt injection
├── agent-skills/               # [SSOT] AI agent skill definitions
│   ├── agent-skill-architect/  # Skill architect
│   ├── config-modernizer/      # Config modernizer skill
│   ├── dotfiles-guidelines/    # Dotfiles guidelines skill
│   └── makefile-organization/  # Makefile organization skill
├── agent-commands/             # [SSOT] AI agent slash commands
│   ├── build-skill.md          # /build-skill
│   ├── git-pr-flow.md          # /git-pr-flow
│   └── setup-gh-actions-test-ci.md  # /setup-gh-actions-test-ci
├── global-rules/               # [SSOT] Coding rules & standards
│   ├── MARKDOWN.md             # Markdown guidelines
│   ├── SHELL.md                # Shell script guidelines
│   ├── DOCS_STYLE.md           # Documentation style
│   ├── GIT_STANDARDS.md        # Git standards
│   └── META_PROMPT.md          # Common meta-prompt template
├── claude/                     # Claude Code configuration
│   ├── CLAUDE.md               # Claude context file
│   └── claude-settings.json    # Claude settings
├── codex/                      # OpenAI Codex configuration
│   └── config.toml             # Codex config
├── gemini/                     # Gemini CLI configuration
│   ├── Core/                   # Core settings (personas, etc.)
│   └── supergemini/            # SuperGemini framework
├── opencode/                   # Opencode configuration
│   ├── AGENTS.md               # Opencode-specific agent context
│   ├── commands/               # Custom slash commands
│   ├── skills/                 # Opencode skills
│   └── DOCUMENT/               # Reference documents
├── .skillportrc                # SkillPort CLI configuration
└── Makefile                    # Setup entry point (includes _mk/*.mk)
```

## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** orchestrated by `dotfiles-core`.
All changes MUST comply with the central layout rules. Please refer to the central [ARCHITECTURE.md](https://raw.githubusercontent.com/yohi/dotfiles-core/refs/heads/master/docs/ARCHITECTURE.md) for the full, authoritative rules and constraints.

## THIS COMPONENT — SPECIAL NOTES

- **All tool directories** (`claude/`, `codex/`, `gemini/`, `opencode/`) are deployed to their
  respective config locations (e.g., `~/.config/opencode/`) via Makefile targets using `ln -sfn`.
- **SSOT Principle**: All rules and skills MUST be edited in `agent-skills/` or `global-rules/`.
  Run `make sync-agents` to propagate changes to each agent's config.
- `opencode/AGENTS.md` is a **subdirectory-level** agent context — distinct from this root-level AGENTS.md.
- `_mk/` splits Makefile targets by AI tool (one `.mk` file per tool).
- `agent-skills/` contains reusable skill definitions with `SKILL.md` in each subdirectory.
- `global-rules/` contains coding standards shared across all agents.

## CODE STYLE

- **Documentation / README**: Japanese (日本語)
- **AGENTS.md**: English
- **Commit Messages**: Japanese, Conventional Commits (e.g., `feat: 新機能追加`, `fix: バグ修正`)
- **Shell**: `set -euo pipefail`, dynamic path resolution, idempotent operations

## FORBIDDEN OPERATIONS

Per `opencode.jsonc` (when present), these operations are blocked for agent execution:

- `rm` (destructive file operations)
- `ssh` (remote access)
- `sudo` (privilege escalation)

## SSOT REFERENCES

All agent skills and coding rules are centralized in the following directories.
Refer to these before executing any task.

- **Skills**: `agent-skills/` — Each subdirectory contains a `SKILL.md` with task-specific instructions
- **Coding Rules**: `global-rules/` — MARKDOWN.md, SHELL.md, DOCS_STYLE.md, GIT_STANDARDS.md

<!-- SKILLPORT_START -->
## SkillPort Skills

Skills are reusable expert knowledge that help you complete tasks effectively.
Each skill contains step-by-step instructions, templates, and scripts.

### Workflow

1. **Find a skill** - Check the list below for a skill matching your task
2. **Get instructions** - Run `skillport show <skill-id>` to load full instructions
3. **Follow the instructions** - Execute the steps using your available tools

### Tips

- Skills may include scripts - execute them via the skill's path, don't read them into context
- If instructions reference `{path}`, replace it with the skill's directory path
- When uncertain, check the skill's description to confirm it matches your task

<available_skills>
<skill>
  <name>agent-skill-architect</name>
  <description>Designs and generates best-practice-compliant SKILL.md files for OpenCode agent skills. Use when creating new agent skills, drafting skill definitions, or improving existing skill files. Guides through requirements discovery and outputs production-ready SKILL.md with proper YAML frontmatter, XML-structured instructions, and progressive disclosure patterns.</description>
  <location>agent-skills/agent-skill-architect/SKILL.md</location>
</skill>
<skill>
  <name>config-modernizer</name>
  <description>OpenCodeの設定ファイルを分析し、最新のベストプラクティスやリリース情報に基づいてリファクタリングを行う専門スキル。ユーザーから「設定の最新化」「アップグレード」を求められた際や、.jsonc などの設定ファイルが存在する場合にトリガーされます。</description>
  <location>agent-skills/config-modernizer/SKILL.md</location>
</skill>
<skill>
  <name>dotfiles-guidelines</name>
  <description>Core principles, persona definitions, and command workflows for the dotfiles project. Use when seeking development guidance, selecting an appropriate expert persona (Architect, Developer, Tester, DevOps, Analyst), or following standard project commands (analyze, implement, design, etc.). Ensures consistency, quality, and adherence to project-wide best practices.</description>
  <location>agent-skills/dotfiles-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>git-master</name>
  <description>Gitの操作を安全かつ適切に行うための専門スキル。特に、変更を適切に分割し、Conventional Commitsに従った日本語のコミットメッセージを作成します。</description>
  <location>agent-skills/git-master/SKILL.md</location>
</skill>
<skill>
  <name>makefile-organization</name>
  <description>Guidelines for organizing and maintaining modular Makefiles. Use when refactoring, creating new .mk files, or ensuring consistency across the project's Makefile structure. Covers naming conventions, inclusion order, idempotency management, and error handling for a robust development environment.</description>
  <location>agent-skills/makefile-organization/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/brainstorming</name>
  <description>You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation.</description>
  <location>agent-skills/superpowers/brainstorming/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/dispatching-parallel-agents</name>
  <description>Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies</description>
  <location>agent-skills/superpowers/dispatching-parallel-agents/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/executing-plans</name>
  <description>Use when you have a written implementation plan to execute in a separate session with review checkpoints</description>
  <location>agent-skills/superpowers/executing-plans/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/finishing-a-development-branch</name>
  <description>Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup</description>
  <location>agent-skills/superpowers/finishing-a-development-branch/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/receiving-code-review</name>
  <description>Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation</description>
  <location>agent-skills/superpowers/receiving-code-review/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/requesting-code-review</name>
  <description>Use when completing tasks, implementing major features, or before merging to verify work meets requirements</description>
  <location>agent-skills/superpowers/requesting-code-review/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/subagent-driven-development</name>
  <description>Use when executing implementation plans with independent tasks in the current session</description>
  <location>agent-skills/superpowers/subagent-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/systematic-debugging</name>
  <description>Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes</description>
  <location>agent-skills/superpowers/systematic-debugging/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/test-driven-development</name>
  <description>Use when implementing any feature or bugfix, before writing implementation code</description>
  <location>agent-skills/superpowers/test-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/using-git-worktrees</name>
  <description>Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification</description>
  <location>agent-skills/superpowers/using-git-worktrees/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/using-superpowers</name>
  <description>Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions</description>
  <location>agent-skills/superpowers/using-superpowers/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/verification-before-completion</name>
  <description>Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always</description>
  <location>agent-skills/superpowers/verification-before-completion/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/writing-plans</name>
  <description>Use when you have a spec or requirements for a multi-step task, before touching code</description>
  <location>agent-skills/superpowers/writing-plans/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/writing-skills</name>
  <description>Use when creating new skills, editing existing skills, or verifying skills work before deployment</description>
  <location>agent-skills/superpowers/writing-skills/SKILL.md</location>
</skill>
</available_skills>
<!-- SKILLPORT_END -->
