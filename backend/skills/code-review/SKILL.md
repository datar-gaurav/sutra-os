---
name: Code Review
slug: code-review
description: |
  Load when the user asks to review code, audit a PR, find bugs in code they
  paste, or assess code quality. Trigger phrases: "review this", "look at my code",
  "is this right", "what's wrong with X".
icon: Code2
color: "#06b6d4"
version: 1.1.0
category: coding
tools:
  - read_file
  - search_files
config_schema:
  type: object
  properties:
    language:
      type: string
      default: any
      description: Programming language to focus on
    strictness:
      type: string
      enum: [strict, moderate, lenient]
      default: moderate
      description: How strictly to enforce coding standards
---

Read the actual files with `read_file` before commenting — never review code you haven't seen. Cite `file:line` for every issue.

Categorize findings as **Critical / Major / Minor / Suggestion**. Always pair a problem with a concrete fix, not just the observation.

Strictness ({strictness}):
- `strict` — flag every style deviation and untested branch.
- `moderate` — flag bugs, security issues, perf cliffs, and missing tests for non-trivial logic.
- `lenient` — only flag bugs and security issues.

End with a single-paragraph overall assessment.

## Gotchas
