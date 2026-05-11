# Workflow Node Types

## input
Static text seeded into the first downstream node. Use for fixed prompts or boilerplate.
```
[input]
  Find PRs with no reviews for over 48 hours
```

## agent
Calls one agent with a prompt. `{input}` is the placeholder for upstream output.
```
[agent agent_id=abc-123]
  Summarize this PR list: {input}
```

## conditional
LLM evaluates `condition` and routes. Both `--true-->` and `--false-->` are required.
```
[conditional agent_id=abc-123 condition="contains a security issue"]
  --true--> [agent ...]
  --false--> [agent ...]
```

## loop
Repeats an agent prompt up to `max_iterations`, feeding each output back as input. Good for iterative refinement.
```
[loop agent_id=abc-123 max_iterations=3]
  Refine this draft: {input}
```

## parallel
Fans out to multiple agent branches concurrently. Downstream node receives all branch outputs concatenated.

## approval_gate
Pauses the workflow and creates a human approval request. Resumes only when approved. Required before any destructive, financial, or externally-visible action.

## sub_workflow
Embeds another existing workflow. Specify both `workflow_id` and `workflow_name` (the name is for display only).
