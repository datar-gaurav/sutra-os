"""Built-in guardrail library.

Importing this package registers every shipped guardrail with the base
registry. App code should import from here so the registration side effects
run before lookup.
"""

from app.composed_agents.guardrails.base import Guardrail, get, list_all, register  # noqa: F401
# Side-effect imports — each module calls register() at the bottom.
from app.composed_agents.guardrails import (  # noqa: F401
    group,
    injection_detector,
    pii_redactor,
    prompt_judge,
    schema_validator,
)

__all__ = ["Guardrail", "get", "list_all", "register"]
