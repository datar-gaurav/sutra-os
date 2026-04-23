from typing import List
import json
import logging
import re
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.workflow import Workflow
from pydantic import BaseModel
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflows"])

class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    schedule_interval: Optional[int] = None
    definition: Optional[Dict[str, Any]] = None

class WorkflowResponse(WorkflowCreate):
    id: str
    is_active: bool
    last_run_at: Optional[Any] = None
    last_run_status: Optional[str] = None
    last_run_logs: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True

@router.get("/", response_model=List[WorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow))
    return result.scalars().all()

@router.post("/", response_model=WorkflowResponse, status_code=201)
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    # Validate DAG before saving (skip for empty/new workflows)
    if data.definition and data.definition.get("nodes"):
        from app.core.workflow_engine import validate_workflow_dag
        errors = validate_workflow_dag(data.definition)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

    workflow = Workflow(
        name=data.name,
        description=data.description,
        schedule_interval=data.schedule_interval,
        definition=data.definition or {}
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)

    from app.core.scheduler import sync_workflows
    await sync_workflows()
    return workflow

@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Validate DAG before saving (skip for empty workflows)
    if data.definition and data.definition.get("nodes"):
        from app.core.workflow_engine import validate_workflow_dag
        errors = validate_workflow_dag(data.definition)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

    workflow.name = data.name
    workflow.description = data.description
    workflow.schedule_interval = data.schedule_interval
    if data.definition is not None:
        workflow.definition = data.definition
        
    await db.flush()
    await db.refresh(workflow)
    
    from app.core.scheduler import sync_workflows
    await sync_workflows()
    return workflow

@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(workflow)
    await db.flush()
    
    from app.core.scheduler import sync_workflows
    await sync_workflows()
    return {"status": "deleted"}

@router.post("/validate")
async def validate_workflow(data: WorkflowCreate):
    """Validate a workflow definition without saving. Returns validation errors if any."""
    from app.core.workflow_engine import validate_workflow_dag
    errors = validate_workflow_dag(data.definition or {})
    return {"valid": len(errors) == 0, "errors": errors}


class WorkflowExecute(BaseModel):
    initial_input: Optional[str] = ""

@router.post("/{workflow_id}/execute")
async def execute_workflow_route(workflow_id: str, data: Optional[WorkflowExecute] = None, db: AsyncSession = Depends(get_db)):
    import asyncio
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    from app.core.scheduler import execute_workflow
    initial_input = data.initial_input if data else ""
    # Run in background so the endpoint returns immediately
    asyncio.create_task(execute_workflow(workflow_id, initial_input=initial_input))
    return {"status": "started"}


# ─── Export ──────────────────────────────────────────────────────────────────

def _workflow_to_markdown(workflow: Workflow) -> str:
    """Render a workflow as a Claude-readable / importable Markdown document."""
    definition = workflow.definition or {}
    nodes: list[dict] = definition.get("nodes", [])
    edges: list[dict] = definition.get("edges", [])

    # Build a label → id index for edge rendering
    id_to_label: dict[str, str] = {}
    for n in nodes:
        label = n.get("data", {}).get("label") or n["id"]
        id_to_label[n["id"]] = label

    lines: list[str] = []
    lines.append(f"# Workflow: {workflow.name}")
    lines.append("")
    if workflow.description:
        lines.append(workflow.description)
        lines.append("")
    schedule = f"Every {workflow.schedule_interval} minutes" if workflow.schedule_interval else "Manual"
    lines.append(f"**Schedule:** {schedule}  ")
    lines.append(f"**Active:** {'true' if workflow.is_active else 'false'}")
    lines.append("")
    lines.append("## Nodes")
    lines.append("")

    for idx, node in enumerate(nodes, 1):
        ntype = node.get("type", "unknown")
        data = node.get("data", {})
        label = data.get("label") or node["id"]
        lines.append(f"### {idx}. [{ntype}] {label}")
        lines.append(f"- id: {node['id']}")
        if ntype == "input":
            val = data.get("value", "")
            lines.append(f"- value: {val}")
        elif ntype == "agent":
            lines.append(f"- agent_id: {data.get('agent_id', '')}")
            lines.append(f"- prompt: {data.get('prompt', '{input}')}")
            lines.append(f"- max_retries: {data.get('max_retries', 0)}")
        elif ntype == "conditional":
            lines.append(f"- condition: {data.get('condition', '')}")
            lines.append(f"- agent_id: {data.get('agent_id', '')}")
        elif ntype == "loop":
            lines.append(f"- agent_id: {data.get('agent_id', '')}")
            lines.append(f"- prompt: {data.get('prompt', '{input}')}")
            lines.append(f"- max_iterations: {data.get('max_iterations', 3)}")
            lines.append(f"- max_retries: {data.get('max_retries', 0)}")
        elif ntype == "approval_gate":
            lines.append(f"- description: {data.get('description', '')}")
        elif ntype == "sub_workflow":
            lines.append(f"- workflow_id: {data.get('workflow_id', '')}")
            lines.append(f"- workflow_name: {data.get('workflow_name', '')}")
        # parallel has no extra fields
        lines.append("")

    lines.append("## Edges")
    lines.append("")
    for edge in edges:
        src_label = id_to_label.get(edge.get("source", ""), edge.get("source", ""))
        tgt_label = id_to_label.get(edge.get("target", ""), edge.get("target", ""))
        handle = edge.get("sourceHandle")
        if handle in ("true", "false"):
            lines.append(f"{src_label} --{handle}--> {tgt_label}")
        else:
            lines.append(f"{src_label} --> {tgt_label}")

    lines.append("")
    lines.append(f"<!-- exported_at: {datetime.utcnow().isoformat()}Z -->")
    return "\n".join(lines)


