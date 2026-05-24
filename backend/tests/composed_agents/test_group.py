"""GuardrailGroup composition modes — ALL/ANY/SEQUENCE."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.composed_agents.compiler import compile_graph
from app.composed_agents.schemas import default_graph_spec
from app.composed_agents.state import initial_state


def _patch_llm_returning(text: str):
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=text))
    return patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock_llm,
    )


async def test_group_all_rejects_when_any_child_rejects():
    """ALL: PII redactor (passes) followed by another PII redactor in reject mode."""
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "safety_group",
            "type": "group",
            "config": {
                "mode": "ALL",
                "children": [
                    {"id": "pii1", "type": "pii_redactor", "config": {"action": "warn"}},
                    {"id": "pii2", "type": "pii_redactor", "config": {"action": "reject"}},
                ],
            },
        }
    ]

    with _patch_llm_returning("nope"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(
            initial_state(HumanMessage(content="my ssn is 123-45-6789"))
        )

    # First child warned, second rejected, group rolled up as fatal.
    actions = [g.action for g in final["guardrail_results"]]
    assert "warn" in actions
    assert "reject" in actions
    assert final.get("rejection_message")
    assert "safety_group" in final["rejection_message"]


async def test_group_all_passes_when_all_children_pass():
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "ok_group",
            "type": "group",
            "config": {
                "mode": "ALL",
                "children": [
                    {"id": "p1", "type": "pii_redactor", "config": {"action": "warn"}},
                    {"id": "p2", "type": "pii_redactor", "config": {"action": "warn"}},
                ],
            },
        }
    ]
    with _patch_llm_returning("hi"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="hello there")))
    assert not final.get("rejection_message")


async def test_group_all_chains_mutations():
    """First child redacts emails; LLM should see redacted text."""
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "redact_group",
            "type": "group",
            "config": {
                "mode": "ALL",
                "children": [
                    {"id": "redact1", "type": "pii_redactor", "config": {"action": "redact"}},
                ],
            },
        }
    ]
    captured: dict = {}

    async def _capture(messages):
        captured["msgs"] = messages
        return AIMessage(content="ok")

    mock_llm = AsyncMock(); mock_llm.ainvoke = _capture
    with patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock_llm,
    ):
        graph = compile_graph(spec)
        await graph.ainvoke(initial_state(HumanMessage(content="email jane@acme.com")))

    user_msg = next(m for m in captured["msgs"] if isinstance(m, HumanMessage))
    assert "[REDACTED:EMAIL]" in user_msg.content
    assert "jane@acme.com" not in user_msg.content


async def test_group_any_passes_if_any_child_passes():
    """ANY: one rejecting child, one allowing child → group passes."""
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "any_group",
            "type": "group",
            "config": {
                "mode": "ANY",
                "children": [
                    # ssn pattern → rejects
                    {"id": "rej", "type": "pii_redactor", "config": {"action": "reject"}},
                    # clean — passes (input contains an ssn but the second child only warns)
                    {"id": "warn", "type": "pii_redactor", "config": {"action": "warn"}},
                ],
            },
        }
    ]
    with _patch_llm_returning("ok"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="ssn 123-45-6789")))
    # ANY: the warn-mode child passes, so the group passes overall.
    assert not final.get("rejection_message")
    # Group summary verdict is in the trace.
    summaries = [g for g in final["guardrail_results"] if g.guardrail_id == "any_group"]
    assert summaries and summaries[-1].action == "allow"


async def test_group_any_rejects_when_all_children_reject():
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "all_reject_group",
            "type": "group",
            "config": {
                "mode": "ANY",
                "children": [
                    {"id": "r1", "type": "pii_redactor", "config": {"action": "reject"}},
                    {"id": "r2", "type": "pii_redactor", "config": {"action": "reject"}},
                ],
            },
        }
    ]
    with _patch_llm_returning("ok"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="ssn 123-45-6789")))
    assert final.get("rejection_message")
    assert "all_reject_group" in final["rejection_message"]


async def test_group_sequence_is_alias_for_all():
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "seq",
            "type": "group",
            "config": {
                "mode": "SEQUENCE",
                "children": [
                    {"id": "pii", "type": "pii_redactor", "config": {"action": "reject"}},
                ],
            },
        }
    ]
    with _patch_llm_returning("ok"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="ssn 123-45-6789")))
    assert final.get("rejection_message")
