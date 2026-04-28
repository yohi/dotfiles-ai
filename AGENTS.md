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
- **`dotfiles-ai`** (this repository) manages the mind and tools of the AI (`mcp.json`, Agent instructions, SkillPort).
Never mix IDE styling configurations here, and never put AI instructions or MCP configs in `dotfiles-ide`.

## 3. Directory Mandates
- `claude/`, `gemini/`, `opencode/`, `codex/`: High-level configuration for specific AI CLI tools.
- `ide/`: AI-specific configurations (MCP) for Cursor and VSCode. (UI settings are moved to `dotfiles-ide`).
- `global-rules/`: Source of Truth for cross-project AI instructions.
- `agent-skills/`: The master repository for SkillPort skills.
- `mcp/`: Management of the Docker MCP Gateway and associated catalogs.

## 4. Development Workflow
- **SSOT Enforcement**: Never edit symlinked files in home directories (e.g., `~/.gemini/GEMINI.md`). Always edit the Source of Truth within this repository.
- **MCP Gateway**: Use the **Unified SSE Gateway (`http://localhost:10888/sse`)** as the standard connection method for all tools.
  - **SSOT Principle**: **`apm.yml`** is the master manifest for the project. **APM** stands for **Microsoft APM (Agent Package Manager)**. **`mcp/servers.yaml`** is the Source of Truth for Gateway-side MCP configurations. `mcp/config.yaml` is auto-generated from it via APM's `post_install` hook.
  - **Benefits of SSE Integration**:
    - **Zero-second Startup**: Since the Gateway is not launched individually for each agent session, initialization delays (typically 7-10s) and timeouts/hangs are completely eliminated.
    - **Resource Stability**: Prevents "too many open files" errors and Docker container conflicts common with the stdio transport method.
    - **APM Integration**: `apm install` automatically injects the Gateway SSE endpoint into all detected AI clients.
  - **Maintenance**: The gateway runs as a background service (`docker-mcp-gateway.service`), and the `mcp-watchdog.service` ensures automatic recovery in case of hangs.
- **Skill Management**: New AI capabilities MUST be implemented as SkillPort skills in `agent-skills/` and managed via MCP.
- **External Skills (APM)**: High-quality external skills (like `superpowers/`) are managed via `apm.yml`. They are automatically synchronized using `apm install` or `make setup`. This prevents duplicating external code while maintaining version consistency.

