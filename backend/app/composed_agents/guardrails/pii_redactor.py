"""PII redactor — regex-based, no LLM call.

Cheap, deterministic guardrail useful as both an input-stage redactor and a
quick output-stage leak check. Detects email, phone, SSN, and credit-card-shaped
numbers by default; users toggle which entities to look for via config.

Action policy:
  - "redact" → return a mutated text with each match replaced by [REDACTED:<TYPE>].
    The guardrail PASSES (action="mutate") and lets the run continue.
  - "reject" → if any match is found, abort the run.
  - "warn"   → log the finding but do not modify the message; PASSES.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.composed_agents.guardrails.base import register
from app.composed_agents.state import AgentState, GuardrailResult


_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
}


class PIIRedactor:
    id = "pii_redactor"
    name = "PII Redactor"
    description = "Detects emails, phone numbers, SSNs and credit-card-shaped numbers via regex. Can redact, reject, or warn."
    kind = "both"

    config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {"type": "string", "enum": list(_PATTERNS.keys())},
                "default": ["email", "phone", "ssn", "credit_card"],
                "description": "Which entity types to scan for.",
            },
            "action": {
                "type": "string",
                "enum": ["redact", "reject", "warn"],
                "default": "redact",
            },
        },
    }

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult:
        t0 = time.monotonic()

        entities = config.get("entities") or list(_PATTERNS.keys())
        action = config.get("action", "redact")

        messages = state.get("messages") or []
        # We scan the most recent user/assistant message — input stage gets the
        # user message; output stage gets the assistant message that was just
        # generated. Either way, the head of the list at this point.
        target = messages[-1] if messages else None
        text = _to_text(target.content) if target is not None else ""

        found: list[tuple[str, str]] = []  # (entity_type, matched_string)
        mutated = text
        for ent in entities:
            pat = _PATTERNS.get(ent)
            if not pat:
                continue
            for m in pat.finditer(text):
                found.append((ent, m.group(0)))
            if action == "redact":
                mutated = pat.sub(f"[REDACTED:{ent.upper()}]", mutated)

        latency_ms = int((time.monotonic() - t0) * 1000)

        if not found:
            return GuardrailResult(
                guardrail_id=self.id,
                stage="input",  # caller overrides via attachment context
                passed=True,
                action="allow",
                reason="No PII detected.",
                latency_ms=latency_ms,
            )

        reason = f"Found {len(found)} PII match(es): " + ", ".join(
            f"{kind}" for kind, _ in found[:5]
        )

        if action == "reject":
            return GuardrailResult(
                guardrail_id=self.id,
                stage="input",
                passed=False,
                action="reject",
                reason=reason,
                latency_ms=latency_ms,
            )
        if action == "warn":
            return GuardrailResult(
                guardrail_id=self.id,
                stage="input",
                passed=True,
                action="warn",
                reason=reason,
                latency_ms=latency_ms,
            )
        # default: redact
        return GuardrailResult(
            guardrail_id=self.id,
            stage="input",
            passed=True,
            action="mutate",
            reason=reason,
            mutated_text=mutated,
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


register(PIIRedactor())
