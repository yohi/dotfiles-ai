# Agent Instructions for dotfiles-ai


## COMPONENT LAYOUT CONVENTION

This repository is part of the **dotfiles polyrepo** managed by [dotfiles-core](https://github.com/yohi/dotfiles-core).

### ⚠️ CRITICAL: SYMBOLIC LINK & STANDALONE USAGE
- **Standalone usage is NOT supported.** 公式にはサポートされていませんが、自己責任での単体使用は可能であり、使用する場合は symbolic links と ARCHITECTURE.md に従い、共通ライブラリ（dotfiles-core）を上書きしないことを前提としてください.
- **Symbolic Links:** This repository relies on symbolic links to `common-mk`. **NEVER** suggest or perform a replacement of these symbolic links with physical files/directories. 
- **SSOT:** Always respect the "Single Source of Truth" principle. Shared logic resides in `dotfiles-core`, and components must remain thin wrappers or specific configurations.
- **Architectural Compliance:** All modifications must adhere to the layout defined in the central [ARCHITECTURE.md](https://github.com/yohi/dotfiles-core/blob/master/docs/ARCHITECTURE.md).

> [!IMPORTANT]
> Please refer to [DOTFILES_COMMON_RULES.md](./DOTFILES_COMMON_RULES.md) for common base rules.
> 
> **Note on Symbolic Links:**
> Several files are symbolic links to an external `common-mk` directory:
> - `DOTFILES_COMMON_RULES.md` -> `../../common-mk/DOTFILES_COMMON_RULES.md`
> - `_mk/core.mk` -> `../../../common-mk/core.mk`
> - `_mk/help.mk` -> `../../../common-mk/help.mk`
>
> If these links appear broken, ensure the `common-mk` repository is placed at the correct relative path as specified in [README.md](./README.md#-単体使用時の注意点).

## 1. Hierarchy & Authority
- **Global Rules (`global-rules/AGENTS.global.md`)**: The **Global Foundation**. It contains universal instructions shared across *all* projects, such as Identity, Language Policy (Japanese output), Security protocols, and cross-project SkillPort workflows.
- **Project Rules (`AGENTS.md`)**: The **Local Constitution** (This file). It contains project-specific mandates, architectural decisions, and directory structures unique to this repository. Local project rules take precedence over global rules if a conflict occurs.
- **Sub-directory Rules**: Highly specific overrides for individual agents or components (e.g., `opencode/AGENTS.md`).

## 2. Project Purpose
This repository is the Central Authority for AI Agent configurations, specialized skills, and AI-enabled development environments. It ensures a consistent "AI persona" across all tools and machines.

### 💡 Core Design Philosophy: Separation of Concerns
We strictly separate **"AI Rules & Behavior"** (`dotfiles-ai`) from **"IDE Infrastructure & UI"** (`dotfiles-ide`).
- **`dotfiles-ide`** manages the physical editor settings (`settings.json`, `keybindings.json`, visual themes) for both Cursor and VSCode.
- **`dotfiles-ai`** (this repository) manages the mind and tools of the AI (`mcp.json`, `supercursor`/`supercopilot` framework, Agent instructions, SkillPort).
Never mix IDE styling configurations here, and never put AI instructions or MCP configs in `dotfiles-ide`.

## 3. Directory Mandates
- `claude/`, `gemini/`, `opencode/`, `codex/`: High-level configuration for specific AI CLI tools.
- `ide/`: AI-specific configurations (MCP, SuperCursor/SuperCopilot) for Cursor and VSCode. (UI settings are moved to `dotfiles-ide`).
- `global-rules/`: Source of Truth for cross-project AI instructions.
- `agent-skills/`: The master repository for SkillPort skills.
- `mcp/`: Management of the Docker MCP Gateway and associated catalogs.

## 4. Development Workflow
- **SSOT Enforcement**: Never edit symlinked files in home directories (e.g., `~/.gemini/GEMINI.md`). Always edit the Source of Truth within this repository.
- **MCP Gateway**: Use the Unified SSE Gateway (`http://localhost:10888/sse`) for all tools. New MCP servers MUST be defined in `mcp/catalogs/custom.yaml.template`.
- **Skill Management**: New AI capabilities MUST be implemented as SkillPort skills in `agent-skills/` and managed via MCP.

## 5. Tooling & Automation
- `make setup`: Bootstrap the environment and create initial symlinks.
- `make setup-docker-mcp`: Re-render MCP configurations and synchronize all agents.
- `make sync-agents`: Propagate global rules and skill updates to all agent contexts.

<!-- SKILLPORT_START -->
## SkillPort Skills

Skills are reusable expert knowledge that help you complete tasks effectively.
Each skill contains step-by-step instructions, templates, and scripts.

### Workflow

1. **Search** - Call `search_skills(query)` to find skills matching your task
2. **Load** - Call `load_skill(skill_id)` to get full instructions and `path`
3. **Execute** - Follow the instructions using your available tools

### Tools

- `search_skills(query)` - Find skills by task description. Use `""` to list all.
- `load_skill(id)` - Get full instructions and the skill's filesystem path.

### Tips

- Use your native Read tool with `{path}/file` for templates/assets
- Replace `{path}` in instructions with the actual path from `load_skill`
- If search returns too many results, use more specific terms

<available_skills>
<skill>
  <name>agent-skill-architect</name>
  <description>Designs and generates best-practice-compliant SKILL.md files for OpenCode agent skills. Use when creating new agent skills, drafting skill definitions, or improving existing skill files. Guides through requirements discovery and outputs production-ready SKILL.md with proper YAML frontmatter, XML-structured instructions, and progressive disclosure patterns.</description>
  <location>agent-skills/agent-skill-architect/SKILL.md</location>
</skill>
<skill>
  <name>config-modernizer</name>
  <description>A specialized skill for analyzing OpenCode configuration files and performing refactoring based on the latest best practices and release information. Triggered when requested for "configuration modernization" or "upgrading", or when configuration files like .jsonc are present.</description>
  <location>agent-skills/config-modernizer/SKILL.md</location>
</skill>
<skill>
  <name>dotfiles-guidelines</name>
  <description>Core principles, persona definitions, and command workflows for the dotfiles project. Use when seeking development guidance, selecting an appropriate expert persona (Architect, Developer, Tester, DevOps, Analyst), or following standard project commands (analyze, implement, design, etc.). Ensures consistency, quality, and adherence to project-wide best practices.</description>
  <location>agent-skills/dotfiles-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>git-master</name>
  <description>A specialized skill for performing Git operations safely and appropriately. Particularly focuses on splitting changes correctly and creating Japanese commit messages following Conventional Commits.</description>
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

## BEGIN Superpowers Workflow
# Superpowers Workflow (Adaptive Application)
This project employs the [obra/superpowers](https://github.com/obra/superpowers) workflow. While its principles are mandatory, its execution MUST be **tailored to the task's complexity** to balance rigor and efficiency.

## Core Mandate: "Think, Plan, Verify"
Regardless of task size, you MUST adhere to the core philosophy:
1.  **Research & Design:** Understand context and constraints before acting (`superpowers/brainstorming`).
2.  **Structured Planning:** Define steps before execution (`superpowers/writing-plans`).
3.  **Empirical Verification:** Confirm outcomes with evidence (`superpowers/verification-before-completion`).

## Adaptive Execution Levels

### 1. High Intensity (New Features / Complex Bug Fixes / Architecture)
**Full adherence is MANDATORY.**
- **Workflow:** `superpowers/brainstorming` → `superpowers/writing-plans` → `superpowers/test-driven-development` → `superpowers/verification-before-completion`.
- **Requirement:** Detailed design docs, multi-checkpoint plans, and pre-implementation test cases.

### 2. Medium Intensity (Improvements / Refactoring / Moderate Logic Changes)
**Streamlined execution.**
- **Workflow:** Combined (Brainstorm/Plan) → Implementation → `superpowers/verification-before-completion`.
- **Requirement:** A clear, concise implementation plan. TDD is recommended for core logic but can be adapted for non-critical paths.

### 3. Low Intensity (Trivial Fixes / Documentation / Config Typos)
**Rapid response.**
- **Workflow:** Brief mental model check → Direct Act → Immediate Verification.
- **Requirement:** Formal skills may be skipped for speed, but the final state MUST be verified and reported.

## Skill Integration (SkillPort)
- **Tool-First:** AI agents MUST use the `load_skill` (MCP) tool as the primary method for loading expert guidance. Direct file path reads or direct access to skill files are strictly forbidden during runtime and for Pull Requests.
- **CLI Fallback:** Use `skillport show` only for manual operations or in non-MCP environments where specifically instructed.
## END Superpowers Workflow

## 単体使用時の注意点

公式にはサポートされていませんが、自己責任での単体使用は可能であり、使用する場合は symbolic links と ARCHITECTURE.md に従い、共通ライブラリ（dotfiles-core）を上書きしないことを前提としてください.
