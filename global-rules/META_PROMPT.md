# Progressive Reference Map

This file is a map of available references, not a requirement to preload every
file before every task. Identify the references relevant to the current task
and read only those files.

## Skills

Task-specific skills are stored as `SKILL.md` files under `../agent-skills/`.
Search for the relevant skill, load it before acting, and follow its workflow.

## Global Rule Files

- `AGENTS.global.md` - universal scope, priorities, and safety boundaries.
- `MARKDOWN.md` - Markdown conventions and linting expectations.
- `SHELL.md` - POSIX and Bash scripting conventions.
- `DOCS_STYLE.md` - human-facing documentation structure and language policy.
- `GIT_STANDARDS.md` - commit and pull request conventions.
- `STACKED_PR_WORKFLOW.md` - stacked PR workflow; read only when the task
  explicitly uses stacked PRs. This file never authorizes a merge.
