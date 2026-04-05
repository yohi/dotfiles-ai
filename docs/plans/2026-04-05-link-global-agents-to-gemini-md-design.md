# Design: Link global-rules/AGENTS.global.md to ~/.gemini/GEMINI.md

## Goal
Manage the global context of Gemini CLI (`~/.gemini/GEMINI.md`) using a symbolic link to the version-controlled `global-rules/AGENTS.global.md` in the dotfiles repository.

## Background
- `~/.gemini/GEMINI.md` provides global instructions to Gemini CLI.
- `global-rules/AGENTS.global.md` in the repository contains the same structure but with more advanced and up-to-date instructions (especially regarding the Superpowers workflow).
- Centralizing this configuration allows for easier updates and consistency across environments.

## Proposed Changes
1.  **Backup**: Rename the existing `~/.gemini/GEMINI.md` to `~/.gemini/GEMINI.md.bak`.
2.  **Symbolic Link**: Create a symbolic link from `~/.gemini/GEMINI.md` pointing to the absolute path of `global-rules/AGENTS.global.md`.

## Detailed Approach
- Use `realpath` to get the absolute path of the target file to ensure the link remains valid regardless of the current working directory.
- Use `ln -s` to create the symbolic link.

## Verification Plan
1.  **Link Verification**: Run `ls -l ~/.gemini/GEMINI.md` to confirm it points to the correct location.
2.  **Read Verification**: Run `cat ~/.gemini/GEMINI.md` to ensure the content is readable and matches the source.
