---
name: Browser Automation
slug: browser-automation
description: |
  Load when the user wants to navigate a website, click through a flow, fill a
  form, extract data from a page, or record an interaction as a reusable
  playbook.
icon: Globe
color: "#ef4444"
version: 2.1.0
category: automation
tools:
  - browser_open
  - browser_click
  - browser_type
  - browser_screenshot
  - browser_extract_text
  - browser_extract_data
  - browser_wait
  - browser_select
  - browser_scroll
  - browser_navigate
  - browser_close
  - browser_record_start
  - browser_record_stop
  - browser_record_status
  - list_playbooks
  - load_playbook
config_schema:
  type: object
  properties:
    default_timeout:
      type: integer
      default: 30000
---

Default operation timeout: {default_timeout}ms.

Always read the interactive-elements summary returned by `browser_open` before clicking — guessing selectors wastes turns.

CSS selectors are more reliable than text matching. Use `browser_wait` before interacting with anything that loads dynamically.

For repeat workflows: check `list_playbooks` first. To capture a new one, `browser_record_start` → do the task → `browser_record_stop` saves it as `.md`.

When you hit a CAPTCHA, popup, or unexpected state, take a screenshot and ask the user — don't click around hoping to escape.

Always `browser_close` when done; sessions hold significant resources.

See `references/selectors.md` for selector cookbook (login forms, infinite scroll, modal dismissal).

## Gotchas
