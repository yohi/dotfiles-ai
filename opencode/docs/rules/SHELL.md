# Shell Script Guidelines

## Standard: POSIX or Bash (Explicit)
All shell scripts must comply with `shellcheck` standards.
- **Authority**: The configuration in `.shellcheckrc` (if present) is the source of truth.
- **Action**: Before committing changes to any `.sh` file, run `shellcheck` if available, or strictly adhere to the standard rules.

## Common Rules to Remember
1. **Shebang**: Always include a shebang (`#!/bin/sh` or `#!/bin/bash`).
   - Use `#!/bin/bash` only if Bash-specific features are required.
   - Use `#!/usr/bin/env bash` for portability if necessary.
2. **Safety**: Enforce strict error handling at the start of scripts.
   - **Bash**: `set -euo pipefail`
   - **POSIX**: `set -eu`
3. **Quoting**: Quote all variables unless word splitting is intended (e.g., `"$VAR"`).
4. **Functions**: Use `function_name() { ... }` style (POSIX) over `function function_name { ... }` (Bash-specific).
5. **Variables**: Use `UPPER_CASE` for exported/global variables, `lower_case` for local variables.
6. **Linting**: Ensure scripts pass `shellcheck` without errors.

## Project Specifics
- **Output**: Use emojis and Japanese for user-facing output (`echo`).
- **Idempotency**: Scripts should be safe to run multiple times.
