---
name: Report Writing
slug: report-writing
description: |
  Load when the user wants a written report produced from prior research, notes,
  or data — executive summary, technical write-up, or narrative report.
icon: FileText
color: "#6366f1"
version: 1.1.0
category: writing
tools:
  - read_file
  - write_file
  - search_knowledge_base
config_schema:
  type: object
  properties:
    report_style:
      type: string
      enum: [executive, technical, narrative]
      default: executive
---

Style: {report_style}.

- `executive` — TL;DR → Key Findings → Recommendations → Supporting Data.
- `technical` — Abstract → Background → Methodology → Results → Discussion → Conclusion.
- `narrative` — Context → Story arc → Evidence → Implications → Next Steps.

Lead with the most important finding, not background. Every claim is backed by data or a cited source — no exceptions.

End with concrete next steps. If owners are identifiable, name them.

Save the final report via `write_file`.

## Gotchas
