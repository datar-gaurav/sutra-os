---
name: Translation
slug: translation
description: |
  Load when the user wants text translated between languages, or asks for
  localized phrasing of an existing draft.
icon: Languages
color: "#f97316"
version: 1.1.0
category: writing
tools: []
config_schema:
  type: object
  properties:
    target_language:
      type: string
      default: English
    preserve_formatting:
      type: boolean
      default: true
---

Target language: {target_language}. Preserve formatting: {preserve_formatting}.

Translate idioms by the *closest cultural equivalent*, not literally. If no equivalent exists, give the literal translation plus a one-line note.

Preserve tone (formal/casual/technical) from the source.

When preserve_formatting is true, keep all markdown structure intact: headers, lists, bold/italic, code blocks, links.

For technical content, use the standard industry terminology in the target language — not a literal back-translation.

## Gotchas
