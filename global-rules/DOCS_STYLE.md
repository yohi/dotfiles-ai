# Documentation Style Guidelines

## Scope

Use this file for human-facing documentation. `AGENTS.global.md` remains the
canonical source for agent behavior and safety boundaries.

## Language

- Use the repository's canonical documentation language.
- For `yohi/*` repositories, English is canonical. Add `.ja.md` translations
  only for useful human-facing documents; do not create Japanese duplicates of
  `AGENTS.md`, `SPEC.md`, schemas, skills, prompts, or machine-consumed files.
- Keep agent-facing rule files in English.

## Structure

- Keep `README.md` focused on discovery, onboarding, quick start, and routing.
- Put detailed architecture, configuration, deployment, operations, and
  migration guidance in `docs/` or another clearly named reference document.
- Keep one canonical source for each kind of information. Summaries should
  link to the canonical document rather than duplicate it.
- Lead with the document's purpose and conclusion before adding detail.

## Markdown

- Use headings, lists, tables, and code blocks consistently.
- Always specify a language for fenced code blocks.
- Use relative links for repository-internal references and verify their
  targets.
- Keep documents concise, current, and easy to navigate.
