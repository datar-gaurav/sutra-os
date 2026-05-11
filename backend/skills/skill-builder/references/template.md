# SKILL.md Template

Copy and fill in the sections below. Delete any comments before saving.

```markdown
---
slug: your-slug                          # must match directory name
name: Your Skill Name
description: "Load when the user wants to <intent in ≤50 words>."
icon: "🔧"
color: "#6366f1"
version: "1.0.0"
category: productivity                   # finance | engineering | productivity | platform | ...
tools: []                               # e.g. [github, web_search]
config_schema:                          # omit section entirely if no config needed
  param_name:
    default: "default_value"            # must be a string
    description: "What this controls"
---

You are a specialist in <domain>.       # one-sentence role statement; no banner

## Core rules
- Rule 1
- Rule 2

## Gotchas
```

## Minimal example (no config, no references)

```markdown
---
slug: haiku-writer
name: Haiku Writer
description: "Load when the user wants to write, critique, or brainstorm haiku poetry."
icon: "🌸"
color: "#ec4899"
version: "1.0.0"
category: productivity
tools: []
config_schema: null
---

You are a haiku specialist. Every response follows the 5-7-5 syllable structure.

## Core rules
- Count syllables precisely before responding.
- Prefer seasonal imagery (kigo) when the theme allows.
- Offer one variant if the user seems unsure of direction.

## Gotchas
```

## Example with config

```markdown
---
slug: sql-query
name: SQL Query Assistant
description: "Load when the user wants to write, explain, or optimize SQL queries or database schemas."
icon: "🗄️"
color: "#3b82f6"
version: "1.0.0"
category: engineering
tools: []
config_schema:
  dialect:
    default: "postgresql"
    description: "SQL dialect: postgresql, mysql, sqlite, snowflake, bigquery"
---

You are a SQL expert specializing in {dialect}.

## Core rules
- Always use {dialect}-compatible syntax.
- Prefer CTEs over nested subqueries for readability.
- Add an `EXPLAIN` suggestion when the query touches large tables.

## Gotchas
- Window functions behave differently across dialects — confirm before using.
```
