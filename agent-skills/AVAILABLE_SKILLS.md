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
  <name>custom/update-opencode-models</name>
  <description>Updates the LLM models in apm.yml, personal.env, and work.env using the latest model-schema from models.dev, and updates opencode/README.md from the latest release of oh-my-openagent.</description>
  <location>agent-skills/custom/update-opencode-models/SKILL.md</location>
</skill>
<skill>
  <name>local/dotfiles-guidelines</name>
  <description>Core principles, persona definitions, and command workflows for the dotfiles project. Use when seeking development guidance, selecting an appropriate expert persona (Architect, Developer, Tester, DevOps, Analyst), or following standard project commands (analyze, implement, design, etc.). Ensures consistency, quality, and adherence to project-wide best practices.</description>
  <location>.claude/skills/dotfiles-guidelines/SKILL.md</location>
</skill>
</available_skills>
<!-- SKILLPORT_END -->














































































