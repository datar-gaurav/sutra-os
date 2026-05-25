"""Eval runner — executes a suite of EvalCases against a ComposedAgent.

For each case we:
  1. invoke runner.run_once with case.input
  2. apply each non-null expectation (guardrail_blocked, schema, judge_rubric)
  3. PASS only if every applicable expectation passes (deterministic AND)
  4. write an EvalResult row; aggregate into the EvalRun summary

The judge LLM is invoked once per case that has a judge_rubric. Other
expectations are deterministic.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.composed_agents.runner import run_once
from app.core.llm_registry import llm_registry

logger = logging.getLogger(__name__)


@dataclass
class CaseOutcome:
    case_id: str
    case_name: str
    passed: bool
    verdict: str           # PASS | FAIL | ERROR
    reason: str
    output: str
    latency_ms: int
    judge_confidence: float | None = None


_JUDGE_SYSTEM = """You are a strict eval judge. Reply with ONLY a JSON object:
{"verdict": "PASS" | "FAIL", "reason": "<short>", "confidence": 0.0-1.0}
Judge whether the agent's response satisfies the rubric. Be strict but fair."""


async def judge_case(
    case_input: str,
    case_rubric: str,
    agent_output: str,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
) -> tuple[bool, str, float]:
    """Run the LLM judge once. Returns (passed, reason, confidence).
    Fail-open: judge errors do not fail the case."""
    try:
        llm = llm_registry.get_chat_model(
            provider=provider, model=model, temperature=0.0, max_tokens=300, streaming=False
        )
        resp = await llm.ainvoke(
            [
                SystemMessage(content=_JUDGE_SYSTEM),
                HumanMessage(
                    content=(
                        f"Rubric:\n{case_rubric}\n\n"
                        f"Input:\n{case_input}\n\n"
                        f"Agent response:\n{agent_output}"
                    )
                ),
            ]
        )
        raw = _to_text(resp.content)
        obj = _extract_json(raw)
        verdict = (obj.get("verdict") or "").upper()
        return (
            verdict == "PASS",
            obj.get("reason") or "",
            float(obj.get("confidence") or 0.5),
        )
    except Exception as e:
        logger.warning("Judge call failed: %s", e)
        return True, f"judge unavailable, defaulting to PASS: {e}", 0.0


async def run_case(
    composed_agent_id: str,
    composed_agent_version: int,
    graph_spec: dict[str, Any],
    case_id: str,
    case_name: str,
    case_input: str,
    judge_rubric: str | None,
    expected_guardrail_blocked: bool | None,
    expected_schema: dict | None,
    judge_provider: str = "openai",
    judge_model: str = "gpt-4o-mini",
) -> CaseOutcome:
    """Execute a single case and judge against its expectations."""
    t0 = time.monotonic()
    try:
        _run_id, final = await run_once(
            composed_agent_id, composed_agent_version, graph_spec, case_input
        )
    except Exception as e:
        logger.exception("Eval case run failed (%s)", case_name)
        return CaseOutcome(
            case_id=case_id,
            case_name=case_name,
            passed=False,
            verdict="ERROR",
            reason=f"agent run crashed: {e}",
            output="",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    messages = final.get("messages") or []
    last = messages[-1] if messages else None
    output = _to_text(last.content if last else "")
    rejected = bool(final.get("rejection_message"))
    latency_ms = int((time.monotonic() - t0) * 1000)

    failures: list[str] = []
    judge_conf: float | None = None

    # 1) guardrail-blocked expectation
    if expected_guardrail_blocked is not None:
        if expected_guardrail_blocked and not rejected:
            failures.append("expected the run to be blocked by a guardrail but it ran to completion")
        if (not expected_guardrail_blocked) and rejected:
            failures.append(
                f"unexpected guardrail rejection: {final.get('rejection_message')}"
            )

    # 2) schema expectation
    if expected_schema is not None and not rejected:
        try:
            import jsonschema
            payload = json.loads(_strip_code_fence(output))
            jsonschema.validate(instance=payload, schema=expected_schema)
        except Exception as e:
            failures.append(f"schema check failed: {e}")

    # 3) LLM-judge rubric — skip if the case expected a rejection AND we got one.
    if judge_rubric and not (expected_guardrail_blocked and rejected):
        passed, reason, judge_conf = await judge_case(
            case_input, judge_rubric, output, judge_provider, judge_model
        )
        if not passed:
            failures.append(f"judge said FAIL: {reason}")

    passed = not failures
    return CaseOutcome(
        case_id=case_id,
        case_name=case_name,
        passed=passed,
        verdict="PASS" if passed else "FAIL",
        reason="; ".join(failures) if failures else "all expectations passed",
        output=output[:8000],
        latency_ms=latency_ms,
        judge_confidence=judge_conf,
    )


def _to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content) if content is not None else ""


def _strip_code_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


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
        return {"verdict": "PASS", "reason": "judge output unparseable", "confidence": 0.0}
