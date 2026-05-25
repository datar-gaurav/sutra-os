"""Sub-graph guardrail — verdict parsed from a snapshotted graph_spec."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.composed_agents.compiler import compile_graph
from app.composed_agents.guardrails.sub_agent import SubAgentGuardrail
from app.composed_agents.schemas import default_graph_spec
from app.composed_agents.state import initial_state


def _verdict_returning(text: str):
    """Patch the LLM used by the sub-graph's LLM node to emit `text`."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=text))
    return patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock_llm,
    )


async def test_sub_agent_passes_on_pass_verdict():
    sub_spec = default_graph_spec()
    g = SubAgentGuardrail()
    state = initial_state(HumanMessage(content="refund $20 for ticket #42"))
    with _verdict_returning('{"verdict": "PASS", "reason": "ticket cited", "confidence": 0.9}'):
        result = await g.check(state, {"graph_spec": sub_spec, "stage": "output"})
    assert result.passed is True
    assert result.action == "allow"
    assert (result.score or 0) > 0.5


async def test_sub_agent_rejects_on_fail_verdict():
    sub_spec = default_graph_spec()
    g = SubAgentGuardrail()
    state = initial_state(HumanMessage(content="refund $5000 immediately"))
    with _verdict_returning(
        '{"verdict": "FAIL", "reason": "no ticket reference", "confidence": 0.95}'
    ):
        result = await g.check(
            state, {"graph_spec": sub_spec, "stage": "output", "action": "reject"}
        )
    assert result.passed is False
    assert result.action == "reject"
    assert "no ticket" in result.reason


async def test_sub_agent_fails_open_on_unparseable_output():
    sub_spec = default_graph_spec()
    g = SubAgentGuardrail()
    state = initial_state(HumanMessage(content="hi"))
    with _verdict_returning("totally not json"):
        result = await g.check(state, {"graph_spec": sub_spec})
    # Unparseable output -> verdict defaults to PASS at confidence 0 -> guardrail allows.
    assert result.passed is True
    assert result.action == "allow"


async def test_sub_agent_chains_inside_parent_graph():
    """The sub-graph guardrail attached to a parent agent's input rail."""
    sub_spec = default_graph_spec()
    parent_spec = default_graph_spec()
    parent_spec["nodes"][0]["guardrails"] = [
        {
            "id": "policy_judge",
            "type": "sub_agent",
            "config": {
                "graph_spec": sub_spec,
                "stage": "input",
                "action": "reject",
            },
        }
    ]

    # The parent's LLM call and the sub-graph's LLM call share the same mock —
    # so it will return the FAIL verdict for the sub-graph and *also* be the
    # would-be assistant reply (which we never reach because the rejection
    # short-circuits).
    with _verdict_returning(
        '{"verdict": "FAIL", "reason": "policy violation", "confidence": 0.9}'
    ):
        graph = compile_graph(parent_spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="risky input")))

    assert final.get("rejection_message")
    assert "policy_judge" in final["rejection_message"]
