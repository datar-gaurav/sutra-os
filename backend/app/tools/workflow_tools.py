"""Workflow tools — allow agents to create, list, execute, and inspect workflows."""

import json
import logging
import re
import uuid

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

WORKFLOW_TOOL_IDS = {
    "create_workflow",
    "list_workflows",
    "execute_workflow",
    "get_workflow_details",
}

# ─── Markdown parser (shared with routes) ────────────────────────────────────

_EDGE_STYLE = {"stroke": "#c4b5a0", "strokeWidth": 1.5, "strokeDasharray": "6 4"}
_MARKER_END = {"type": "ArrowClosed", "color": "#c4b5a0", "width": 18, "height": 18}


def _parse_workflow_markdown(md: str) -> tuple[str, str | None, int | None, bool, dict]:
    """
    Parse a Sutra workflow Markdown document.
    Returns: (name, description, schedule_interval, is_active, definition)
    """
    name = "Agent-Created Workflow"
    description: str | None = None
    schedule_interval: int | None = None
    is_active = True

    name_match = re.search(r"^#\s+Workflow:\s+(.+)$", md, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip()

    schedule_match = re.search(r"\*\*Schedule:\*\*\s+Every\s+(\d+)\s+minutes?", md, re.IGNORECASE)
    if schedule_match:
        schedule_interval = int(schedule_match.group(1))

    active_match = re.search(r"\*\*Active:\*\*\s+(true|false)", md, re.IGNORECASE)
    if active_match:
        is_active = active_match.group(1).lower() == "true"

    header_end = name_match.end() if name_match else 0
    nodes_start = md.find("## Nodes")
    if nodes_start > header_end:
        candidate = md[header_end:nodes_start].strip()
        desc_lines = [
            l for l in candidate.splitlines()
            if l.strip()
            and not l.startswith("**Schedule:**")
            and not l.startswith("**Active:**")
        ]
        if desc_lines:
            description = " ".join(desc_lines)

    edges_start = md.find("## Edges")
    nodes_section = md[nodes_start:edges_start] if edges_start > 0 else md[nodes_start:]

    node_blocks = re.split(r"(?=###\s+\d+\.)", nodes_section)
    nodes: list[dict] = []
    label_to_id: dict[str, str] = {}
    x_step = 250

    for i, block in enumerate(node_blocks):
        block = block.strip()
        if not block or block.startswith("## Nodes"):
            continue
        header_match = re.match(r"###\s+\d+\.\s+\[(\w+)\]\s+(.+)", block)
        if not header_match:
            continue
        ntype = header_match.group(1)
        label = header_match.group(2).strip()

        kv: dict[str, str] = {}
        for kv_match in re.finditer(r"^-\s+(\w+):\s*(.*)$", block, re.MULTILINE):
            kv[kv_match.group(1)] = kv_match.group(2).strip()

        node_id = kv.get("id") or f"{ntype}-{uuid.uuid4().hex[:10]}"
        label_to_id[label] = node_id

        data: dict = {"label": label}
        if ntype == "input":
            data["value"] = kv.get("value", "")
        elif ntype == "agent":
            data["agent_id"] = kv.get("agent_id", "")
            data["prompt"] = kv.get("prompt", "{input}")
            data["max_retries"] = int(kv.get("max_retries", "0") or "0")
        elif ntype == "conditional":
            data["condition"] = kv.get("condition", "")
            data["agent_id"] = kv.get("agent_id", "")
        elif ntype == "loop":
            data["agent_id"] = kv.get("agent_id", "")
            data["prompt"] = kv.get("prompt", "{input}")
            data["max_iterations"] = int(kv.get("max_iterations", "3") or "3")
            data["max_retries"] = int(kv.get("max_retries", "0") or "0")
        elif ntype == "approval_gate":
            data["description"] = kv.get("description", "")
        elif ntype == "discussion":
            data["discussion_type"] = kv.get("discussion_type", "brainstorm")
            data["topic"] = kv.get("topic", "{input}")
            data["participant_names"] = kv.get("participant_names", "")
            data["moderator_name"] = kv.get("moderator_name", "")
            data["max_rounds"] = int(kv.get("max_rounds", "2") or "2")
        elif ntype == "sub_workflow":
            data["workflow_id"] = kv.get("workflow_id", "")
            data["workflow_name"] = kv.get("workflow_name", "")

        nodes.append({
            "id": node_id,
            "type": ntype,
            "position": {"x": 200 + i * x_step, "y": 150},
            "data": data,
        })

    edges: list[dict] = []
    if edges_start > 0:
        for line in md[edges_start:].splitlines():
            line = line.strip()
            handle_match = re.match(r"^(.+?)\s+--(\w+)-->\s+(.+)$", line)
            plain_match = re.match(r"^(.+?)\s+-->\s+(.+)$", line)

            if handle_match:
                src_label = handle_match.group(1).strip()
                handle = handle_match.group(2).strip()
                tgt_label = handle_match.group(3).strip()
            elif plain_match:
                src_label = plain_match.group(1).strip()
                handle = None
                tgt_label = plain_match.group(2).strip()
            else:
                continue

            src_id = label_to_id.get(src_label)
            tgt_id = label_to_id.get(tgt_label)
            if not src_id or not tgt_id:
                continue

            edges.append({
                "id": f"e-{uuid.uuid4().hex[:8]}",
                "source": src_id,
                "target": tgt_id,
                "sourceHandle": handle,
                "type": "smoothstep",
                "style": _EDGE_STYLE,
                "markerEnd": _MARKER_END,
            })

    return name, description, schedule_interval, is_active, {"nodes": nodes, "edges": edges}


# ─── Tool factory ─────────────────────────────────────────────────────────────

def create_workflow_tools():
    """Create workflow management LangChain tools."""

    @tool
    async def create_workflow(markdown_definition: str) -> str:
        """Create a new Sutra workflow from a Markdown definition.

        The markdown must follow the Sutra workflow format:

        # Workflow: <name>
        <optional description>
        **Schedule:** Every <N> minutes   (or omit for manual)
        **Active:** true

        ## Nodes
        ### 1. [input] Start
        - id: input-001
        - value: Initial input text

        ### 2. [agent] My Agent Node
        - id: agent-001
        - agent_id: <uuid of a running agent>
        - prompt: Process this: {input}
        - max_retries: 1

        ### 3. [conditional] Quality Gate
        - id: cond-001
        - condition: The output meets quality standards
        - agent_id: <uuid of evaluator agent>

        ### 4. [loop] Refine
        - id: loop-001
        - agent_id: <uuid>
        - prompt: Improve: {input}
        - max_iterations: 3

        ### 5. [approval_gate] Approve
        - id: gate-001
        - description: Human approval required before continuing

        ### 6. [parallel] Fan Out
        - id: parallel-001

        ### 7. [discussion] Team Brainstorm
        - id: disc-001
        - discussion_type: brainstorm
        - topic: What should we build next? Context: {input}
        - participant_names: Nova, Engineer, Analyst
        - moderator_name: Nova
        - max_rounds: 2

        ### 8. [sub_workflow] Sub-Process
        - id: sub-001
        - workflow_id: <uuid of another workflow>
        - workflow_name: <name for display>

        ## Edges
        Start --> My Agent Node
        My Agent Node --> Quality Gate
        Quality Gate --true--> Publish
        Quality Gate --false--> Refine

        Returns the created workflow's ID and name.
        """
        from app.db.session import async_session_factory
        from app.models.workflow import Workflow
        from app.core.workflow_engine import validate_workflow_dag

        try:
            name, description, schedule_interval, is_active, definition = _parse_workflow_markdown(
                markdown_definition
            )

            if definition.get("nodes"):
                errors = validate_workflow_dag(definition)
                if errors:
                    return json.dumps({"error": "Workflow validation failed", "details": errors})

            async with async_session_factory() as db:
                workflow = Workflow(
                    name=name,
                    description=description,
                    schedule_interval=schedule_interval,
                    is_active=is_active,
                    definition=definition,
                )
                db.add(workflow)
                await db.flush()
                await db.refresh(workflow)
                await db.commit()

            from app.core.scheduler import sync_workflows
            await sync_workflows()

            node_count = len(definition.get("nodes", []))
            edge_count = len(definition.get("edges", []))
            return json.dumps({
                "success": True,
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "nodes": node_count,
                "edges": edge_count,
                "schedule": f"Every {schedule_interval} minutes" if schedule_interval else "Manual",
                "message": f"Workflow '{name}' created with {node_count} nodes and {edge_count} edges.",
            })
        except Exception as e:
            logger.error(f"create_workflow error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def list_workflows(search: str = "") -> str:
        """List all workflows. Optionally filter by name substring.
        Returns each workflow's ID, name, description, schedule, status, and last run info."""
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.workflow import Workflow

        try:
            async with async_session_factory() as db:
                result = await db.execute(select(Workflow).order_by(Workflow.name))
                workflows = result.scalars().all()

            if search:
                s = search.lower()
                workflows = [w for w in workflows if s in w.name.lower()]

            return json.dumps({
                "workflows": [
                    {
                        "id": w.id,
                        "name": w.name,
                        "description": w.description,
                        "schedule": f"Every {w.schedule_interval} minutes" if w.schedule_interval else "Manual",
                        "is_active": w.is_active,
                        "last_run_status": w.last_run_status,
                        "last_run_at": w.last_run_at.isoformat() if w.last_run_at else None,
                        "node_count": len((w.definition or {}).get("nodes", [])),
                    }
                    for w in workflows
                ],
                "total": len(workflows),
            })
        except Exception as e:
            logger.error(f"list_workflows error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def execute_workflow(workflow_id: str, initial_input: str = "") -> str:
        """Execute a workflow by its ID. Optionally provide an initial input string
        that will be passed to the first node. Returns immediately — execution runs
        in the background. Use get_workflow_details to check last_run_status later."""
        import asyncio
        from app.db.session import async_session_factory
        from app.models.workflow import Workflow

        try:
            async with async_session_factory() as db:
                workflow = await db.get(Workflow, workflow_id)
                if not workflow:
                    return json.dumps({"error": f"Workflow '{workflow_id}' not found."})
                if not workflow.is_active:
                    return json.dumps({"error": f"Workflow '{workflow.name}' is not active."})
                name = workflow.name

            from app.core.scheduler import execute_workflow as _exec
            asyncio.create_task(_exec(workflow_id, initial_input=initial_input))

            return json.dumps({
                "success": True,
                "workflow_id": workflow_id,
                "workflow_name": name,
                "message": f"Workflow '{name}' execution started. Check get_workflow_details for results.",
            })
        except Exception as e:
            logger.error(f"execute_workflow error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def get_workflow_details(workflow_id: str) -> str:
        """Get full details of a workflow including its node/edge structure,
        schedule, last run status, and the most recent execution logs."""
        from app.db.session import async_session_factory
        from app.models.workflow import Workflow

        try:
            async with async_session_factory() as db:
                workflow = await db.get(Workflow, workflow_id)
                if not workflow:
                    return json.dumps({"error": f"Workflow '{workflow_id}' not found."})

                definition = workflow.definition or {}
                nodes = definition.get("nodes", [])
                edges = definition.get("edges", [])

                node_summaries = [
                    {
                        "id": n["id"],
                        "type": n.get("type"),
                        "label": n.get("data", {}).get("label"),
                        "agent_id": n.get("data", {}).get("agent_id"),
                    }
                    for n in nodes
                ]

                edge_summaries = [
                    {
                        "from": e.get("source"),
                        "to": e.get("target"),
                        "handle": e.get("sourceHandle"),
                    }
                    for e in edges
                ]

                # Last 10 log entries
                recent_logs = (workflow.last_run_logs or [])[-10:]

                return json.dumps({
                    "id": workflow.id,
                    "name": workflow.name,
                    "description": workflow.description,
                    "schedule": f"Every {workflow.schedule_interval} minutes" if workflow.schedule_interval else "Manual",
                    "is_active": workflow.is_active,
                    "last_run_status": workflow.last_run_status,
                    "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
                    "nodes": node_summaries,
                    "edges": edge_summaries,
                    "recent_logs": recent_logs,
                })
        except Exception as e:
            logger.error(f"get_workflow_details error: {e}")
            return json.dumps({"error": str(e)})

    return [create_workflow, list_workflows, execute_workflow, get_workflow_details]
