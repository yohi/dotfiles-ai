# Guarded Stacked PR Workflow

## Scope and Priority

This workflow is opt-in. Apply it only when the task explicitly uses stacked
PRs, phase/base/task branches, or this document by name. Ordinary branch and PR
work is governed by the repository instructions and does not inherit these
constraints.

`AGENTS.global.md` remains authoritative for universal safety rules and
priority. This document adds workflow-specific constraints; it never
authorizes a pull request merge.

## Metadata

```yaml
workflow_metadata:
  name: Guarded Stacked PR Workflow
  version: 1.4.2
  policy:
    human_in_the_loop: true
    naming_enforcement: strict
    sync_method: rebase
  naming_convention:
    base: feature/phase[N]-[feature]__base
    task: feature/phase[N]-task[M]-[subfeature]
```

## 1. Branch Naming

Use the following patterns when this workflow is active. Do not use generic
prefixes such as `feat/` or `fix/` for these branches.

- **Base branch**: `feature/phase1-redis-monitor__base`
- **Task branch**: `feature/phase1-task1-interface-def`

## 2. Workflow

### Step 1: Set Up Branches

1. Create the base branch from `master` and end its name with `__base`.
2. Create the first task branch from the base branch.

```bash
git checkout -b feature/phase1-redis-monitor__base
git checkout -b feature/phase1-task1-interface-def
```

### Step 2: Implement and Stack

1. Keep each task at or below 200 LOC and require unit tests to pass fully.
2. Create a draft PR whose base is the workflow base branch.
3. Create each subsequent task branch from the preceding task branch.

### Step 3: Propagate Changes

1. When a preceding task has been merged into `__base` through an explicitly
   authorized operation, rebase all later task branches onto the updated base.
2. If a rebase conflict occurs, do not resolve it automatically. Run
   `git rebase --abort`, report the conflict, and ask a human to decide.
3. Stop even when a conflict appears small if its history is difficult to
   interpret.

## 3. Forbidden Actions

When this workflow is active, do not:

1. Use branch prefixes outside the naming patterns above.
2. Push directly to the `__base` branch; use a PR instead.
3. Auto-merge into `master`. This workflow does not grant merge permission;
   all merges remain subject to `AGENTS.global.md`.
4. Start the next task without rebasing the preceding task's changes.

## 4. PR Checklist

Before creating a PR, verify:

- [ ] The branch name matches `feature/phase[N]-task[M]-...`.
- [ ] The PR targets the workflow `__base` branch, not `master`.
- [ ] The diff is 200 LOC or smaller.
- [ ] The change has one purpose and does not include unrelated work.

## 5. Progress Report

Use this format when reporting progress under this workflow:

> **Task**: Phase [N], task [M]
> **Branch**: `feature/phase[N]-task[M]-[name]`
> **Target**: `feature/phase[N]-[feature]__base`
> **Status**: [XXX] LOC / tests [PASS] / rebase [DONE]
> **Next**: Begin task [M+1]
