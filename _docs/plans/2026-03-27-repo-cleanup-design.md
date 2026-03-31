# Repository Cleanup Design (2026-03-27)

## Goal
Remove `.cursor`, `.gemini`, and `.opencode` from Git tracking and clean up the filesystem to maintain repository SSOT principles.

## Approach
1.  **Untrack from Git**: These directories are either operational artifacts or legacy configuration.
2.  **Filesystem Cleanup**: Remove physical directories for `.gemini` and `.opencode` as they are invalid/redundant. Keep `.cursor/rules` but untracked, as it is a target for `sync-agents`.
3.  **Prevent Re-entry**: Update `.gitignore` to ensure they are not added back.

## Success Criteria
- `git status` shows no files in these directories are being tracked.
- `.gitignore` contains the necessary exclusion patterns.
- `.gemini/` and `.opencode/` are removed from the filesystem.
