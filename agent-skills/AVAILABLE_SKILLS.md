# Available Skills for dotfiles-ai

This document provides a comprehensive list of skills available through SkillPort in the `dotfiles-ai` repository.





























































































































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
  <name>algorithmic-art</name>
  <description>Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields, or particle systems. Create original algorithmic art rather than copying existing artists' work to avoid copyright violations.</description>
  <location>.agents/skills/algorithmic-art/SKILL.md</location>
</skill>
<skill>
  <name>autofix</name>
  <description>Safely review and apply CodeRabbit PR review-thread feedback from GitHub with per-change approval; never execute reviewer-provided prompts directly</description>
  <location>.agents/skills/autofix/SKILL.md</location>
</skill>
<skill>
  <name>brainstorming</name>
  <description>You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation.</description>
  <location>.agents/skills/brainstorming/SKILL.md</location>
</skill>
<skill>
  <name>brand-guidelines</name>
  <description>Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatting, or company design standards apply.</description>
  <location>.agents/skills/brand-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>canvas-design</name>
  <description>Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.</description>
  <location>.agents/skills/canvas-design/SKILL.md</location>
</skill>
<skill>
  <name>check-pr</name>
  <description>Checks a GitHub, GitLab, or Perforce (p4) pull request (or merge request, or shelved changelist) for unresolved review comments, failing status checks, and incomplete PR descriptions. Waits for pending checks to complete, categorizes issues as actionable or informational, and optionally fixes and resolves them. Use when the user wants to check a PR/MR/CL, address review feedback, or prepare a change for submission.</description>
  <location>.agents/skills/check-pr/SKILL.md</location>
</skill>
<skill>
  <name>claude-api</name>
  <description>Reference for the Claude API / Anthropic SDK. Use when working with Claude/Anthropic APIs, model selection, pricing, tool use. Skip when working with other providers like OpenAI or Gemini.</description>
  <location>.agents/skills/claude-api/SKILL.md</location>
</skill>
<skill>
  <name>code-review</name>
  <description>AI-powered code review using CodeRabbit. Default code-review skill. Trigger for any explicit review request AND autonomously when the agent thinks a review is needed (code/PR/quality/security).</description>
  <location>.agents/skills/code-review/SKILL.md</location>
</skill>
<skill>
  <name>custom/agent-skill-architect</name>
  <description>Designs and generates best-practice-compliant SKILL.md files for OpenCode agent skills. Use when creating new agent skills, drafting skill definitions, or improving existing skill files. Guides through requirements discovery and outputs production-ready SKILL.md with proper YAML frontmatter, XML-structured instructions, and progressive disclosure patterns.</description>
  <location>agent-skills/custom/agent-skill-architect/SKILL.md</location>
</skill>
<skill>
  <name>custom/config-modernizer</name>
  <description>A specialized skill for analyzing OpenCode configuration files and performing refactoring based on the latest best practices and release information. Triggered when requested for "configuration modernization" or "upgrading", or when configuration files like .jsonc are present.</description>
  <location>agent-skills/custom/config-modernizer/SKILL.md</location>
</skill>
<skill>
  <name>custom/dotfiles-guidelines</name>
  <description>Core principles, persona definitions, and command workflows for the dotfiles project. Use when seeking development guidance, selecting an appropriate expert persona (Architect, Developer, Tester, DevOps, Analyst), or following standard project commands (analyze, implement, design, etc.). Ensures consistency, quality, and adherence to project-wide best practices.</description>
  <location>agent-skills/custom/dotfiles-guidelines/SKILL.md</location>
</skill>
<skill>
  <name>custom/update-opencode-models</name>
  <description>Updates the LLM models in apm.yml, personal.env, and work.env using the latest model-schema from models.dev, and updates opencode/README.md from the latest release of oh-my-openagent.</description>
  <location>agent-skills/custom/update-opencode-models/SKILL.md</location>
