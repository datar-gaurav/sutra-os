"""Pydantic schemas for the graph_spec JSON stored on ComposedAgent rows.

A graph_spec is validated on save and again at compile time. Node types are a
discriminated union on `kind`, so each node kind declares its own config shape.
Adding a new node kind = adding a new NodeSpec subclass and a Literal entry.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


# ─── Guardrail attachment shape ──────────────────────────────────────────────


class GuardrailAttachment(BaseModel):
    """A configured guardrail referenced by an input/output rail or a node."""

    # Stable id within the graph — lets the trace viewer point at a specific
    # guardrail when reporting a verdict.
    id: str

    # Which built-in (or saved custom) guardrail to use.
    type: str = Field(
        description="Built-in id: 'pii_redactor' | 'schema_validator' | 'prompt_judge' | 'injection_detector'"
    )

    # Per-guardrail config. The shape is owned by each guardrail implementation.
    config: dict[str, Any] = Field(default_factory=dict)

    # What to do if the guardrail rejects. The guardrail's own action takes
    # precedence; this is the fallback policy.
    on_reject: Literal["abort", "warn"] = "abort"

    # Provenance — set when the attachment was loaded from the SavedGuardrail
    # library. Used by the UI to offer "Sync from library" when the library
    # has a newer version. Config is still a SNAPSHOT (not a live reference)
    # to avoid silent behavior changes across agents.
    source_id: str | None = None
    source_version: int | None = None


# ─── Node specs (discriminated union on `kind`) ──────────────────────────────


class _BaseNode(BaseModel):
    id: str
    kind: str
    # Optional UI hints — position, label. Not used by the runtime.
    ui: dict[str, Any] = Field(default_factory=dict)


class InputNode(_BaseNode):
    """The single entry node. Holds the input-rail guardrails."""

    kind: Literal["input"] = "input"
    guardrails: list[GuardrailAttachment] = Field(default_factory=list)


class LLMNode(_BaseNode):
    """A single scoped LLM call (NOT a ReAct loop). Optional structured output."""

    kind: Literal["llm"] = "llm"
    system_prompt: str = ""
    llm_provider: str | None = None     # falls back to a default if unset
    llm_model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048
    # JSON schema for structured output. None = free-form text.
    output_schema: dict[str, Any] | None = None
    # Per-node guardrails — narrower scope than the input/output rails.
    pre_guardrails: list[GuardrailAttachment] = Field(default_factory=list)
    post_guardrails: list[GuardrailAttachment] = Field(default_factory=list)


class OutputNode(_BaseNode):
    """The single terminal node. Holds the output-rail guardrails."""

    kind: Literal["output"] = "output"
    guardrails: list[GuardrailAttachment] = Field(default_factory=list)


# Discriminated union — extend by adding the new class and the new Literal.
NodeSpec = Annotated[
    Union[InputNode, LLMNode, OutputNode],
    Field(discriminator="kind"),
]


# ─── Edges ───────────────────────────────────────────────────────────────────


class EdgeSpec(BaseModel):
    """A directed edge. `condition` is optional and only meaningful when the
    source node sets state["branch"] — the compiler emits a conditional edge.
    """

    source: str
    target: str
    condition: str | None = None  # match state["branch"] == condition


# ─── Top-level graph ─────────────────────────────────────────────────────────


class GraphSpec(BaseModel):
    """Full graph definition stored on ComposedAgent.graph_spec."""

    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    entry: str  # node id of the InputNode

    @model_validator(mode="after")
    def _validate_topology(self) -> "GraphSpec":
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("Duplicate node ids in graph_spec")

        if self.entry not in ids:
            raise ValueError(f"entry '{self.entry}' is not a known node id")

        entry_node = next(n for n in self.nodes if n.id == self.entry)
        if entry_node.kind != "input":
            raise ValueError("entry node must be of kind 'input'")

        # Exactly one input, exactly one output — enforced for Phase 1.
        # Multi-input/output graphs are a future enhancement.
        input_count = sum(1 for n in self.nodes if n.kind == "input")
        output_count = sum(1 for n in self.nodes if n.kind == "output")
        if input_count != 1:
            raise ValueError(f"graph must have exactly 1 input node, found {input_count}")
        if output_count != 1:
            raise ValueError(f"graph must have exactly 1 output node, found {output_count}")

        for e in self.edges:
            if e.source not in ids:
                raise ValueError(f"edge source '{e.source}' is not a known node id")
            if e.target not in ids:
                raise ValueError(f"edge target '{e.target}' is not a known node id")

        return self

    def node_by_id(self, node_id: str) -> NodeSpec:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)


# ─── Helpers for the API layer ───────────────────────────────────────────────


def default_graph_spec() -> dict[str, Any]:
    """A minimal valid graph: input -> llm -> output. Returned to the frontend
    when a user creates a new composed agent so the canvas is never empty."""
    return GraphSpec(
        nodes=[
            InputNode(id="input", ui={"position": {"x": 100, "y": 200}}),
            LLMNode(
                id="llm_main",
                system_prompt="You are a helpful AI assistant.",
                ui={"position": {"x": 400, "y": 200}},
            ),
            OutputNode(id="output", ui={"position": {"x": 700, "y": 200}}),
        ],
        edges=[
            EdgeSpec(source="input", target="llm_main"),
            EdgeSpec(source="llm_main", target="output"),
        ],
        entry="input",
    ).model_dump()
