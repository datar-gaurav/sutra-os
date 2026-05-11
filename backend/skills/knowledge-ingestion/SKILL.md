---
name: Knowledge Ingestion
slug: knowledge-ingestion
description: |
  Load when the user wants to ingest a URL, document, or text snippet into the
  knowledge base for future retrieval. Trigger phrases: "save this", "ingest",
  "add to KB".
icon: Upload
color: "#059669"
version: 1.1.0
category: research
tools:
  - ingest_url_to_kb
  - scrape_webpage
  - search_knowledge_base
config_schema:
  type: object
  properties:
    target_kb_id:
      type: string
      default: ""
    chunk_strategy:
      type: string
      enum: [page, section, paragraph]
      default: section
---

Target KB: {target_kb_id}. Chunk strategy: {chunk_strategy}.

Before ingesting, search the KB for the same source — duplicate ingestion creates noisy retrieval.

For URLs: `ingest_url_to_kb` directly.
For pages requiring navigation (login, JS): `scrape_webpage` first, then ingest the extracted text.

After ingest, verify by searching for a distinctive phrase from the document. If it doesn't surface, the ingestion silently failed.

Flag stale-prone sources (pricing pages, news, changelogs) in the title so they can be re-ingested later.

## Gotchas
