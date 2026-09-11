# Git Standards

## Commit Messages

- Use [Conventional Commits](https://www.conventionalcommits.org/ja/v1.0.0/).
- Write the commit subject and body in Japanese; keep the Conventional Commit
  type in English.
- Use the format `type(scope): subject` when a scope improves clarity.
- Keep each commit atomic and limited to its intended files.

## Before Committing

- Inspect `git status`, the complete diff, and recent history before staging.
- Stage files by explicit path. Never use broad staging such as `git add .`.
- Run the relevant deterministic verification commands and report their
  results.
- Never commit secrets, credentials, `.env` files, or machine-specific paths.

## Pull Requests

This file does not authorize pull request merges. The explicit authorization,
scope, and confirmation requirements in `AGENTS.global.md` are authoritative.
