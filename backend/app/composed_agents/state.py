"""Runtime state types for composed agents.

AgentState is what flows through the LangGraph StateGraph compiled from a
GraphSpec. Every node reads it and returns a partial dict that LangGraph
merges in. Keys are deliberately narrow — graph authors put their own
intermediate values under `scratchpad`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


GuardrailAction = Literal["allow", "mutate", "reject", "warn"]


@dataclass
class GuardrailResult:
    """Verdict returned by a guardrail's check() method."""

    guardrail_id: str            # e.g. "pii_redactor" or a user-saved name
    stage: Literal["input", "output"]
    passed: bool
    action: GuardrailAction
    reason: str = ""
    score: float | None = None
    latency_ms: int = 0
    # If action == "mutate", the guardrail returns a replacement message string.
    # The compiler applies this to the head message in AgentState.
    mutated_text: str | None = None


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    result: Any
    latency_ms: int = 0


@dataclass
class ProbeRecord:
    """Eval-only signal — populated when running under the eval harness."""

    node_id: str
    name: str
    value: Any
    timestamp_ms: int = 0


@dataclass
class CostAccumulator:
    tokens_in: int = 0
    tokens_out: int = 0
    dollars: float = 0.0


class AgentState(TypedDict, total=False):
    """The state object every node in a composed agent's graph reads and writes."""

    # Conversation — appended to (LangGraph's add_messages reducer dedupes).
    messages: Annotated[list[BaseMessage], add_messages]

    # Free-form intermediate values keyed by graph author.
    scratchpad: dict[str, Any]

    # Audit log of tool calls made during this run.
    tool_calls: list[ToolCallRecord]

    # Every guardrail's verdict from this run (input and output combined).
    guardrail_results: list[GuardrailResult]

    # Eval-only signals (empty in normal runs).
    eval_probes: list[ProbeRecord]

    # Running totals so token_guard and budgets can stop a run mid-flight.
    cost: CostAccumulator

    # Router decisions set this so conditional edges can read it.
    branch: str | None

    # If set, the run was aborted by a guardrail and this is the message to return.
    rejection_message: str | None


def initial_state(user_message: BaseMessage) -> AgentState:
    """Build a fresh AgentState seeded with the user's input message."""
    return {
        "messages": [user_message],
        "scratchpad": {},
        "tool_calls": [],
        "guardrail_results": [],
        "eval_probes": [],
        "cost": CostAccumulator(),
        "branch": None,
        "rejection_message": None,
    }
