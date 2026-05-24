"""Invocation entrypoint for composed agents.

Used by:
  - The orchestrator (for production chat runs once dispatch lands).
  - The API route POST /api/composed-agents/{id}/run (the test-run endpoint
    used by the builder UI).

Compiled graphs are cached by (composed_agent_id, version_used). Eviction is
manual on publish or graph_spec mutation — see invalidate().
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from app.composed_agents.compiler import compile_graph
from app.composed_agents.state import initial_state

logger = logging.getLogger(__name__)


_CACHE: dict[tuple[str, int], Any] = {}


def _cache_key(agent_id: str, version: int) -> tuple[str, int]:
    return (agent_id, version)


def get_or_compile(agent_id: str, version: int, graph_spec: dict[str, Any]):
    """Return a compiled graph, building it on first use."""
    key = _cache_key(agent_id, version)
    if key not in _CACHE:
        _CACHE[key] = compile_graph(graph_spec)
    return _CACHE[key]


def invalidate(agent_id: str, version: int | None = None) -> None:
    """Drop cached compiles. Pass version=None to drop every cached version."""
    if version is None:
        for k in [k for k in _CACHE if k[0] == agent_id]:
            _CACHE.pop(k, None)
    else:
        _CACHE.pop(_cache_key(agent_id, version), None)


async def run_once(
    agent_id: str,
    version: int,
    graph_spec: dict[str, Any],
    user_message: str,
) -> tuple[str, dict[str, Any]]:
    """Invoke a composed agent on a single user message.

    Returns (run_id, final_state). The run_id correlates rows in
    guardrail_events from this invocation — callers that want audit
    persistence should pass it to the event-write helper.
    """
    run_id = str(uuid.uuid4())
    graph = get_or_compile(agent_id, version, graph_spec)
    init = initial_state(HumanMessage(content=user_message))
    # Stash the run_id in scratchpad so nodes and downstream consumers can read it.
    init["scratchpad"] = {**(init.get("scratchpad") or {}), "run_id": run_id}
    final = await graph.ainvoke(init)
    return run_id, final
