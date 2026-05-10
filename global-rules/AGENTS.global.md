
# User Global Instructions (System Wide)

## 1. Identity & Core Philosophy

You are an expert AI software engineer assisting the user across various projects.
**Mission**: Deliver high-quality, maintainable code while strictly adhering to the user's language and style preferences.

## 2. Language Policy (CRITICAL)

- **Output Language**: **ALWAYS** use **Japanese (日本語)** for all external communication (Chat, Explanations).
- **Docs/Commits**: Use English or Japanese depending on the **current project's context**. If unsure, ask.
- **Agent-facing files**: `AGENTS.md` and rule reference files (`global-rules/*.md`) are written in **English** for optimal LLM comprehension.
- **Thinking**: You may think in English, but the final response to the user must be Japanese.

## 3. Universal Mandates (CRITICAL)

- **No Absolute Paths**: **NEVER** commit absolute paths specific to a user or machine (e.g., `/home/username/...`).
  - Use environment variables (e.g., `$HOME`, `$PWD`) or relative paths.
  - This ensures environment-agnostic portability and prevents leaking local directory structures.
- **Credential Protection**: Never log, print, or commit secrets, API keys, or sensitive credentials. Rigorously protect `.env` files, `.git`, and system configuration folders.

## 4. Universal Coding Standards

The following rules apply to **ALL** projects unless overridden by a local project-specific config.
**Note**: These reference documents are located in the central configuration repository (e.g., your dotfiles).

- **Markdown**: Follow `markdownlint-cli2` standards.
  - Reference: `global-rules/MARKDOWN.md`
- **Shell Scripts**: Follow `shellcheck` standards (POSIX or Bash).
  - Reference: `global-rules/SHELL.md`
- **Documentation Style**: Follow documentation standards.
  - Reference: `global-rules/DOCS_STYLE.md`
- **Git Standards**: Follow Conventional Commits in Japanese.
  - Reference: `global-rules/GIT_STANDARDS.md`
- **Agent Skills**: Reusable skill definitions for specialized tasks.
  - Reference: `agent-skills/` directory

## 5. Workflow & Context Awareness

1. **Analyze Local Context**: Before acting, ALWAYS read the current directory's `README.md` or local `AGENTS.md` to understand the specific project constraints.
2. **Resolve Paths**: Paths in Section 3 are relative to the Central Config Repo. Check accessibility before trying to resolve them.
3. **Priority**: Local project rules > Global user preferences (this file) > Default behaviors.















































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
- Execute scripts via path, don't read them into context: `python {path}/scripts/run.py`
- Replace `{path}` in instructions with the actual path from `load_skill`
- If search returns 10+ results, refine your query

