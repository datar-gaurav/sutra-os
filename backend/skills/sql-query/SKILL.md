---
name: SQL Query
slug: sql-query
description: |
  Load when the user asks to write, optimize, debug, or explain a SQL query.
  Trigger phrases: "write a query", "SQL for", "why is this slow", "explain this
  query".
icon: Database
color: "#14b8a6"
version: 1.1.0
category: data
tools: []
config_schema:
  type: object
  properties:
    dialect:
      type: string
      enum: [postgresql, mysql, sqlite, bigquery, snowflake]
      default: postgresql
    safety_mode:
      type: boolean
      default: true
---

Dialect: {dialect}. Safety mode: {safety_mode}.

Prefer CTEs to nested subqueries when the query has more than two levels of selection — readability matters more than micro-perf at this level.

Use window functions over self-joins for ranks and running totals.

When safety_mode is on, never emit `DELETE`, `DROP`, `TRUNCATE`, or unguarded `UPDATE` without showing the query first and asking the user to confirm.

When optimizing: suggest missing indexes by pointing at the predicates that would benefit. Rewrite correlated subqueries as joins when possible.

## Gotchas
