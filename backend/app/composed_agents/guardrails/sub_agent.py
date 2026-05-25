"""Sub-graph guardrail — a guardrail that IS itself a composed agent.

The most powerful escape hatch in the design ladder: when a single LLM-judge
isn't enough (e.g. "retrieve the user's KYC tier → check claim against policy
doc → ask a judge LLM"), the guardrail is itself a composed agent and its
final assistant message is parsed as a {verdict, reason, confidence} verdict.

Design notes:
  - The sub-agent's graph_spec is SNAPSHOTTED into the attachment config at
    attach time (same provenance pattern as SavedGuardrail), not looked up at
    runtime. This avoids needing a DB session inside check() and keeps the
    guardrail's behavior frozen against drift in the upstream agent.
  - The sub-agent receives the parent's current message as its input.
  - The sub-agent's output node must produce JSON of shape
    {"verdict": "PASS"|"FAIL", "reason": str, "confidence": 0..1}. We tolerate
    code fences and surrounding prose, mirroring prompt_judge.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from app.composed_agents.guardrails.base import register
from app.composed_agents.state import AgentState, GuardrailResult, initial_state

logger = logging.getLogger(__name__)


class SubAgentGuardrail:
    id = "sub_agent"
    name = "Sub-Graph Guardrail"
    description = (
        "Run another composed agent as the guardrail. Its final message must be "
        '{"verdict": "PASS"|"FAIL", "reason": ..., "confidence": ...}.'
    )
    kind = "both"

    config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "graph_spec": {
                "type": "object",
                "description": "Snapshotted graph_spec from the source composed agent.",
            },
            "source_agent_id": {
                "type": "string",
                "description": "The id of the upstream agent this snapshot came from.",
            },
            "source_version": {
                "type": "integer",
                "description": "Source agent version at snapshot time (used by UI to flag drift).",
            },
            "stage": {"type": "string", "enum": ["input", "output"], "default": "output"},
            "action": {
                "type": "string",
                "enum": ["reject", "warn"],
                "default": "reject",
            },
            "min_confidence": {"type": "number", "default": 0.0},
        },
        "required": ["graph_spec"],
    }

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult:
        t0 = time.monotonic()

        graph_spec = config.get("graph_spec")
        if not graph_spec:
            return _pass(self.id, config.get("stage", "output"), "No graph_spec configured.", t0)

        stage = config.get("stage", "output")
        action = config.get("action", "reject")
        min_conf = float(config.get("min_confidence") or 0.0)

        # Build the sub-agent's input from the parent's current head message.
        messages = state.get("messages") or []
        if not messages:
            return _pass(self.id, stage, "No input to evaluate.", t0)
        head = messages[-1]
        text = _to_text(head.content)

        # Compile-and-run. Import compiler lazily to avoid a circular import
        # (guardrails/__init__ is imported by compiler).
        from app.composed_agents.compiler import compile_graph

        try:
            graph = compile_graph(graph_spec)
            sub_state = initial_state(HumanMessage(content=text))
            # Tag the sub-state so nested guardrail_events (if persisted) point
            # back at the parent run.
            sub_state["scratchpad"] = {
                **(sub_state.get("scratchpad") or {}),
                "parent_run_id": (state.get("scratchpad") or {}).get("run_id"),
                "sub_run_id": str(uuid.uuid4()),
            }
            final = await graph.ainvoke(sub_state)
        except Exception as e:
            logger.exception("sub-graph guardrail crashed")
            return _pass(self.id, stage, f"Sub-graph crashed; failing open: {e}", t0)

        # Parse the final assistant message as a verdict.
        sub_msgs = final.get("messages") or []
        last = sub_msgs[-1] if sub_msgs else None
        raw = _to_text(last.content if last else "")
        verdict_obj = _extract_json(raw)

        verdict = (verdict_obj.get("verdict") or "").upper()
        reason = verdict_obj.get("reason") or ""
        confidence = float(verdict_obj.get("confidence") or 0.5)

        latency_ms = int((time.monotonic() - t0) * 1000)

        if verdict == "FAIL" and confidence >= min_conf:
            return GuardrailResult(
                guardrail_id=self.id,
                stage=stage,  # type: ignore[arg-type]
                passed=(action == "warn"),
                action=("warn" if action == "warn" else "reject"),
                reason=reason or "Sub-graph returned FAIL.",
                score=confidence,
                latency_ms=latency_ms,
            )

        return GuardrailResult(
            guardrail_id=self.id,
            stage=stage,  # type: ignore[arg-type]
            passed=True,
            action="allow",
            reason=reason or "Sub-graph returned PASS.",
            score=confidence,
            latency_ms=latency_ms,
        )


def _to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content) if content is not None else ""


def _extract_json(raw: str) -> dict[str, Any]:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {"verdict": "PASS", "reason": "Sub-graph output unparseable.", "confidence": 0.0}


def _pass(gid: str, stage: str, reason: str, t0: float) -> GuardrailResult:
    return GuardrailResult(
        guardrail_id=gid,
        stage=stage,  # type: ignore[arg-type]
        passed=True,
        action="allow",
        reason=reason,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


register(SubAgentGuardrail())