def _markdown_to_definition(md: str) -> tuple[str, Optional[str], Optional[int], bool, dict]:
    """
    Parse a Sutra workflow markdown document.
    Returns: (name, description, schedule_interval, is_active, definition)
    """
    name = "Imported Workflow"
    description: Optional[str] = None
    schedule_interval: Optional[int] = None
    is_active = True

    nodes: list[dict] = []
    edges: list[dict] = []

    # ── Header ──────────────────────────────────────────────────────────────
    name_match = re.search(r"^#\s+Workflow:\s+(.+)$", md, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip()

    schedule_match = re.search(r"\*\*Schedule:\*\*\s+Every\s+(\d+)\s+minutes?", md, re.IGNORECASE)
    if schedule_match:
        schedule_interval = int(schedule_match.group(1))

    active_match = re.search(r"\*\*Active:\*\*\s+(true|false)", md, re.IGNORECASE)
    if active_match:
        is_active = active_match.group(1).lower() == "true"

    # Description: text between header line and ## Nodes
    header_end = name_match.end() if name_match else 0
    nodes_start = md.find("## Nodes")
    if nodes_start > header_end:
        candidate = md[header_end:nodes_start].strip()
        # Strip schedule/active lines
        desc_lines = [
            l for l in candidate.splitlines()
            if l.strip() and not l.startswith("**Schedule:**") and not l.startswith("**Active:**")
        ]
        if desc_lines:
            description = " ".join(desc_lines)

    # ── Nodes ────────────────────────────────────────────────────────────────
    edges_start = md.find("## Edges")
    nodes_section = md[nodes_start:edges_start] if edges_start > 0 else md[nodes_start:]

    # Split into per-node blocks via ### headers
    node_blocks = re.split(r"(?=###\s+\d+\.)", nodes_section)
    label_to_id: dict[str, str] = {}

    x_offset = 200
    y_base = 150
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

        # Extract key-value pairs (lines starting with "- key: value")
        kv: dict[str, str] = {}
        for kv_match in re.finditer(r"^-\s+(\w+):\s*(.*)$", block, re.MULTILINE):
            kv[kv_match.group(1)] = kv_match.group(2).strip()

        node_id = kv.get("id") or f"{ntype}-{uuid.uuid4().hex[:10]}"
        label_to_id[label] = node_id

        data: dict[str, Any] = {"label": label}
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
        elif ntype == "sub_workflow":
            data["workflow_id"] = kv.get("workflow_id", "")
            data["workflow_name"] = kv.get("workflow_name", "")

        nodes.append({
            "id": node_id,
            "type": ntype,
            "position": {"x": x_offset + i * x_step, "y": y_base},
            "data": data,
        })

    # ── Edges ────────────────────────────────────────────────────────────────
    if edges_start > 0:
        edges_section = md[edges_start:]
        edge_style = {"stroke": "#c4b5a0", "strokeWidth": 1.5, "strokeDasharray": "6 4"}
        marker_end = {"type": "ArrowClosed", "color": "#c4b5a0", "width": 18, "height": 18}

        for line in edges_section.splitlines():
            line = line.strip()
            # --true--> or --false-->
            handle_match = re.match(r"^(.+?)\s+--(\w+)-->\s+(.+)$", line)
            # plain -->
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

            edge_id = f"e-{uuid.uuid4().hex[:8]}"
            edges.append({
                "id": edge_id,
                "source": src_id,
                "target": tgt_id,
                "sourceHandle": handle,
                "type": "smoothstep",
                "style": edge_style,
                "markerEnd": marker_end,
            })

    return name, description, schedule_interval, is_active, {"nodes": nodes, "edges": edges}


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    format: str = Query(default="json", pattern="^(json|markdown)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export a workflow as JSON or Markdown (Claude-importable)."""
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if format == "markdown":
        md = _workflow_to_markdown(workflow)
        return PlainTextResponse(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{workflow.name}.md"'},
        )

    # JSON export
    payload = {
        "sutra_export": "workflow",
        "version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "name": workflow.name,
        "description": workflow.description,
        "schedule_interval": workflow.schedule_interval,
        "is_active": workflow.is_active,
        "definition": workflow.definition or {},
    }
    return PlainTextResponse(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{workflow.name}.json"'},
    )


# ─── Import ──────────────────────────────────────────────────────────────────

class WorkflowImportRequest(BaseModel):
    content: str  # Raw JSON string or Markdown string
    format: str = "json"  # "json" or "markdown"
    name_override: Optional[str] = None


@router.post("/import", response_model=WorkflowResponse, status_code=201)
async def import_workflow(data: WorkflowImportRequest, db: AsyncSession = Depends(get_db)):
    """
    Import a workflow from a JSON export or a Markdown definition.
    Markdown format is Claude-friendly — Claude can generate workflows as Markdown
    which you paste here to create them instantly.
    """
    if data.format == "markdown":
        name, description, schedule_interval, is_active, definition = _markdown_to_definition(data.content)
    else:
        try:
            payload = json.loads(data.content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

        if payload.get("sutra_export") != "workflow":
            raise HTTPException(status_code=422, detail="Not a valid Sutra workflow export")

        name = payload.get("name", "Imported Workflow")
        description = payload.get("description")
        schedule_interval = payload.get("schedule_interval")
        is_active = payload.get("is_active", True)
        definition = payload.get("definition", {})

    if data.name_override:
        name = data.name_override

    # Validate DAG
    if definition.get("nodes"):
        from app.core.workflow_engine import validate_workflow_dag
        errors = validate_workflow_dag(definition)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

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

    from app.core.scheduler import sync_workflows
    await sync_workflows()
    return workflow


# ─── Generate from Natural Language ─────────────────────────────────────────

class WorkflowGenerateRequest(BaseModel):
    description: str
    agent_id: Optional[str] = None


@router.post("/generate", response_model=WorkflowResponse, status_code=201)
async def generate_workflow_from_text(data: WorkflowGenerateRequest, db: AsyncSession = Depends(get_db)):
    """Generate a workflow from a natural language description using an LLM."""
    from app.core.llm_registry import llm_registry
    from app.models.agent import Agent
    from langchain_core.messages import HumanMessage, SystemMessage

    # Find an LLM: prefer specified agent, then Dash, then any active agent
    agent = None
    if data.agent_id:
        agent = await db.get(Agent, data.agent_id)
    if not agent:
        result = await db.execute(select(Agent).where(Agent.name == "Dash", Agent.is_active.is_(True)))
        agent = result.scalars().first()
    if not agent:
        result = await db.execute(select(Agent).where(Agent.is_active.is_(True)).limit(1))
        agent = result.scalars().first()

    provider = agent.llm_provider if agent else "ollama"
    model = agent.llm_model if agent else "llama3"

    try:
        llm = llm_registry.get_chat_model(provider=provider, model=model, temperature=0.3, max_tokens=4096, streaming=False)
    except Exception:
        llm = llm_registry.get_chat_model(provider="ollama", model="llama3", temperature=0.3, max_tokens=4096, streaming=False)

    system_prompt = """You are an expert workflow designer for the Sutra AI Orchestrator platform.
Generate a workflow in the following Markdown format based on the user's description.

Node types:
- [input]: Start node. Fields: value (initial input or empty)
- [agent]: Runs an AI agent. Fields: agent_id (leave empty), prompt (use {input} for previous output), max_retries
- [conditional]: Branches on a condition. Fields: condition (string), agent_id (leave empty)
- [loop]: Iterates with an agent. Fields: agent_id (leave empty), prompt, max_iterations, max_retries
- [approval_gate]: Pauses for human review. Fields: description
- [parallel]: Fan-out to parallel branches. No extra fields.

Edge format:
- Simple: NodeLabel --> NextNodeLabel
- Conditional: NodeLabel --true--> NextNodeLabel  /  NodeLabel --false--> NextNodeLabel

Rules:
1. Always start with an [input] node named "Start"
2. Leave agent_id empty — the user will configure it later
3. Use {input} in prompts to pass output from the previous step
4. Use descriptive node labels
5. Return ONLY the Markdown document, no explanation or code fences

Example format:
# Workflow: <name>

<description>

**Schedule:** Manual
**Active:** true

## Nodes

### 1. [input] Start
- id: input-1
- value:

### 2. [agent] <Step Name>
- id: agent-1
- agent_id:
- prompt: {input}
- max_retries: 0

## Edges

Start --> <Step Name>"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Create a workflow for: {data.description}"),
    ]

    try:
        response = await llm.ainvoke(messages)
        md: str = response.content

        # Strip code fences if the model wrapped the output
        fence_match = re.search(r"```(?:markdown)?\n([\s\S]+?)\n```", md)
        if fence_match:
            md = fence_match.group(1)

        name, description, schedule_interval, is_active, definition = _markdown_to_definition(md)

        if definition.get("nodes"):
            from app.core.workflow_engine import validate_workflow_dag
            errors = validate_workflow_dag(definition)
            if errors:
                logger.warning("Generated workflow has validation warnings: %s", errors)

        workflow = Workflow(
            name=name,
            description=description,
            schedule_interval=schedule_interval,
            is_active=False,  # start as draft — user must activate
            definition=definition,
        )
        db.add(workflow)
        await db.flush()
        await db.refresh(workflow)

        from app.core.scheduler import sync_workflows
        await sync_workflows()
        return workflow

    except Exception as e:
        logger.error("Workflow generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Workflow generation failed: {e}")
