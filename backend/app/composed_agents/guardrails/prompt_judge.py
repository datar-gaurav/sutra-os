"""Prompt-based LLM judge — generic guardrail powered by an LLM-as-judge.

The user supplies a rubric in natural language; this guardrail wraps it in a
structured-output schema ({verdict, reason, confidence}) and runs it via the
LLM registry. Used for things like "the response must not promise a refund
without referencing a ticket id".

This is the building block for the entire "Rung 2" of the guardrail ladder
(prompt-authored custom guardrails) without needing code.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.composed_agents.guardrails.base import register
from app.composed_agents.state import AgentState, GuardrailResult
from app.core.llm_registry import llm_registry

logger = logging.getLogger(__name__)


_JUDGE_SYSTEM = """You are a strict guardrail judge.

You will be given a rubric and a piece of text. Decide whether the text PASSES
or FAILS the rubric. Reply with ONLY a JSON object, no prose:

{"verdict": "PASS" | "FAIL", "reason": "<short explanation>", "confidence": 0.0-1.0}

Be strict but fair. If the text is ambiguous, default to PASS with low confidence.
"""


class PromptJudge:
    id = "prompt_judge"
    name = "Prompt-Based LLM Judge"
    description = "LLM-as-judge using a user-provided rubric. Use this for nuanced checks that aren't worth coding (refund policy, off-topic, tone)."
    kind = "both"

    config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "rubric": {
                "type": "string",
                "description": "Natural-language rubric. Describe what the text MUST do (or must not do) to pass.",
            },
            "judge_provider": {"type": "string", "default": "openai"},
            "judge_model": {"type": "string", "default": "gpt-4o-mini"},
            "stage": {
                "type": "string",
                "enum": ["input", "output"],
                "default": "output",
            },
            "action": {
                "type": "string",
                "enum": ["reject", "warn"],
                "default": "reject",
            },
            "min_confidence": {
                "type": "number",
                "default": 0.0,
                "description": "Ignore FAIL verdicts below this confidence (still logs as warn).",
            },
        },
        "required": ["rubric"],
    }

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult:
        t0 = time.monotonic()

        rubric = (config.get("rubric") or "").strip()
        if not rubric:
            return _allow(self.id, config.get("stage", "output"), "No rubric configured.", t0)

        stage = config.get("stage", "output")
        action = config.get("action", "reject")
        min_conf = float(config.get("min_confidence") or 0.0)
        provider = config.get("judge_provider") or "openai"
        model = config.get("judge_model") or "gpt-4o-mini"

        messages = state.get("messages") or []
        target = messages[-1] if messages else None
        text = _to_text(target.content) if target is not None else ""

        prompt = (
            f"Rubric:\n{rubric}\n\n"
            f"Text to judge:\n---\n{text}\n---\n"
            "Reply with ONLY the JSON object."
        )

        try:
            judge = llm_registry.get_chat_model(
                provider=provider,
                model=model,
                temperature=0.0,
                max_tokens=300,
                streaming=False,
            )
            resp = await judge.ainvoke(
                [SystemMessage(content=_JUDGE_SYSTEM), HumanMessage(content=prompt)]
            )
            raw = _to_text(resp.content)
            verdict_obj = _extract_json(raw)
        except Exception as e:
            logger.warning("prompt_judge failed: %s", e)
            return _allow(self.id, stage, f"Judge unavailable ({e}); defaulting to pass.", t0)

        verdict = (verdict_obj.get("verdict") or "").upper()
        reason = verdict_obj.get("reason") or ""
        confidence = float(verdict_obj.get("confidence") or 0.5)
        latency_ms = int((time.monotonic() - t0) * 1000)

        if verdict == "FAIL" and confidence >= min_conf:
            return GuardrailResult(
                guardrail_id=self.id,
                stage=stage,
                passed=(action == "warn"),
                action=("warn" if action == "warn" else "reject"),
                reason=reason or "Failed rubric.",
                score=confidence,
                latency_ms=latency_ms,
            )

        return GuardrailResult(
            guardrail_id=self.id,
            stage=stage,
            passed=True,
            action="allow",
            reason=reason or "Passed rubric.",
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
    """Be permissive — some models wrap JSON in prose or code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    # Find the first '{' .. matching '}' if there's surrounding prose.
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {"verdict": "PASS", "reason": "Judge output unparseable.", "confidence": 0.0}


def _allow(gid: str, stage: str, reason: str, t0: float) -> GuardrailResult:
    return GuardrailResult(
        guardrail_id=gid,
        stage=stage,
        passed=True,
        action="allow",
        reason=reason,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


register(PromptJudge())
