---
name: Meeting Notes
slug: meeting-notes
description: |
  Load when the user shares a meeting transcript, summary, or recording link and
  wants notes captured plus action items extracted as trackable tasks.
icon: ClipboardList
color: "#ec4899"
version: 1.1.0
category: writing
tools:
  - create_task
  - save_memory
config_schema:
  type: object
  properties:
    format:
      type: string
      enum: [bullets, prose, action-items-only]
      default: bullets
---

Format: {format}.

Structure: Attendees & Date → Discussion → Decisions (with rationale) → Action Items (owner + deadline) → Follow-ups.

Every action item gets a `create_task` call. If owner/deadline aren't stated, write "owner: TBD" / "due: TBD" rather than guessing.

Save the summary via `save_memory` so future "what did we decide about X?" queries can retrieve it.

## Gotchas
