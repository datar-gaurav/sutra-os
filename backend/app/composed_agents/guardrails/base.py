"""Guardrail protocol + global registry.

A guardrail is a small object with:
  - id          — stable string used in DB configs and trace logs
  - kind        — "input" or "output" (some, like prompt_judge, are dual-stage)
  - config_schema — JSON schema for the per-instance config (the UI renders this)
  - check(state, config) -> GuardrailResult — the actual logic

The registry maps a type string ("pii_redactor", "schema_validator", ...) to
a Guardrail instance. The compiler resolves attachments by looking up the type
here, then calls check() with the attachment's config dict.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, Protocol, runtime_checkable

from app.composed_agents.state import AgentState, GuardrailResult


@runtime_checkable
class Guardrail(Protocol):
    """Interface every guardrail implements. Stateless — config arrives per call."""

    id: str
    kind: Literal["input", "output", "both"]
    name: str
    description: str
    config_schema: dict[str, Any]

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult: ...


_REGISTRY: dict[str, Guardrail] = {}


def register(guardrail: Guardrail) -> Guardrail:
    """Decorator-style registration. Idempotent — re-registering overwrites."""
    _REGISTRY[guardrail.id] = guardrail
    return guardrail


def get(guardrail_id: str) -> Guardrail:
    if guardrail_id not in _REGISTRY:
        raise KeyError(f"Unknown guardrail '{guardrail_id}'. Registered: {list(_REGISTRY)}")
    return _REGISTRY[guardrail_id]


def list_all() -> list[dict[str, Any]]:
    """Return JSON-serializable descriptors for every registered guardrail.

    Used by GET /api/composed-agents/guardrails to populate the picker UI.
    """
    out = []
    for g in _REGISTRY.values():
        out.append(
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "kind": g.kind,
                "config_schema": g.config_schema,
            }
        )
    return out
