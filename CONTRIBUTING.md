# Contributing

## Documentation and Rules (SSOT Pattern)

To avoid maintenance drift across multiple components, we use the **Single Source of Truth (SSOT)** pattern for documentation and global rules.

- **Canonical Source**: All global documentation (`GIT_STANDARDS.md`, `DOCS_STYLE.md`, `MARKDOWN.md`, etc.) must be edited in the **`global-rules/`** directory.
- **Reference Pattern**: In other directories like `opencode/docs/global`, these files are referenced via symlinks to `../../global-rules`.
- **Modifications**: Do not duplicate these files. If you need to update a rule, apply the change directly to the file within the `global-rules/` directory.
