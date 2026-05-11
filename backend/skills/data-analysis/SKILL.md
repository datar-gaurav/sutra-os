---
name: Data Analysis
slug: data-analysis
description: |
  Load when the user wants analysis on a dataset — trends, distributions, summary
  statistics, or insights from a CSV/JSON/Excel file.
icon: BarChart3
color: "#10b981"
version: 1.1.0
category: data
tools:
  - analyze_data
  - read_file
config_schema:
  type: object
  properties:
    preferred_format:
      type: string
      enum: [table, narrative, bullets]
      default: narrative
---

Output format: {preferred_format}.

Before drawing conclusions: shape, dtypes, missing values, basic stats, and a look at distributions/outliers. State your assumptions explicitly.

Don't confuse correlation with causation — say "associated with" unless there's an experimental setup that earns the word "caused".

Numbers, not adjectives: "revenue rose 23% QoQ" beats "revenue rose significantly".

End with concrete recommendations the reader can act on, and a "Data quality notes" section if anything could invalidate the conclusions.

## Gotchas
