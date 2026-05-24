"""GuardrailGroup — a composition primitive for chaining guardrails.

A group is NOT a regular guardrail. It's a control-flow construct expanded by
the compiler's chain runner. The runner detects attachments with
``type == "group"`` and recursively applies the children with the configured
mode semantics:

  - ALL (default) — every child must pass; first reject is fatal; mutations
    chain in order.
  - ANY            — group passes if any one child passes. Mutations are NOT
    applied in this mode (semantically ambiguous which child's mutation wins).
  - SEQUENCE       — alias for ALL with the intent of "ordered, short-circuit".

A descriptor is registered with a stub ``check`` that raises if called
directly — this surfaces a bug if the runner ever forgets to special-case the
type. The descriptor exists so the UI picker can list "Group" as a first-class
option alongside the built-in guardrails.
"""

from __future__ import annotations

from typing import Any

from app.composed_agents.guardrails.base import register
from app.composed_agents.state import AgentState, GuardrailResult


GROUP_TYPE = "group"
GROUP_MODES = ("ALL", "ANY", "SEQUENCE")


class GuardrailGroupDescriptor:
    """Picker metadata for the UI. The runner expands groups inline; this
    object's ``check`` raises to make accidental dispatch loud."""

    id = GROUP_TYPE
    name = "Guardrail Group"
    description = (
        "Bundle multiple guardrails with ALL/ANY/SEQUENCE logic. Use this when "
        "a single rule isn't enough (e.g. PII redact AND topic check AND injection scan)."
    )
    kind = "both"

    config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": list(GROUP_MODES), "default": "ALL"},
            "children": {
                "type": "array",
                "description": "List of GuardrailAttachment objects.",
                "items": {"type": "object"},
                "default": [],
            },
        },
    }

    async def check(self, state: AgentState, config: dict[str, Any]) -> GuardrailResult:
        # The compiler's chain runner should expand groups before reaching here.
        # If we ever hit this, the runner has a bug.
        raise RuntimeError(
            "GuardrailGroup.check() called directly — the compiler should "
            "expand groups inline. Did you forget to special-case type=='group'?"
        )


register(GuardrailGroupDescriptor())
