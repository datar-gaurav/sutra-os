"""JSON Schema validator — output-stage guardrail.

Checks that the final assistant message (when the graph expects structured
output) parses to valid JSON and conforms to the provided JSONSchema. On
failure, the action is reject by default; users may switch to "warn" to keep
the response flowing while surfacing the violation in the trace.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.composed_agents.guardrails.base import register
from app.composed_agents.state import AgentState, GuardrailResult


class SchemaValidator:
    id = "schema_validator"
    name = "JSON Schema Validator"
    description = "Validates the final assistant message against a JSON schema."
    kind = "output"

    config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "schema": {
                "type": "object",
                "description": "JSONSchema (draft-2020-12) the response must conform to.",
            },
            "action": {
                "type": "string",
                "enum": ["reject", "warn"],
                "default": "reject",
            },
            "strip_code_fence": {
                "type": "boolean",
                "default": True,
                "description": "Tolerate ```json ... ``` fenced output from the model.",
            },
        },
        "required": ["schema"],
    }

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult:
        t0 = time.monotonic()

        schema = config.get("schema") or {}
        action = config.get("action", "reject")
        strip_fence = config.get("strip_code_fence", True)

        messages = state.get("messages") or []
        target = messages[-1] if messages else None
        text = _to_text(target.content) if target is not None else ""

        if strip_fence:
            text = _strip_code_fence(text)

        # Step 1: parse JSON.
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            return _fail(
                f"Response is not valid JSON: {e}",
                action,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        # Step 2: validate against schema. Import jsonschema lazily so the
        # dependency only bites when this guardrail is actually configured.
        try:
            import jsonschema
        except ImportError:
            return _fail(
                "jsonschema package is not installed.",
                action,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        try:
            jsonschema.validate(instance=payload, schema=schema)
        except jsonschema.ValidationError as e:
            return _fail(
                f"Schema violation: {e.message} (at {list(e.absolute_path)})",
                action,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        return GuardrailResult(
            guardrail_id="schema_validator",
            stage="output",
            passed=True,
            action="allow",
            reason="Response conforms to schema.",
            latency_ms=int((time.monotonic() - t0) * 1000),
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
        # Drop opening fence (possibly with a language tag) and trailing fence.
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def _fail(reason: str, action: str, latency_ms: int) -> GuardrailResult:
    if action == "warn":
        return GuardrailResult(
            guardrail_id="schema_validator",
            stage="output",
            passed=True,
            action="warn",
            reason=reason,
            latency_ms=latency_ms,
        )
    return GuardrailResult(
        guardrail_id="schema_validator",
        stage="output",
        passed=False,
        action="reject",
        reason=reason,
        latency_ms=latency_ms,
    )


register(SchemaValidator())
