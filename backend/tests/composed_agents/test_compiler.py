"""Compiler — happy path + guardrail short-circuit + schema validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.composed_agents.compiler import compile_graph
from app.composed_agents.schemas import GraphSpec, default_graph_spec
from app.composed_agents.state import initial_state


def _patch_llm_returning(text: str):
    """Patch llm_registry.get_chat_model used by the LLM node executor."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=text))
    return patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock_llm,
    )


# ─── GraphSpec validation ──────────────────────────────────────────────────


def test_default_graph_spec_is_valid():
    spec = default_graph_spec()
    GraphSpec.model_validate(spec)  # would raise on failure


def test_graph_must_have_exactly_one_output():
    bad = default_graph_spec()
    # Remove the output node — should fail validation.
    bad["nodes"] = [n for n in bad["nodes"] if n["kind"] != "output"]
    with pytest.raises(ValidationError):
        GraphSpec.model_validate(bad)


def test_entry_must_be_input_kind():
    bad = default_graph_spec()
    bad["entry"] = "llm_main"  # llm node, not input
    with pytest.raises(ValidationError):
        GraphSpec.model_validate(bad)


# ─── Compiler happy path ───────────────────────────────────────────────────


async def test_minimal_graph_runs_end_to_end():
    spec = default_graph_spec()
    with _patch_llm_returning("Hi there."):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="hello")))
    messages = final["messages"]
    # User + assistant message at minimum.
    assert any(isinstance(m, AIMessage) and "Hi there." in m.content for m in messages)
    assert final.get("rejection_message") in (None, "")


# ─── Guardrail short-circuit ───────────────────────────────────────────────


async def test_input_guardrail_reject_short_circuits_to_output():
    spec = default_graph_spec()
    # Attach a PII redactor in REJECT mode on the input node.
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "pii_block",
            "type": "pii_redactor",
            "config": {"action": "reject"},
        }
    ]

    with _patch_llm_returning("This LLM should never be called."):
        graph = compile_graph(spec)
        final = await graph.ainvoke(
            initial_state(HumanMessage(content="my ssn is 123-45-6789"))
        )

    # Run is aborted by guardrail.
    assert final.get("rejection_message")
    assert "pii_block" in final["rejection_message"]
    # Final message is the refusal emitted by the output node.
    last = final["messages"][-1]
    assert isinstance(last, AIMessage)
    assert "blocked by guardrail" in last.content.lower()
    # Guardrail trace records the rejection.
    assert any(g.action == "reject" for g in final["guardrail_results"])


async def test_input_pii_redactor_mutates_then_llm_sees_clean_text():
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {
            "id": "pii_redact",
            "type": "pii_redactor",
            "config": {"action": "redact"},
        }
    ]

    captured_input: dict = {}

    async def _capture(messages):
        captured_input["msgs"] = messages
        return AIMessage(content="OK")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = _capture
    with patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock_llm,
    ):
        graph = compile_graph(spec)
        final = await graph.ainvoke(
            initial_state(HumanMessage(content="Email me at jane@acme.com"))
        )

    # LLM received the redacted text, not the raw email.
    user_msg = next(m for m in captured_input["msgs"] if isinstance(m, HumanMessage))
    assert "[REDACTED:EMAIL]" in user_msg.content
    assert "jane@acme.com" not in user_msg.content
    # Run wasn't rejected.
    assert not final.get("rejection_message")


async def test_output_schema_validator_rejects_bad_json():
    spec = default_graph_spec()
    # Output node validates the response is JSON with an "answer" field.
    spec["nodes"][2]["guardrails"] = [
        {
            "id": "answer_schema",
            "type": "schema_validator",
            "config": {
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                },
                "action": "reject",
            },
        }
    ]

    with _patch_llm_returning("just plain text, no json"):
        graph = compile_graph(spec)
        final = await graph.ainvoke(initial_state(HumanMessage(content="hi")))

    assert final.get("rejection_message")
    last = final["messages"][-1]
    assert "blocked by guardrail" in last.content.lower()
