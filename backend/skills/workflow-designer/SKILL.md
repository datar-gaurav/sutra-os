---
name: Workflow Designer
slug: workflow-designer
description: |
  Load when the user wants to design, create, or run a multi-step workflow that
  chains multiple agents and tools. Trigger phrases: "build a workflow",
  "automate this", "create a pipeline".
icon: GitMerge
color: "#6366f1"
version: 1.1.0
category: automation
tools:
  - create_workflow
  - list_workflows
  - execute_workflow
  - get_workflow_details
config_schema:
  type: object
  properties:
    default_schedule:
      type: string
      enum: [manual, hourly, daily, weekly]
      default: manual
    auto_execute:
      type: boolean
      default: false
---

Default schedule: {default_schedule}. Auto-execute on create: {auto_execute}.

Before designing: `list_workflows` to see if an existing one can be reused or extended.

Aim for **3–7 nodes**. If you need more, the workflow is doing too much — split it.

For full node-type syntax (input, agent, conditional, loop, parallel, approval_gate, sub_workflow) and connection rules, read `references/node-types.md`.

Hard rules:
- Every node must be connected (no orphans).
- Conditional nodes need both `--true-->` and `--false-->` edges.
- Use `approval_gate` before any destructive, financial, or externally-visible action.
- `agent_id` fields must be real running agent UUIDs — ask the user if you don't have them.

Schedule intervals: hourly=60, daily=1440, weekly=10080 (minutes).

## Gotchas
