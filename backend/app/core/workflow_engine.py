"""Enhanced workflow execution engine supporting conditional, parallel, approval gate, and loop nodes."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 0  # Per-node default; override via node data "max_retries"
RETRY_BACKOFF_BASE = 2  # Exponential backoff base in seconds
DEFAULT_NODE_TIMEOUT = 300  # 5 minutes default; override via node data "timeout_seconds"


def _build_graph(nodes: list, edges: list) -> tuple[dict, dict, dict]:
    """
    Returns:
      node_map: {node_id -> node}
      successors: {node_id -> [(target_id, source_handle)]}   # source_handle is "true"/"false"/None
      predecessors: {node_id -> [source_id]}
    """
    node_map = {n["id"]: n for n in nodes}
    successors: dict[str, list] = {n["id"]: [] for n in nodes}
    predecessors: dict[str, list] = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        handle = edge.get("sourceHandle")  # "true", "false", or None
        if src and tgt and src in successors and tgt in predecessors:
            successors[src].append((tgt, handle))
            predecessors[tgt].append(src)

    return node_map, successors, predecessors


def _topo_sort(node_map: dict, predecessors: dict) -> list[str]:
    """Kahn's algorithm — returns nodes in execution order.

    Raises ValueError if the graph contains a cycle.
    """
    in_degree = {nid: len(preds) for nid, preds in predecessors.items()}
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        # We don't need edges here, just decrement any successors
        for other in node_map:
            if other != nid and nid in predecessors.get(other, []):
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

    if len(order) != len(node_map):
        remaining = set(node_map.keys()) - set(order)
        raise ValueError(
            f"Workflow graph contains a cycle involving nodes: {remaining}. "
            "Remove the cycle to execute this workflow."
        )

    return order


def validate_workflow_dag(definition: dict) -> list[str]:
    """Validate a workflow definition and return a list of error messages (empty = valid)."""
    errors: list[str] = []
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not nodes:
        return errors  # Empty workflow is valid (blank canvas)

    node_map, successors, predecessors = _build_graph(nodes, edges)

    # Cycle detection
    try:
        _topo_sort(node_map, predecessors)
    except ValueError as e:
        errors.append(str(e))

    # Check for disconnected nodes (no edges at all)
    if len(nodes) > 1:
        connected = set()
        for edge in edges:
            connected.add(edge.get("source"))
            connected.add(edge.get("target"))
        for n in nodes:
            if n["id"] not in connected:
                errors.append(f"Node '{n.get('data', {}).get('label', n['id'])}' is disconnected.")

    return errors


async def _evaluate_condition(condition: str, text: str, agent_id: str | None) -> bool:
    """Ask an LLM (via the orchestrator) whether `text` satisfies `condition`. Falls back to False."""
    if not agent_id:
        return True
    try:
        from app.core.orchestrator import orchestrator
        from app.core.agent_manager import agent_manager
        from app.db.session import async_session_factory
        if not agent_manager.is_running(agent_id):
            return True
        prompt = (
            f"Evaluate whether the following text satisfies this condition:\n"
            f"Condition: {condition}\n\n"
            f"Text:\n{text}\n\n"
            f"Answer with ONLY 'YES' or 'NO'."
        )
        async with async_session_factory() as db:
            result = await orchestrator.route_message(
                agent_id=agent_id, message=prompt, db=db
            )
        answer = result.get("output", "").strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.warning(f"Condition evaluation failed: {e}")
        return True


async def _invoke_agent(
    agent_id: str,
    prompt: str,
    max_retries: int = 0,
    timeout_seconds: int = DEFAULT_NODE_TIMEOUT,
) -> str:
    """Call an agent and return its text output. Retries with exponential backoff on failure.

    Args:
        agent_id: The agent to invoke.
        prompt: The prompt to send.
        max_retries: Number of retries on failure (exponential backoff).
        timeout_seconds: Max seconds to wait per attempt. 0 = no timeout.
    """
    from app.core.orchestrator import orchestrator
    from app.core.agent_manager import agent_manager
    from app.db.session import async_session_factory

    if not agent_manager.is_running(agent_id):
        return f"[Agent {agent_id} is not running]"

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            # Pass a db session so purpose-based smart routing, daily budget
            # checks, and memory injection apply — same path as chat.
            async with async_session_factory() as db:
                coro = orchestrator.route_message(
                    agent_id=agent_id, message=prompt, db=db
                )
                if timeout_seconds and timeout_seconds > 0:
                    result = await asyncio.wait_for(coro, timeout=timeout_seconds)
                else:
                    result = await coro
            return result.get("output", "[No output]")
        except asyncio.TimeoutError:
            last_error = TimeoutError(
                f"Agent {agent_id} timed out after {timeout_seconds}s"
            )
            logger.warning(f"Agent {agent_id} timed out after {timeout_seconds}s (attempt {attempt + 1})")
            if attempt >= max_retries:
                break
            wait = RETRY_BACKOFF_BASE ** attempt
            await asyncio.sleep(wait)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    f"Agent {agent_id} attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(f"Agent {agent_id} failed after {attempt + 1} attempts: {e}")

    return f"[Error after {max_retries + 1} attempts: {last_error}]"


async def execute_workflow_enhanced(workflow_id: str, initial_input: str = "", current_depth: int = 0) -> dict[str, Any]:
    """
    Enhanced workflow executor supporting:
      - input: static text input (falls back to initial_input if value is empty)
      - agent: LLM agent node (prompt template with {input})
      - conditional: route to true/false branch based on LLM evaluation
      - parallel: execute multiple branches concurrently, join results
      - approval_gate: pause and create a pending ApprovalRequest
      - loop: repeat a prompt N times, feeding output back as input
      - sub_workflow: execute another workflow as a node

    Returns a dict with:
      - status: "success" | "failed" | "waiting_approval"
      - logs: list of log entries
      - results: {node_id -> output}
      - final_output: joined output of all terminal nodes
    """
    from app.db.session import async_session_factory
    from app.models.workflow import Workflow
    from app.models.approval_request import ApprovalRequest, ApprovalStatus

    if current_depth > 10:
        return {
            "status": "failed", 
            "logs": [{"type": "error", "message": "Max sub-workflow recursion depth reached (10)"}], 
            "results": {},
            "final_output": ""
        }

    logs: list[dict] = []
    results: dict[str, str] = {}

    def log(node_id: str | None, type: str, message: str):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node_id": node_id,
            "type": type,
            "message": message,
        }
        logs.append(entry)
        logger.info(f"[workflow:{workflow_id}] [{type}] {message[:200]}")

    async with async_session_factory() as db:
        workflow = await db.get(Workflow, workflow_id)
        if not workflow or not workflow.is_active:
            return {"status": "failed", "logs": logs, "results": {}, "final_output": ""}

        definition = workflow.definition or {}
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

    if not nodes:
        return {"status": "failed", "logs": [{"type": "error", "message": "Empty workflow"}], "results": {}, "final_output": ""}

    node_map, successors, predecessors = _build_graph(nodes, edges)

    # Validate graph is a DAG (no cycles)
    try:
        exec_order = _topo_sort(node_map, predecessors)
    except ValueError as e:
        log(None, "error", str(e))
        return {"status": "failed", "logs": logs, "results": {}, "final_output": ""}

    # Track which nodes to skip (pruned by conditional routing)
    skipped: set[str] = set()
    # Track parallel fan-in: node -> list of inputs gathered
    parallel_inputs: dict[str, list[str]] = {}

    for node_id in exec_order:
        if node_id in skipped:
            log(node_id, "info", f"Skipping node {node_id} (pruned by conditional)")
            continue

        node = node_map[node_id]
        node_type = node.get("type", "")
        data = node.get("data", {})

        # Gather input from all predecessor results
        pred_ids = predecessors.get(node_id, [])
        input_parts = [results[p] for p in pred_ids if p in results and p not in skipped]

        # For parallel fan-in: collect deferred inputs
        if node_id in parallel_inputs:
            input_parts = parallel_inputs[node_id] + input_parts

        # Feed initial_input to start nodes (nodes with no predecessors)
        if not pred_ids and initial_input:
            input_parts = [initial_input] + input_parts

        input_text = "\n".join(input_parts).strip()

        # ─── INPUT ────────────────────────────────────────────────────────────
        if node_type == "input":
            value = data.get("value", "")
            results[node_id] = value if value else input_text
            log(node_id, "info", f"Input node '{data.get('label', node_id)}':\n{results[node_id]}")

        # ─── AGENT ────────────────────────────────────────────────────────────
        elif node_type == "agent":
            agent_id = data.get("agent_id", "")
            prompt_template = data.get("prompt", "{input}")
            prompt = prompt_template.replace("{input}", input_text)
            node_retries = int(data.get("max_retries", DEFAULT_MAX_RETRIES))
            node_timeout = int(data.get("timeout_seconds", DEFAULT_NODE_TIMEOUT))
            log(node_id, "info", f"Agent node '{data.get('label', node_id)}' → agent {agent_id}" +
                (f" (retries: {node_retries})" if node_retries else "") +
                (f" (timeout: {node_timeout}s)" if node_timeout != DEFAULT_NODE_TIMEOUT else ""))
            output = await _invoke_agent(agent_id, prompt, max_retries=node_retries, timeout_seconds=node_timeout)
            results[node_id] = output
            is_error = output.startswith("[Error") or output.startswith("[Agent")
            log(node_id, "error" if is_error else "success", f"Agent output:\n{output}")

        # ─── CONDITIONAL ──────────────────────────────────────────────────────
        elif node_type == "conditional":
            condition = data.get("condition", "")
            eval_agent_id = data.get("agent_id", "")
            log(node_id, "info", f"Conditional '{data.get('label', node_id)}': evaluating — {condition!r}")

            passed = await _evaluate_condition(condition, input_text, eval_agent_id or None)
            result_label = "TRUE" if passed else "FALSE"
            results[node_id] = input_text  # pass input through unchanged
            log(node_id, "info", f"Condition result: {result_label}")

            # Prune the branch that wasn't taken
            for (tgt, handle) in successors.get(node_id, []):
                if handle == "true" and not passed:
                    skipped.add(tgt)
                elif handle == "false" and passed:
                    skipped.add(tgt)

        # ─── PARALLEL ─────────────────────────────────────────────────────────
        elif node_type == "parallel":
            # Fan-out: execute all direct successors concurrently
            child_ids = [tgt for (tgt, _) in successors.get(node_id, [])]
            log(node_id, "info", f"Parallel node '{data.get('label', node_id)}': fan-out to {child_ids}")

            async def run_branch(child_id: str) -> tuple[str, str]:
                child_node = node_map.get(child_id, {})
                child_data = child_node.get("data", {})
                child_type = child_node.get("type", "")
                if child_type == "agent":
                    tmpl = child_data.get("prompt", "{input}")
                    prompt = tmpl.replace("{input}", input_text)
                    retries = int(child_data.get("max_retries", DEFAULT_MAX_RETRIES))
                    timeout = int(child_data.get("timeout_seconds", DEFAULT_NODE_TIMEOUT))
                    output = await _invoke_agent(
                        child_data.get("agent_id", ""), prompt,
                        max_retries=retries, timeout_seconds=timeout,
                    )
                    return child_id, output
                return child_id, input_text

            branch_results = await asyncio.gather(*[run_branch(cid) for cid in child_ids])
            for child_id, output in branch_results:
                results[child_id] = output
                log(child_id, "success", f"Parallel branch '{child_id}':\n{output}")

            # Mark child nodes as already executed so the main loop skips them
            skipped.update(child_ids)

            # Find the first downstream node after all branches and feed joined results
            all_outputs = [out for _, out in branch_results]
            joined = "\n\n---\n\n".join(all_outputs)
            results[node_id] = joined

        # ─── APPROVAL GATE ────────────────────────────────────────────────────
        elif node_type == "approval_gate":
            title = data.get("label", "Workflow Approval Required")
            description = data.get("description", "")
            log(node_id, "info", f"Approval gate '{title}': checking for existing approval")

            async with async_session_factory() as db:
                from sqlalchemy import select
                # Look for an already-approved request for this workflow+node
                stmt = select(ApprovalRequest).where(
                    ApprovalRequest.workflow_id == workflow_id,
                    ApprovalRequest.node_id == node_id,
                    ApprovalRequest.status == ApprovalStatus.approved.value,
                )
                existing = (await db.execute(stmt)).scalars().first()

                if existing:
                    log(node_id, "success", "Approval already granted by reviewer. Continuing.")
                    results[node_id] = input_text
                else:
                    # Create a pending approval request
                    req = ApprovalRequest(
                        workflow_id=workflow_id,
                        node_id=node_id,
                        title=title,
                        description=description or f"Workflow paused at '{title}'. Review and approve to continue.",
                        context={"input": input_text, "results_so_far": results},
                        status=ApprovalStatus.pending.value,
                    )
                    db.add(req)
                    await db.commit()
                    log(node_id, "warning",
                        f"Workflow paused — approval required. Request ID: {req.id}")
                    return {"status": "waiting_approval", "logs": logs, "results": results, "final_output": ""}

        # ─── LOOP ─────────────────────────────────────────────────────────────
        elif node_type == "loop":
            agent_id = data.get("agent_id", "")
            prompt_template = data.get("prompt", "{input}")
            max_iterations = int(data.get("max_iterations", 3))
            node_retries = int(data.get("max_retries", DEFAULT_MAX_RETRIES))
            node_timeout = int(data.get("timeout_seconds", DEFAULT_NODE_TIMEOUT))
            log(node_id, "info",
                f"Loop node '{data.get('label', node_id)}': {max_iterations} iterations, agent {agent_id}")

            current = input_text
            for i in range(max_iterations):
                prompt = prompt_template.replace("{input}", current)
                output = await _invoke_agent(agent_id, prompt, max_retries=node_retries, timeout_seconds=node_timeout)
                log(node_id, "info", f"Loop iteration {i + 1}/{max_iterations}:\n{output}")
                current = output

            results[node_id] = current
            log(node_id, "success", f"Loop complete. Final output:\n{current}")

        # ─── DISCUSSION ───────────────────────────────────────────────────────
        elif node_type == "discussion":
            disc_type = data.get("discussion_type", "brainstorm")
            disc_title = data.get("label", "Workflow Discussion")
            disc_topic = data.get("topic", "{input}")
            disc_topic = disc_topic.replace("{input}", input_text)
            participant_names = [
                n.strip()
                for n in data.get("participant_names", "").split(",")
                if n.strip()
            ]
            moderator_name = data.get("moderator_name", "").strip() or None
            max_rounds = int(data.get("max_rounds", 2))

            log(node_id, "info",
                f"Discussion node '{disc_title}': type={disc_type}, "
                f"participants={participant_names}, rounds={max_rounds}")

            try:
                from sqlalchemy import select
                from app.models.agent import Agent
                from app.models.discussion import Discussion as DiscModel
                from app.core.discussion_engine import discussion_engine

                async with async_session_factory() as db:
                    # Resolve participant names to IDs
                    participant_ids = []
                    for pname in participant_names:
                        result = await db.execute(
                            select(Agent).where(Agent.name.ilike(pname))
                        )
                        agent = result.scalars().first()
                        if agent:
                            participant_ids.append(agent.id)
                        else:
                            log(node_id, "warning", f"Participant '{pname}' not found")

                    # Resolve moderator
                    moderator_id = None
                    if moderator_name:
                        result = await db.execute(
                            select(Agent).where(Agent.name.ilike(moderator_name))
                        )
                        mod_agent = result.scalars().first()
                        if mod_agent:
                            moderator_id = mod_agent.id

                    if not participant_ids:
                        results[node_id] = "[No participants found for discussion]"
                        log(node_id, "error", "No valid participants resolved")
                        continue

                    disc = DiscModel(
                        title=disc_title,
                        topic=disc_topic,
                        type=disc_type,
                        participant_agent_ids=participant_ids,
                        moderator_agent_id=moderator_id,
                        max_rounds=max_rounds,
                        messages=[],
                    )
                    db.add(disc)
                    await db.commit()
                    await db.refresh(disc)
                    disc_id = disc.id

                # Run the discussion engine
                summary = ""
                action_items = []
                async for event in discussion_engine.run(disc_id):
                    if event.get("type") == "summary":
                        summary = event.get("summary", "")
                        action_items = event.get("action_items", [])
                    elif event.get("type") == "error":
                        log(node_id, "error", f"Discussion error: {event.get('message')}")

                output_parts = [f"DISCUSSION SUMMARY:\n{summary}"]
                if action_items:
                    output_parts.append(
                        "ACTION ITEMS:\n" + "\n".join(f"- {item}" for item in action_items)
                    )
                results[node_id] = "\n\n".join(output_parts)
                log(node_id, "success", f"Discussion concluded:\n{results[node_id]}")

            except Exception as e:
                results[node_id] = f"[Discussion failed: {e}]"
                log(node_id, "error", f"Discussion failed: {e}")

        # ─── SUB-WORKFLOW ─────────────────────────────────────────────────────
        elif node_type == "sub_workflow":
            sub_id = data.get("workflow_id", "")
            log(node_id, "info", f"Sub-workflow node '{data.get('label', node_id)}': executing {sub_id}")
            
            sub_result = await execute_workflow_enhanced(sub_id, initial_input=input_text, current_depth=current_depth + 1)
            
            # Merge logs
            for sl in sub_result.get("logs", []):
                logs.append({**sl, "message": f"[{data.get('label', node_id)}] {sl['message']}"})
                
            if sub_result["status"] == "waiting_approval":
                return {"status": "waiting_approval", "logs": logs, "results": results, "final_output": ""}
            
            if sub_result["status"] == "failed":
                results[node_id] = "[Sub-workflow failed]"
                log(node_id, "error", f"Sub-workflow {sub_id} failed.")
            else:
                results[node_id] = sub_result.get("final_output", "")
                log(node_id, "success", f"Sub-workflow {sub_id} finished.")

        else:
            log(node_id, "warning", f"Unknown node type '{node_type}' — skipping")
            results[node_id] = input_text

    # Calculate final output: join all nodes that have no successors and were not skipped
    final_parts = []
    for node_id in exec_order:
        if node_id not in skipped and not successors.get(node_id):
            if node_id in results:
                final_parts.append(results[node_id])
    
    final_output = "\n\n---\n\n".join(final_parts).strip()

    return {"status": "success", "logs": logs, "results": results, "final_output": final_output}
