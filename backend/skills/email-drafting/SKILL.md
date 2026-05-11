---
name: Email Drafting
slug: email-drafting
description: |
  Load when the user asks to draft, compose, or send an email — or to write a
  Telegram message that is substantively a message draft (not a quick reply).
icon: Mail
color: "#f59e0b"
version: 1.1.0
category: writing
tools:
  - send_email
  - send_telegram_message
config_schema:
  type: object
  properties:
    tone:
      type: string
      enum: [formal, casual, persuasive, empathetic]
      default: formal
    signature:
      type: string
      default: ""
---

Tone: {tone}. Signature: {signature}.

Subject lines must say what the email is *about* — not "Following up" or "Quick question".

Skip the "I hope this email finds you well" preamble unless the recipient relationship calls for it. Get to the ask in the first or second sentence.

One ask per email. If there are multiple, number them and put a deadline next to each that has one.

Always show the draft to the user before sending unless they explicitly said "send it".

## Gotchas
