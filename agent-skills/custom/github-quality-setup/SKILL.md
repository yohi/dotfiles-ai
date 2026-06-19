---
name: github-quality-setup
description: >
  Set up a comprehensive GitHub repository quality and security toolchain.
  Use this skill whenever the user wants to configure GitHub Actions, code review bots,
  static analysis, security scanning, dependency updates, or coverage reporting for a
  repository -- even if they only mention some of the tools (CodeRabbit, SonarCloud,
  Semgrep, Dependabot, CodeQL, Snyk, Trivy, Codecov). Also use when the user says things
  like "make my repo production-ready", "add CI quality gates", "set up GitHub security",
  "configure PR automation", or "add workflow files for code review/security".
  Works for any language; Python and TypeScript examples are provided in the bundled reference.
---

# GitHub Repository Quality & Security Setup

Configure a GitHub repository with a curated, production-ready toolchain for AI code
review, static analysis, security scanning, dependency management, and test coverage.

## What this skill produces

- Ready-to-commit workflow files under `.github/workflows/`
- A `.github/dependabot.yml` for automated dependency updates
- A `.coderabbit.yaml` for CodeRabbit AI review configuration
- A `sonar-project.properties` for SonarCloud scan settings
- A `codecov.yml` for Codecov upload behavior and thresholds
- A concise setup checklist (GitHub settings, required secrets, third-party sign-ups)

## When to use this skill

Use this skill when the user asks to set up, configure, add, or improve any of the
following for a GitHub repository:

- AI code review (CodeRabbit)
- Static analysis / linting / code quality (SonarCloud, Semgrep)
- Security scanning (CodeQL, Snyk, Trivy)
- Dependency updates (Dependabot)
- Test coverage reporting (Codecov)
- General "production-ready" or "quality gate" CI setup

The user does not need to ask for "all" tools. If they mention only some of them, or use
phrases like "workflow files", "GitHub Actions", "PR automation", or "security scanning",
still generate the full requested subset using this skill.

## Before you start

Ask the user (or infer from the repository) for the minimum required context:

1. **Primary language / stack** (e.g., Python, TypeScript/Node.js, Go, Java, Ruby). If
   unknown, default to Python examples in workflow comments.
2. **Tools to include** (default: all eight below). Respect exclusions if the user
   explicitly opts out of a tool.
3. **Default branch name** (default: `main`).
4. **Container image** (only if Trivy is selected and the repo builds a Docker image).
5. **Package ecosystem(s)** for Dependabot (default: pip + github-actions for Python;
   npm + github-actions for Node.js).
6. **Workflow triggers** (default: `push` to default branch and `pull_request`).
7. **Repository access level** (public or private; important for configuring tools like SonarCloud and Trivy).


## Output layout

Create files in this structure when all tools are selected:

```text
.github/
  dependabot.yml
  workflows/
    codeql.yml
    semgrep.yml
    sonarcloud.yml
    codecov.yml
    trivy.yml          # only if Trivy selected
    # snyk.yml         # only if Snyk selected (user must provide SNYK_TOKEN)
.coderabbit.yaml
sonar-project.properties
codecov.yml
```

When the user requests a subset, generate only the files for that subset. For example,
if the user asks for CodeRabbit, Semgrep, and Dependabot only, the output should be:

```text
.coderabbit.yaml
.github/dependabot.yml
.github/workflows/semgrep.yml
```

IMPORTANT: If the user says "workflow files", "GitHub Actions", or similar, do NOT limit
output to `.github/workflows/*.yml` only. The selected tools require supporting config files
(`.coderabbit.yaml`, `.github/dependabot.yml`, `sonar-project.properties`, `codecov.yml`) as well.
Always generate the complete file set for every selected tool unless the user explicitly
opts out of a specific file.

## Step-by-step instructions

### 1. Read the bundled reference

Load `references/tool-configs.md` for copy-paste-ready workflow and config templates.
These templates include the latest stable GitHub Actions versions as of the skill's
release. Prefer them over writing workflows from scratch so the output stays consistent
and up to date.

### 2. Inspect the target repository (when available)

If the user points to a local checkout:

- Read `README.md` to confirm the language and framework.
- Look at existing `.github/workflows/` to avoid overwriting files.
- Check `pyproject.toml`, `setup.py`, `package.json`, or equivalent to determine package
  manager and test command.
- Note any existing `.coderabbit.yaml`, `sonar-project.properties`, or `codecov.yml`.

If conflicting files already exist, warn the user and propose a merge instead of silently
replacing them.

### 3. Generate the config files

For each selected tool, render the corresponding file from the reference with these
substitutions:

- `<DEFAULT_BRANCH>` -> the default branch name.
- `<PRIMARY_LANGUAGE>` -> the dominant language (e.g., `python`, `javascript`).
- `<SONAR_PROJECT_KEY>` -> `<github_org>_<repo_name>` or ask the user.
- `<SONAR_ORG>` -> GitHub organization name or ask the user.
- `<DOCKER_IMAGE>` -> image reference for Trivy (e.g., `ghcr.io/org/repo:latest`).
- `<ECOSYSTEMS>` -> Dependabot ecosystems appropriate for the stack.

Use the file names and directory layout defined above. Do not invent extra tools or
options beyond the eight listed below unless the user asks.

### 4. Provide the setup checklist

After writing files, output a concise checklist in this exact format:

```markdown
## Setup checklist

- [ ] Sign up / log in to CodeRabbit (https://coderabbit.ai) and grant repo access.
- [ ] Sign up to SonarCloud (https://sonarcloud.io), import the repository, and add
      `SONAR_TOKEN` plus `SONAR_HOST_URL` (optional) as GitHub repository secrets.
- [ ] Add `CODECOV_TOKEN` as a GitHub repository secret (get it from https://codecov.io).
- [ ] If using Snyk, add `SNYK_TOKEN` as a GitHub repository secret.
- [ ] If using Trivy for a container image, ensure the image is published to a registry
      accessible from GitHub Actions.
- [ ] Enable GitHub Advanced Security:
      Settings -> Code security and analysis -> Enable "Dependency graph",
      "Dependabot alerts", "Dependabot security updates", and "Code scanning".
- [ ] Commit the generated files and open a pull request.
```

Tailor the checklist to the selected tools only. Remove items for tools the user skipped.

### 5. Final response format

Summarize what was generated, why each tool is included, and the next steps. Keep the
response practical and concise.

Example structure:

```markdown
# GitHub quality & security setup for <repo>

Generated configuration for: CodeRabbit, SonarCloud, Semgrep, Dependabot, CodeQL,
Snyk, Trivy, Codecov.

## Files created

- `.github/workflows/codeql.yml`
- ...

## Tool rationale

- **CodeRabbit**: AI-driven PR review ...
- ...

## Setup checklist

- [ ] ...
```

## Important constraints

- Do not commit or push files. The user must review and commit themselves.
- Never include real tokens, passwords, or API keys in generated files.
- Keep workflow YAML valid and avoid non-ASCII characters (stick to printable ASCII).
- Use the bundled reference templates; do not fabricate action versions.
