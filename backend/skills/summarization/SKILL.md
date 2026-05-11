---
name: Summarization
slug: summarization
description: |
  Load when the user asks to summarize, condense, or TL;DR a document, article,
  meeting transcript, or set of notes.
icon: BookOpen
color: "#a855f7"
version: 1.1.0
category: writing
tools:
  - search_knowledge_base
config_schema:
  type: object
  properties:
    max_length:
      type: number
      default: 200
    style:
      type: string
      enum: [bullets, paragraph, tldr]
      default: bullets
---

Style: {style}. Max length: {max_length} words.

Lead with the single most important takeaway.

Preserve numbers, dates, and proper nouns verbatim from the source. Never introduce information that isn't there.

- `bullets` — 5–7 bullets, each a complete sentence under 20 words.
- `paragraph` — topic sentence + 2–3 supporting + conclusion.
- `tldr` — 1–2 sentences max.

If summarizing multiple sources, note where they agree and where they conflict.

## Gotchas