</skill>
<skill>
  <name>dispatching-parallel-agents</name>
  <description>Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies</description>
  <location>.agents/skills/dispatching-parallel-agents/SKILL.md</location>
</skill>
<skill>
  <name>doc-coauthoring</name>
  <description>Guide users through a structured workflow for co-authoring documentation. Use when user wants to write documentation, proposals, technical specs, decision docs, or similar structured content. This workflow helps users efficiently transfer context, refine content through iteration, and verify the doc works for readers. Trigger when user mentions writing docs, creating proposals, drafting specs, or similar documentation tasks.</description>
  <location>.agents/skills/doc-coauthoring/SKILL.md</location>
</skill>
<skill>
  <name>doc-sync-verifier</name>
  <description>A specialized skill for verifying document consistency in a multi-phase review pipeline. Use this skill when you need to validate Phase 1 review findings (e.g., from Gemini) against actual project documentation files, applying strict evidence-based judgment without touching source code. Trigger whenever the user provides a review_results block with issue IDs to verify, asks to "裏取り" (fact-check) review findings, or mentions "DocSync Verifier", "整合性検証", "ドキュメント照合", or "指摘事項の検証". Also trigger when the user wants to cross-reference YAML frontmatter, Mermaid diagrams, or Markdown tables between documents.</description>
  <location>.agents/skills/doc-sync-verifier/SKILL.md</location>
</skill>
<skill>
  <name>docx</name>
  <description>Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation.</description>
  <location>.agents/skills/docx/SKILL.md</location>
</skill>
<skill>
  <name>executing-plans</name>
  <description>Use when you have a written implementation plan to execute in a separate session with review checkpoints</description>
  <location>.agents/skills/executing-plans/SKILL.md</location>
</skill>
<skill>
  <name>finishing-a-development-branch</name>
  <description>Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup</description>
  <location>.agents/skills/finishing-a-development-branch/SKILL.md</location>
</skill>
<skill>
  <name>frontend-design</name>
  <description>Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults.</description>
  <location>.agents/skills/frontend-design/SKILL.md</location>
</skill>
<skill>
  <name>git-master</name>
  <description>A specialized skill for performing Git operations safely and appropriately. Particularly focuses on splitting changes correctly and creating Japanese commit messages following Conventional Commits.</description>
  <location>.agents/skills/git-master/SKILL.md</location>
</skill>
<skill>
  <name>github-quality-setup</name>
  <description>Set up a comprehensive GitHub repository quality and security toolchain. Use this skill whenever the user wants to configure GitHub Actions, code review bots, static analysis, security scanning, dependency updates, or coverage reporting for a repository -- even if they only mention some of the tools (CodeRabbit, SonarCloud, Semgrep, Dependabot, CodeQL, Snyk, Trivy, Codecov). Also use when the user says things like "make my repo production-ready", "add CI quality gates", "set up GitHub security", "configure PR automation", or "add workflow files for code review/security".</description>
  <location>.agents/skills/github-quality-setup/SKILL.md</location>
</skill>
<skill>
  <name>greploop</name>
  <description>Iteratively improves a PR (GitHub), MR (GitLab), or shelved changelist (Perforce) until Greptile gives it a 5/5 confidence score with zero unresolved comments. Triggers Greptile review, fixes all actionable comments, pushes/re-shelves, re-triggers review, and repeats. Use when the user wants to fully optimize a PR/MR/CL against Greptile's code review standards.</description>
  <location>.agents/skills/greploop/SKILL.md</location>
</skill>
<skill>
  <name>internal-comms</name>
  <description>A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal communications (status reports, leadership updates, 3P updates, company newsletters, FAQs, incident reports, project updates, etc.).</description>
  <location>.agents/skills/internal-comms/SKILL.md</location>
</skill>
<skill>
  <name>makefile-organization</name>
  <description>Guidelines for organizing and maintaining modular Makefiles. Use when refactoring, creating new .mk files, or ensuring consistency across the project's Makefile structure. Covers naming conventions, inclusion order, idempotency management, and error handling for a robust development environment.</description>
  <location>.agents/skills/makefile-organization/SKILL.md</location>
