# Tool configuration templates

Copy and adapt these templates when generating repository setup files.

## Table of contents

1. [`.coderabbit.yaml`](#coderrabbityaml)
2. [`.github/dependabot.yml`](#githubdependabotyml)
3. [`.github/workflows/codeql.yml`](#githubworkflowscodeqlyml)
4. [`.github/workflows/semgrep.yml`](#githubworkflowssemgremlyml)
5. [`.github/workflows/sonarcloud.yml`](#githubworkflowssonarcloudyml)
6. [`sonar-project.properties`](#sonar-projectproperties)
7. [`.github/workflows/codecov.yml`](#githubworkflowscodecovyml)
8. [`codecov.yml`](#codecovyml)
9. [`.github/workflows/trivy.yml`](#githubworkflowstrivyyml)
10. [`.github/workflows/snyk.yml`](#githubworkflowssnykyml)

---

## `.coderabbit.yaml`

```yaml
# yaml-language-server: $schema=https://coderabbit.ai/integrations/schema.v2.json
language: "en"
early_access: false
tone_instructions: "Be concise and actionable. Prioritize security, correctness, and maintainability."
reviews:
  profile: "chill"
  request_changes_workflow: false
  high_level_summary: true
  poem: false
  review_status: true
  collapse_walkthrough: false
  path_filters:
    - "!**/.github/workflows/**"
  path_instructions:
    - path: "src/**"
      instructions: "Review for type safety, error handling, and test coverage."
    - path: "tests/**"
      instructions: "Check that tests are independent and assert meaningful behavior."
  auto_review:
    enabled: true
    drafts: false
    base_branches:
      - "main"
  tools:
    shellcheck:
      enabled: true
    markdownlint:
      enabled: true
chat:
  auto_reply: true
```

## `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    reviewers:
      - "<GITHUB_USERNAME_OR_TEAM>"

  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
```

## `.github/workflows/codeql.yml`

```yaml
name: "CodeQL"

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
  schedule:
    - cron: "0 9 * * 1"

jobs:
  analyze:
    name: Analyze
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      security-events: write

    strategy:
      fail-fast: false
      matrix:
        language: ["python", "javascript"]

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{matrix.language}}"
```

## `.github/workflows/semgrep.yml`

```yaml
name: Semgrep

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  semgrep:
    name: semgrep/ci
    runs-on: ubuntu-latest
    container:
      image: semgrep/semgrep
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - run: semgrep ci --config=auto
```

## `.github/workflows/sonarcloud.yml`

```yaml
name: SonarCloud

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  sonarcloud:
    name: SonarCloud Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies and run tests with coverage
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
          pytest --cov=src --cov-report=xml

      - name: SonarCloud Scan
        uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

## `sonar-project.properties`

```properties
sonar.projectKey=<SONAR_PROJECT_KEY>
sonar.organization=<SONAR_ORG>
sonar.host.url=https://sonarcloud.io
sonar.sources=src
sonar.tests=tests
sonar.python.coverage.reportPaths=coverage.xml
sonar.python.version=3.11
sonar.exclusions=**/tests/**, **/migrations/**, **/node_modules/**
```

## `.github/workflows/codecov.yml`

```yaml
name: Coverage

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  coverage:
    name: Upload coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run tests with coverage
        run: pytest --cov=src --cov-report=xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: ./coverage.xml
          fail_ci_if_error: true
```

## `codecov.yml`

```yaml
coverage:
  status:
    project:
      default:
        target: 80%
        threshold: 2%
    patch:
      default:
        target: 80%

comment:
  layout: "diff, flags, files"
  behavior: default
  require_changes: true
```

## `.github/workflows/trivy.yml`

```yaml
name: Trivy container scan

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
  schedule:
    - cron: "0 10 * * 1"

jobs:
  trivy:
    name: Scan container image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "<DOCKER_IMAGE>"
          format: "sarif"
          output: "trivy-results.sarif"

      - name: Upload Trivy scan results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: "trivy-results.sarif"
```

## `.github/workflows/snyk.yml`

```yaml
name: Snyk Security

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Snyk to check for vulnerabilities
        uses: snyk/actions/python@master
        continue-on-error: true
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --sarif-file-output=snyk.sarif

      - name: Upload result to GitHub Code Scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: snyk.sarif
```