## 5. Tooling & Automation
- `make setup`: Bootstrap the environment and run `apm install`. (This triggers `sync-agents` and executes APM's `post_install` hooks).
- `make setup-docker-mcp`: Bootstrap Docker MCP Gateway service files and runtime environment.
- `make sync-mcp`: Re-render Gateway backend configuration and restart the service. (Executed automatically by `apm install`, but can be run manually after updating `mcp/servers.yaml`).

## 6. MCP Gateway Advanced Configuration

When managing custom command-based MCP servers (e.g., `uv tool run`) using `docker-mcp-gateway`, please note the following technical requirements and workarounds.

### ⚠️ Constraints and Workarounds for Custom Servers
1.  **Mandatory `image` Field (No Host Execution)**: 
    The Docker MCP Gateway **always** executes servers within isolated Docker containers; it cannot execute commands directly on the host machine. When defining a command-based server (e.g., `uvx` or `npx`) in the catalog, you MUST specify a valid Docker image that contains the required execution environment (e.g., `ghcr.io/astral-sh/uv:python3.12-bookworm` for Python/uv, or `node:lts-slim` for Node/npx). Do NOT use a dummy placeholder image, as the command will fail if the dependencies (like `uv` or `git`) are missing inside the container.
2.  **Manual Registration in `registry.yaml`**:
    If a custom server in the catalog is not automatically detected, force its recognition by manually adding an entry to `~/.docker/mcp/registry.yaml`:
    ```yaml
    registry:
      your-server-name:
        ref: ""
    ```
3.  **Environment Variables & Volume Mounts**:
    Host-side tools often require specific environment variables and filesystem access. Explicitly map these using the `env` and `volumes` sections in `mcp/catalogs/custom.yaml.template`.

### 🛠️ Troubleshooting: "too many open files"
A `too many open files` error in the gateway logs usually indicates resource exhaustion from orphaned MCP containers. Cleanup all managed containers using:
```bash
docker ps -q --filter "label=docker-mcp=true" | xargs -r docker stop
docker container prune -f --filter "label=docker-mcp=true"
```

### 📚 References
- [MCP Client 設定ガイド (Unified SSE Gateway)](./_docs/mcp-settings.md)
- [Docker MCP Gateway: Getting Started](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
- [Docker MCP Gateway: FAQs & Troubleshooting](https://docs.docker.com/ai/mcp-catalog-and-toolkit/faqs/)
- [GitHub: docker/mcp-gateway (Lifecycle Management)](https://github.com/docker/mcp-gateway#overview)
- [Community Guide: Advanced Docker MCP Gateway Usage](https://qiita.com/moritalous/items/8789a37b7db451cc1dba)

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
  <location>__REPO_ROOT__/agent-skills/agent-skill-architect/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/algorithmic-art</name>
  <description>Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields, or particle systems. Create original algorithmic art rather than copying existing artists' work to avoid copyright violations.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/algorithmic-art/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/brand-guidelines</name>
  <description>Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatting, or company design standards apply.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/brand-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/canvas-design</name>
  <description>Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/canvas-design/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/doc-coauthoring</name>
  <description>Guide users through a structured workflow for co-authoring documentation. Use when user wants to write documentation, proposals, technical specs, decision docs, or similar structured content. This workflow helps users efficiently transfer context, refine content through iteration, and verify the doc works for readers. Trigger when user mentions writing docs, creating proposals, drafting specs, or similar documentation tasks.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/doc-coauthoring/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/docx</name>
  <description>Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/docx/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/frontend-design</name>
  <description>Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/frontend-design/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/internal-comms</name>
  <description>A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal communications (status reports, leadership updates, 3P updates, company newsletters, FAQs, incident reports, project updates, etc.).</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/internal-comms/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/mcp-builder</name>
  <description>Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/mcp-builder/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/pdf</name>
  <description>Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/pdf/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/pptx</name>
  <description>Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions "deck," "slides," "presentation," or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/pptx/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/skill-creator</name>
  <description>Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/skill-creator/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/slack-gif-creator</name>
  <description>Knowledge and utilities for creating animated GIFs optimized for Slack. Provides constraints, validation tools, and animation concepts. Use when users request animated GIFs for Slack like "make me a GIF of X doing Y for Slack."</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/slack-gif-creator/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/theme-factory</name>
  <description>Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/theme-factory/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/web-artifacts-builder</name>
  <description>Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/web-artifacts-builder/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/webapp-testing</name>
  <description>Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/webapp-testing/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/xlsx</name>
  <description>Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., adding columns, computing formulas, formatting, charting, cleaning messy data); create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path — even casually (like "the xlsx in my downloads") — and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files (malformed rows, misplaced headers, junk data) into proper spreadsheets. The deliverable must be a spreadsheet file. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved.</description>
  <location>__REPO_ROOT__/agent-skills/anthropics/xlsx/SKILL.md</location>
</skill>
<skill>
  <name>config-modernizer</name>
  <description>A specialized skill for analyzing OpenCode configuration files and performing refactoring based on the latest best practices and release information. Triggered when requested for "configuration modernization" or "upgrading", or when configuration files like .jsonc are present.</description>
  <location>__REPO_ROOT__/agent-skills/config-modernizer/SKILL.md</location>
</skill>
<skill>
  <name>doc-sync-verifier</name>
  <description>A specialized skill for verifying document consistency in a multi-phase review pipeline. Use this skill when you need to validate Phase 1 review findings (e.g., from Gemini) against actual project documentation files, applying strict evidence-based judgment without touching source code. Trigger whenever the user provides a review_results block with issue IDs to verify, asks to "裏取り" (fact-check) review findings, or mentions "DocSync Verifier", "整合性検証", "ドキュメント照合", or "指摘事項の検証". Also trigger when the user wants to cross-reference YAML frontmatter, Mermaid diagrams, or Markdown tables between documents.</description>
  <location>__REPO_ROOT__/agent-skills/doc-sync-verifier/SKILL.md</location>
</skill>
<skill>
  <name>dotfiles-guidelines</name>
  <description>Core principles, persona definitions, and command workflows for the dotfiles project. Use when seeking development guidance, selecting an appropriate expert persona (Architect, Developer, Tester, DevOps, Analyst), or following standard project commands (analyze, implement, design, etc.). Ensures consistency, quality, and adherence to project-wide best practices.</description>
  <location>__REPO_ROOT__/agent-skills/dotfiles-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>git-master</name>
  <description>A specialized skill for performing Git operations safely and appropriately. Particularly focuses on splitting changes correctly and creating Japanese commit messages following Conventional Commits.</description>
  <location>__REPO_ROOT__/agent-skills/git-master/SKILL.md</location>
</skill>
<skill>
  <name>makefile-organization</name>
  <description>Guidelines for organizing and maintaining modular Makefiles. Use when refactoring, creating new .mk files, or ensuring consistency across the project's Makefile structure. Covers naming conventions, inclusion order, idempotency management, and error handling for a robust development environment.</description>
  <location>__REPO_ROOT__/agent-skills/makefile-organization/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/brainstorming</name>
  <description>You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation.</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/brainstorming/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/dispatching-parallel-agents</name>
  <description>Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/dispatching-parallel-agents/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/executing-plans</name>
  <description>Use when you have a written implementation plan to execute in a separate session with review checkpoints</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/executing-plans/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/finishing-a-development-branch</name>
  <description>Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/finishing-a-development-branch/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/receiving-code-review</name>
  <description>Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/receiving-code-review/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/requesting-code-review</name>
  <description>Use when completing tasks, implementing major features, or before merging to verify work meets requirements</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/requesting-code-review/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/subagent-driven-development</name>
  <description>Use when executing implementation plans with independent tasks in the current session</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/subagent-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/systematic-debugging</name>
  <description>Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/systematic-debugging/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/test-driven-development</name>
  <description>Use when implementing any feature or bugfix, before writing implementation code</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/test-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/using-git-worktrees</name>
  <description>Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/using-git-worktrees/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/using-superpowers</name>
  <description>Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/using-superpowers/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/verification-before-completion</name>
  <description>Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/verification-before-completion/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/writing-plans</name>
  <description>Use when you have a spec or requirements for a multi-step task, before touching code</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/writing-plans/SKILL.md</location>
</skill>
<skill>
  <name>superpowers/writing-skills</name>
  <description>Use when creating new skills, editing existing skills, or verifying skills work before deployment</description>
  <location>__REPO_ROOT__/agent-skills/superpowers/writing-skills/SKILL.md</location>
</skill>
</available_skills>
<!-- SKILLPORT_END -->

## Superpowers Workflow
This project adheres to the **Superpowers Workflow** as defined in [`global-rules/AGENTS.global.md`](global-rules/AGENTS.global.md). All Skill Integration rules, mandatory MCP tool usage, and workflow principles defined in the global reference apply here to balance rigor and efficiency based on task complexity.

### Project Application Level
As the central authority for AI agent configurations, **Level 1 (High Intensity)** is the default for most tasks.
- **Level 2 (Medium Intensity)** may be applied for refactoring, improvements, or moderate logic changes.
- **Level 3 (Low Intensity)** is reserved for minor documentation edits or trivial configuration changes to ensure a rapid response without sacrificing essential validation.
- **Level 0 (Zero Intensity)** is for greetings, chitchat, or direct inquiries. Skip all formal skills (including `load_skill`) and proceed directly to response.

## 単体使用時の注意点

公式にはサポートされていませんが、自己責任での単体使用は可能であり、使用する場合は symbolic links と ARCHITECTURE.md に従い、共通ライブラリ（dotfiles-core）を上書きしないことを前提としてください.