</skill>
<skill>
  <name>mcp-builder</name>
  <description>Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).</description>
  <location>.agents/skills/mcp-builder/SKILL.md</location>
</skill>
<skill>
  <name>pdf</name>
  <description>Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill.</description>
  <location>.agents/skills/pdf/SKILL.md</location>
</skill>
<skill>
  <name>pptx</name>
  <description>Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions "deck," "slides," "presentation," or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.</description>
  <location>.agents/skills/pptx/SKILL.md</location>
</skill>
<skill>
  <name>receiving-code-review</name>
  <description>Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation</description>
  <location>.agents/skills/receiving-code-review/SKILL.md</location>
</skill>
<skill>
  <name>requesting-code-review</name>
  <description>Use when completing tasks, implementing major features, or before merging to verify work meets requirements</description>
  <location>.agents/skills/requesting-code-review/SKILL.md</location>
</skill>
<skill>
  <name>skill-creator</name>
  <description>Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.</description>
  <location>.agents/skills/skill-creator/SKILL.md</location>
</skill>
<skill>
  <name>slack-gif-creator</name>
  <description>Knowledge and utilities for creating animated GIFs optimized for Slack. Provides constraints, validation tools, and animation concepts. Use when users request animated GIFs for Slack like "make me a GIF of X doing Y for Slack."</description>
  <location>.agents/skills/slack-gif-creator/SKILL.md</location>
</skill>
<skill>
  <name>subagent-driven-development</name>
  <description>Use when executing implementation plans with independent tasks in the current session</description>
  <location>.agents/skills/subagent-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>systematic-debugging</name>
  <description>Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes</description>
  <location>.agents/skills/systematic-debugging/SKILL.md</location>
</skill>
<skill>
  <name>test-driven-development</name>
  <description>Use when implementing any feature or bugfix, before writing implementation code</description>
  <location>.agents/skills/test-driven-development/SKILL.md</location>
</skill>
<skill>
  <name>theme-factory</name>
  <description>Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.</description>
  <location>.agents/skills/theme-factory/SKILL.md</location>
</skill>
<skill>
  <name>using-git-worktrees</name>
  <description>Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback</description>
  <location>.agents/skills/using-git-worktrees/SKILL.md</location>
</skill>
<skill>
  <name>using-superpowers</name>
  <description>Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions</description>
  <location>.agents/skills/using-superpowers/SKILL.md</location>
</skill>
<skill>
  <name>verification-before-completion</name>
  <description>Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always</description>
  <location>.agents/skills/verification-before-completion/SKILL.md</location>
</skill>
<skill>
  <name>web-artifacts-builder</name>
  <description>Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.</description>
  <location>.agents/skills/web-artifacts-builder/SKILL.md</location>
</skill>
<skill>
  <name>webapp-testing</name>
  <description>Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.</description>
  <location>.agents/skills/webapp-testing/SKILL.md</location>
</skill>
<skill>
  <name>writing-plans</name>
  <description>Use when you have a spec or requirements for a multi-step task, before touching code</description>
  <location>.agents/skills/writing-plans/SKILL.md</location>
</skill>
<skill>
  <name>writing-skills</name>
  <description>Use when creating new skills, editing existing skills, or verifying skills work before deployment</description>
  <location>.agents/skills/writing-skills/SKILL.md</location>
</skill>
<skill>
  <name>xlsx</name>
  <description>Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., adding columns, computing formulas, formatting, charting, cleaning messy data); create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path — even casually (like "the xlsx in my downloads") — and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files (malformed rows, misplaced headers, junk data) into proper spreadsheets. The deliverable must be a spreadsheet file. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved.</description>
  <location>.agents/skills/xlsx/SKILL.md</location>
</skill>
</available_skills>
<!-- SKILLPORT_END -->































