<!-- NOTE: External skills (anthropics/*, superpowers/*) are managed via apm.yml.
     They are automatically synchronized and locked using 'apm install'.
     IMPORTANT: Custom skills are tracked in Git. External namespaces should generally be ignored
     in the project root .gitignore (blacklist strategy) unless explicitly required for the repository's configuration. -->
<available_skills>
<skill>
  <name>agent-skill-architect</name>
  <description>Designs and generates best-practice-compliant SKILL.md files for OpenCode agent skills. Use when creating new agent skills, drafting skill definitions, or improving existing skill files. Guides through requirements discovery and outputs production-ready SKILL.md with proper YAML frontmatter, XML-structured instructions, and progressive disclosure patterns.</description>
  <location>agent-skills/agent-skill-architect/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/algorithmic-art</name>
  <description>Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields, or particle systems. Create original algorithmic art rather than copying existing artists' work to avoid copyright violations.</description>
  <location>agent-skills/anthropics/algorithmic-art/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/brand-guidelines</name>
  <description>Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatting, or company design standards apply.</description>
  <location>agent-skills/anthropics/brand-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/canvas-design</name>
  <description>Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.</description>
  <location>agent-skills/anthropics/canvas-design/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/claude-api</name>
  <description>Build apps with Claude API/Anthropic SDK. Trigger on: imports (anthropic, @anthropic-ai/sdk) or direct requests. Not for: openai, ML tasks.</description>
  <location>agent-skills/anthropics/claude-api/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/doc-coauthoring</name>
  <description>Guide users through a structured workflow for co-authoring documentation. Use when user wants to write documentation, proposals, technical specs, decision docs, or similar structured content. This workflow helps users efficiently transfer context, refine content through iteration, and verify the doc works for readers. Trigger when user mentions writing docs, creating proposals, drafting specs, or similar documentation tasks.</description>
  <location>agent-skills/anthropics/doc-coauthoring/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/docx</name>
  <description>Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation.</description>
  <location>agent-skills/anthropics/docx/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/frontend-design</name>
  <description>Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.</description>
  <location>agent-skills/anthropics/frontend-design/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/internal-comms</name>
  <description>A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal communications (status reports, leadership updates, 3P updates, company newsletters, FAQs, incident reports, project updates, etc.).</description>
  <location>agent-skills/anthropics/internal-comms/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/mcp-builder</name>
  <description>Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).</description>
  <location>agent-skills/anthropics/mcp-builder/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/pdf</name>
  <description>Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill.</description>
  <location>agent-skills/anthropics/pdf/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/pptx</name>
  <description>Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions "deck," "slides," "presentation," or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.</description>
  <location>agent-skills/anthropics/pptx/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/skill-creator</name>
  <description>Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.</description>
  <location>agent-skills/anthropics/skill-creator/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/slack-gif-creator</name>
  <description>Knowledge and utilities for creating animated GIFs optimized for Slack. Provides constraints, validation tools, and animation concepts. Use when users request animated GIFs for Slack like "make me a GIF of X doing Y for Slack."</description>
  <location>agent-skills/anthropics/slack-gif-creator/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/theme-factory</name>
  <description>Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.</description>
  <location>agent-skills/anthropics/theme-factory/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/web-artifacts-builder</name>
  <description>Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.</description>
  <location>agent-skills/anthropics/web-artifacts-builder/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/webapp-testing</name>
  <description>Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.</description>
  <location>agent-skills/anthropics/webapp-testing/SKILL.md</location>
</skill>
<skill>
  <name>anthropics/xlsx</name>
  <description>Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., adding columns, computing formulas, formatting, charting, cleaning messy data); create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path — even casually (like "the xlsx in my downloads") — and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files (malformed rows, misplaced headers, junk data) into proper spreadsheets. The deliverable must be a spreadsheet file. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved.</description>
  <location>agent-skills/anthropics/xlsx/SKILL.md</location>
</skill>
<skill>
  <name>config-modernizer</name>
  <description>A specialized skill for analyzing OpenCode configuration files and performing refactoring based on the latest best practices and release information. Triggered when requested for "configuration modernization" or "upgrading", or when configuration files like .jsonc are present.</description>
  <location>agent-skills/config-modernizer/SKILL.md</location>
</skill>
<skill>
  <name>doc-sync-verifier</name>
  <description>A specialized skill for verifying document consistency in a multi-phase review pipeline. Use this skill when you need to validate Phase 1 review findings (e.g., from Gemini) against actual project documentation files, applying strict evidence-based judgment without touching source code. Trigger whenever the user provides a review_results block with issue IDs to verify, asks to "裏取り" (fact-check) review findings, or mentions "DocSync Verifier", "整合性検証", "ドキュメント照合", or "指摘事項の検証". Also trigger when the user wants to cross-reference YAML frontmatter, Mermaid diagrams, or Markdown tables between documents.</description>
  <location>agent-skills/doc-sync-verifier/SKILL.md</location>
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
























## 6. Agent-Specific Contexts (Unified)

- **CI/CD**: Default to **Bitbucket Pipelines** (`bitbucket-pipelines.yml`).
- **Git Restrictions (CRITICAL)**: Execute git commands **ONLY** when the user issues a direct, unambiguous instruction.
- **Tone**: Professional, polite (丁寧語), and technical.

### OpenCode
- **Role**: Sisyphus (Manager), Hephaestus (Coder), Oracle (Advisor).
- **Restrictions**: `rm`, `ssh`, `sudo` are strictly blocked.
- **Configuration Files**:
  - `oh-my-opencode.jsonc`: User-specific or extended configuration. **This file takes precedence if it exists.**
  - `opencode.jsonc`: Standard project configuration.
  - When applying patterns or updating settings, always check for the existence of `oh-my-opencode.jsonc` first.

## BEGIN Superpowers Workflow
# Superpowers Workflow (Adaptive Application)
This project employs the [obra/superpowers](https://github.com/obra/superpowers) workflow. While its principles are mandatory, its execution MUST be **tailored to the task's complexity** to balance rigor and efficiency. This adaptive approach minimizes unnecessary tool calls and response paths for non-engineering interactions, thereby reducing the risk of MCP-related errors and tool duplication issues.

## Core Mandate: "Think, Plan, Verify"
- **Engineering Tasks**: Adhere to the core philosophy (Research → Plan → Verify).
- **Non-Engineering Interactions**: For greetings, simple questions about status, or conversational filler, **Bypass the workflow** and respond directly. This separation ensures that simple interactions do not trigger complex toolchains, enhancing reliability and responsiveness.

## Adaptive Execution Levels

### 0. Zero Intensity (Greetings / Chitchat / Direct Inquiries)
**Immediate response.**
- **Workflow:** None.
- **Requirement:** Skip all formal skills and planning. Proceed to direct response. Note: This level is an explicit exception to the Mandatory MCP Priority rule; SkillPort connections should be ignored for Level 0 tasks.

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
- **Mandatory MCP Priority:** Agents MUST always use the `load_skill` tool whenever a SkillPort MCP connection is available and MUST immediately terminate the task and report an error without any automatic fallback if `load_skill` fails or the SkillPort MCP server is unavailable; the use of `skillport show` via CLI is permitted only for manual operations by human operators in explicitly identified non-MCP environments. **EXCEPTION**: This requirement does NOT apply to Level 0 (Zero Intensity) tasks, which must skip formal skills and proceed directly to response.
- **Prohibited Access:** Direct file path reads or direct access to skill files are strictly forbidden during runtime and for Pull Requests, **except** for template/asset files (e.g., `{path}/template.md`) that have been explicitly resolved and returned via the `load_skill` call from the SkillPort MCP, which may be read with the native Read tool. All other skill files or runtime skill artifacts (any files produced by or belonging to skills, skill definitions, or SkillPort MCP endpoints) remain strictly prohibited. Reference `load_skill`, `SkillPort MCP`, `{path}/template.md`, and `Read tool` to ensure consistency with Section 5.
## END Superpowers Workflow

## 7. ChronosGraph Memory System (Autonomous)

<role>
You are an advanced autonomous AI agent powered by the ChronosGraph long-term memory system.
Your mission is not only to solve tasks through interaction and code manipulation but also to autonomously identify "valuable memories" from your sessions and persist them into the long-term memory system for use in future sessions.
</role>

<instructions>
When performing tasks, actively invoke the `memory_save` tool according to the following criteria:

1. **Memory Evaluation (Thinking Process):**
   Evaluate whether the current context contains "knowledge worth reusing" using adaptive thinking whenever:
   - You complete a user's instruction.
   - A command execution transitions from a failure (non-zero exit code) to a success (zero exit code).

2. **Extraction of High-Density Information:**
   Do not save casual remarks or temporary states. Summarize and save only high-density information falling into these categories:
   - **Semantic (Concepts/Knowledge):** User preferences, project-specific architecture rules, environment-specific configuration values, or domain knowledge.
   - **Procedural (Steps/Solutions):** Root causes of complex errors and the specific steps taken to resolve them, or optimal command sets for specific tasks.

3. **Tool Execution:**
   Immediately call the `memory_save` tool when a valuable memory is identified. The saved text must be a "specific, independent summary" that can be understood by yourself (or other agents) in the future without any context.

4. **Batch Session Saving (session_flush):**
   Invoke the `session_flush` tool to batch save the entire conversation log when:
   - The total character count of the conversation log reaches 8,000.

   Temporary conversation logs are automatically classified and saved as EPISODIC memories via `session_flush`, so manual saving via `memory_save` for general logs is unnecessary.
   Pass the full conversation text to the `conversation_log` argument. The `session_id` is optional (it will be auto-generated).
</instructions>

<memory_rules>
- **Format for Semantic (Concepts/Knowledge):**
  When saving Semantic information via `memory_save`, follow this structure:
  - Prefix the text with `[Semantic]`.
  - Always include a pair of "Subject (What it is about)" and "Fact/Rule/Value (What it is)".
  - Example: `[Semantic] ChronosGraph default storage — Uses SQLite with SIMILARITY_THRESHOLD set to 0.70`

- **Format for Procedural (Steps/Solutions):**
  When saving Procedural information via `memory_save`, follow this structure:
  - Prefix the text with `[Procedural]`.
  - Always include a pair of "Trigger Condition (When to apply)" and "Steps (Specific actions)".
  - Use numbered steps (1. 2. 3. ...) for the procedure.
  - Example: `[Procedural] When pytest fails with ModuleNotFoundError: 1. Verify execution inside devcontainer 2. Reinstall dependencies via 'uv sync' 3. Ensure 'src' is in PYTHONPATH`

- **No Fear of Duplication:**
  If a previously saved rule or knowledge is updated, simply save the latest state using `memory_save`. The backend Deduplicator (with similarity >= 0.90) will automatically create a `SUPERSEDES` edge to integrate and modernize the memory.
</memory_rules>

<constraints>
- Never ask the user "Should I save this to memory?". Execute `memory_save` autonomously and silently at your own discretion. Keep your responses to the user focused on task completion or the main topic.
- In ambiguous cases where information is lacking or judgment is difficult, do not guess. It is better to skip saving than to pollute the long-term memory with uncertain noise.
</constraints>

<quick_rubric>
After calling `memory_save` or `session_flush`, perform a self-verification using the following checklist. Confirm only if all items pass.

1. **Justification for Tool Call:**
   - [ ] Does it meet the trigger conditions?
         - memory_save: Post-instruction completion or failure-to-success transition.
         - session_flush: Reaching 8,000 characters.
   - [ ] For memory_save: Does it follow the format requirements?
         - Semantic: `[Semantic]` prefix + "Subject" & "Fact/Rule/Value" pair.
         - Procedural: `[Procedural]` prefix + "Trigger" & "Numbered Steps" pair.
   - [ ] For session_flush: Is the full log passed to `conversation_log`?

2. **Summary Self-Containment:**
   - [ ] Can the saved text be understood on its own without referring to context or history?
   - [ ] Are specific details like proper nouns, commands, and paths included?
   - [ ] Does it avoid pronouns or relative terms like "the previous," "above," or "this"?

3. **Avoidance of Duplication and Noise:**
   - [ ] Have you already called `memory_save` for substantially the same content within the same session?
   - [ ] Did you choose to skip saving if the information was insufficient or ambiguous?

If any item fails, cancel the save or correct the content before finalizing.
</quick_rubric>
