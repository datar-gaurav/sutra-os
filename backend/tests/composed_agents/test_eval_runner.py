"""Eval runner — judges cases against each expectation type."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from app.composed_agents.evals.runner import run_case
from app.composed_agents.schemas import default_graph_spec


def _patch_agent_llm(text: str):
    """Patches the LLM used by composed_agents.compiler (the agent itself)."""
    mock = AsyncMock(); mock.ainvoke = AsyncMock(return_value=AIMessage(content=text))
    return patch(
        "app.composed_agents.compiler.llm_registry.get_chat_model",
        return_value=mock,
    )


def _patch_judge(verdict: str, reason: str = "", conf: float = 0.9):
    """Patches the LLM used by the eval runner's judge."""
    raw = f'{{"verdict": "{verdict}", "reason": "{reason}", "confidence": {conf}}}'
    mock = AsyncMock(); mock.ainvoke = AsyncMock(return_value=AIMessage(content=raw))
    return patch(
        "app.composed_agents.evals.runner.llm_registry.get_chat_model",
        return_value=mock,
    )


async def test_rubric_case_passes_when_judge_says_pass():
    spec = default_graph_spec()
    with _patch_agent_llm("Hello! How can I help?"), _patch_judge("PASS", "greeted appropriately"):
        outcome = await run_case(
            composed_agent_id=f"a-{__import__('uuid').uuid4()}",
            composed_agent_version=1,
            graph_spec=spec,
            case_id="c1",
            case_name="greeting",
            case_input="hi",
            judge_rubric="Agent should greet politely.",
            expected_guardrail_blocked=None,
            expected_schema=None,
        )
    assert outcome.passed is True
    assert outcome.verdict == "PASS"


async def test_rubric_case_fails_when_judge_says_fail():
    spec = default_graph_spec()
    with _patch_agent_llm("go away"), _patch_judge("FAIL", "rude", conf=0.95):
        outcome = await run_case(
            composed_agent_id=f"a-{__import__('uuid').uuid4()}",
            composed_agent_version=1,
            graph_spec=spec,
            case_id="c1",
            case_name="rudeness",
            case_input="hi",
            judge_rubric="Agent should greet politely.",
            expected_guardrail_blocked=None,
            expected_schema=None,
        )
    assert outcome.passed is False
    assert outcome.verdict == "FAIL"
    assert "rude" in outcome.reason


async def test_expected_guardrail_blocked_passes_when_run_was_blocked():
    spec = default_graph_spec()
    spec["nodes"][0]["guardrails"] = [
        {"id": "block", "type": "pii_redactor", "config": {"action": "reject"}}
    ]
    # Agent's LLM should never be called — guardrail rejects first.
    with _patch_agent_llm("(should not be called)"):
        outcome = await run_case(
            composed_agent_id=f"a-{__import__('uuid').uuid4()}",
            composed_agent_version=1,
            graph_spec=spec,
            case_id="c1",
            case_name="must-block ssn",
            case_input="my ssn is 123-45-6789",
            judge_rubric=None,
            expected_guardrail_blocked=True,
            expected_schema=None,
        )
    assert outcome.passed is True


async def test_expected_guardrail_blocked_fails_when_run_completed():
    spec = default_graph_spec()
    with _patch_agent_llm("ok"):
        outcome = await run_case(
            composed_agent_id=f"a-{__import__('uuid').uuid4()}",
            composed_agent_version=1,
            graph_spec=spec,
            case_id="c1",
            case_name="should-have-blocked",
            case_input="hello",
            judge_rubric=None,
            expected_guardrail_blocked=True,
            expected_schema=None,
        )
    assert outcome.passed is False
    assert "expected the run to be blocked" in outcome.reason


async def test_expected_schema_fails_on_bad_json():
    spec = default_graph_spec()
    with _patch_agent_llm("not json at all"):
        outcome = await run_case(
            composed_agent_id=f"a-{__import__('uuid').uuid4()}",
            composed_agent_version=1,
            graph_spec=spec,
            case_id="c1",
            case_name="json-required",
            case_input="give me json",
            judge_rubric=None,
            expected_guardrail_blocked=None,
            expected_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        )
    assert outcome.passed is False
    assert "schema check failed" in outcome.reason
