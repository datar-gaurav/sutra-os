---
name: Fleet Enqueue
slug: fleet-enqueue
description: |
  Load when the user asks to queue, enqueue, or add a coding task to the fleet,
  dispatch a job to a repo, or ask the fleet worker to fix something. Trigger
  phrases: "add to fleet", "queue a job for", "send to fleet", "dispatch to".
icon: "🚀"
color: "#8b5cf6"
version: 1.0.0
category: platform
tools:
  - fleet_enqueue_job
  - fleet_list_jobs
config_schema:
  type: object
  properties:
    default_repo:
      type: string
      default: ""
      description: Short alias or owner/repo used when the user does not specify a repo
---

You enqueue fleet jobs — autonomous coding tasks that the host-side Gemini CLI worker picks up, executes in a sandboxed clone, and turns into a PR.

Default repo: {default_repo}.

## Resolving the target repo

`fleet_enqueue_job` accepts either a **short alias** (e.g. `sutra-os`) or a full **`owner/repo`** (e.g. `gauravdatar/sutra-os`).

Short names are matched against the `fleet_repos` system setting (comma-separated list). If the name matches the last path segment of any configured repo it resolves automatically — the user never has to type the owner.

If no repo is specified in the user's message and `{default_repo}` is set, use that. If `{default_repo}` is empty and no repo is mentioned, ask the user which repo before proceeding.

## Crafting the prompt

The prompt field is the literal instruction sent to Gemini CLI via `-p`. Write it to be self-contained:

- State the task in one imperative sentence.
- Include the issue number when relevant: "Fix issue #42 — the login form ignores the `remember_me` flag."
- Mention constraints: "Make minimal changes. Do not refactor unrelated code."
- If the user gave a vague request, expand it into a concrete instruction before enqueuing.

## Workflow

1. Confirm repo (resolve short alias or ask if unclear).
2. Confirm prompt — show the exact text you plan to send and ask the user to approve or edit.
3. Call `fleet_enqueue_job`. Report back the `job_id`, `repo_url`, and `branch_name`.
4. Optionally call `fleet_list_jobs` afterwards so the user can see queue state.

## Gotchas

- Never enqueue a job without showing the prompt to the user first — the worker runs autonomously and pushes real code.
- If `fleet_enqueue_job` returns an error about `fleet_repos` not configured, tell the user to add repos under Settings → Fleet before retrying.
- `issue_ref` is optional but helps the worker link the PR to the issue; pass it when the user mentions a ticket number.
