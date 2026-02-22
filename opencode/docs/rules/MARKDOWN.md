# Markdown Guidelines

## Linting Standard: `markdownlint-cli2`
All Markdown files must comply with `markdownlint-cli2` standards.
- **Authority**: The configuration in `.markdownlint-cli2.yaml` (or `.markdownlint.yaml`) is the single source of truth.
- **Action**: Before committing changes to any `.md` file, run `markdownlint-cli2` on the file if available, or strictly adhere to the standard rules.

## Common Rules to Remember
1. **Headers**: Increment headers by one level only (e.g., do not jump from H2 to H4).
2. **Lists**: Use consistent indentation (2 spaces) and markers.
3. **Code Blocks**: Always specify the language for syntax highlighting (e.g., \`\`\`bash).
4. **Spacing**: No trailing spaces; ensure a single newline at the end of the file.
5. **Line Length**: Soft wrap is preferred; do not hard wrap lines unless necessary for tables.

## Project Specifics
- **Language**: Documentation text must be in **Japanese** (except for these rule files).
- **Links**: Use relative paths for internal links.
