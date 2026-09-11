# Markdown Guidelines

## Linting Standard: `markdownlint-cli2`

All Markdown files must comply with `markdownlint-cli2` standards.

- **Authority**: If `.markdownlint-cli2.yaml` or `.markdownlint.yaml` exists,
  it is the single source of truth. Otherwise, use the tool defaults and the
  rules in this file.
- **Action**: Before committing changes to any `.md` file, run
  `markdownlint-cli2` on the file if available, or strictly adhere to the
  standard rules.

## Common Rules to Remember
1. **Headers**: Increment headers by one level only (e.g., do not jump from H2 to H4).
2. **Lists**: Use consistent indentation (2 spaces) and markers.
3. **Code Blocks**: Always specify the language for syntax highlighting (e.g., \`\`\`bash).
4. **Spacing**: No trailing spaces; ensure a single newline at the end of the file.
5. **Line Length**: Soft wrap is preferred; do not hard wrap lines unless necessary for tables.

## Project Specifics

- **Language**: Rule files are written in English. Other documentation follows
  the repository's canonical language. For `yohi/*` repositories, English is
  canonical and Japanese translations use the `.ja.md` suffix when useful.
- **Links**: Use relative paths for internal links and verify their targets.
