---
name: GitHub Operations
slug: github-operations
description: |
  Load when the user asks to create a GitHub issue or PR, push code, commit
  changes, or do anything that touches a git repository on GitHub.
icon: Github
color: "#1f2937"
version: 1.1.0
category: coding
tools:
  - create_github_issue
  - create_github_pr
  - commit_and_push
  - read_file
config_schema:
  type: object
  properties:
    default_repo:
      type: string
      default: ""
    branch_prefix:
      type: string
      default: feature/
---

Default repo: {default_repo}. Branch prefix: {branch_prefix}.

**Issues** — title is an imperative verb + concise description ("Fix auth timeout on mobile"). Body: Problem → Repro → Expected vs Actual → Environment → Proposed Fix.

**PRs** — branch `{branch_prefix}kebab-case-description`. Body: Summary → Test plan → Screenshots if UI → Breaking changes. Link the issue with `Closes #N`.

**Commits** — `type(scope): description`. Types: feat, fix, refactor, docs, test, chore.

Never force-push to `main` or `master`. Never skip hooks (`--no-verify`) unless the user explicitly asks.

## Gotchas
